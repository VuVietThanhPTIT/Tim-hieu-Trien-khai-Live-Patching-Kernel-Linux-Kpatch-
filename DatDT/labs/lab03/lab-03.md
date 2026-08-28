# Lab 03 — Phần 2 & 3: kpatch-build (audit) + Đo hiệu năng khi live patch

## Phần 2 — kpatch-build: build lại  + ghi audit log
### 2.1. Xác nhận `.ko` khớp đúng host trước khi dùng

```bash
modinfo -F vermagic ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
cat /proc/version
uname -r
```
→ chuỗi `vermagic` phải khớp `uname -r` (`6.8.0-134-generic ...`). Nếu không khớp → phải build lại theo đúng quy trình lab02 (source tree tag `Ubuntu-6.8.0-134.134`, `.config` từ `/boot/config-6.8.0-134-generic`, `vmlinux` dbgsym cùng version).

### 2.2. Ghi audit log (bắt buộc, để đánh giá/đối chiếu sau này)

```bash
mkdir -p ~/lab03/audit
cd ~/kpatch-lab

{
  echo "## Audit Log — kpatch-build (Lab03)"
  echo "- Người thực hiện       : $(whoami)"
  echo "- Ngày build             : $(date -u +"%Y-%m-%d %H:%M:%S UTC")"
  echo "- Host build/target      : $(hostname) / $(hostname -I | awk '{print $1}')"
  echo
  echo "### Vật liệu"
  echo "- Kernel target (uname -r) : $(uname -r)"
  echo "- dpkg version linux-image : $(dpkg -l | grep linux-image-6.8.0-134-generic | awk '{print $3}')"
  echo "- Source tree tag           : $(git -C ~/kpatch-lab/patches/noble log -1 --oneline)"
  echo "- .config sha256             : $(sha256sum ~/kpatch-lab/config-6.8.0-134-kpatch)"
  echo "- vmlinux dbgsym sha256      : $(sha256sum ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic)"
  echo "- patch file sha256          : $(sha256sum ~/kpatch-lab/patches/kvm-mmu.patch)"
  echo "- .ko output sha256          : $(sha256sum ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko)"
  echo "- vermagic của .ko           : $(modinfo -F vermagic ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko)"
  echo "- cat /proc/version (host)   : $(cat /proc/version)"
} | tee ~/lab03/audit/audit-$(date -u +%Y%m%dT%H%M%SZ).md
```

File audit này chính là "material chứng minh" `.ko` hợp lệ để dùng ở Phần 3 — giữ lại cùng bộ log hiệu năng.

---

## Phần 3 — Load module khi 2 VM đang chạy + ghi log đo hiệu năng
### 3.1. Chuẩn bị thư mục log

```bash
mkdir -p ~/lab03/perf-test/$(date -u +%Y%m%dT%H%M%SZ)
export TESTDIR=~/lab03/perf-test/$(date -u +%Y%m%dT%H%M%SZ)
echo $TESTDIR
```

### 3.2. Đặt tham số thời gian đo (baseline → load → sau load)
- **Baseline**: 15s trước khi load (đo trạng thái "bình thường" để so sánh).
- **Load**: thời điểm chạy `kpatch load`.
- **Post-load**: 15s sau khi load (đo trạng thái ổn định sau patch).
- Tổng thời lượng ping/iperf3 nên chạy: **~35–40s** để trùm hết cả 3 giai đoạn.

### 3.3. Bật ping liên tục từ VM1 → VM2 (độ phân giải cao, có timestamp)
Trong **VM1** (ssh vào `10.0.50.11`), cài `moreutils` nếu chưa có rồi chạy:
```bash
sudo apt install -y moreutils   # cung cấp lệnh `ts`
ping -D -i 0.2 -w 40 10.0.50.12 | ts '%Y-%m-%d %H:%M:%.S' > ~/ping.log &
```
> `-D` in epoch timestamp sẵn trong output của ping, `ts` thêm timestamp người đọc được cho từng dòng — dùng cả hai để tiện đối chiếu chéo. `-w 40` tự dừng sau 40s.

### 3.4. Bật iperf3 hai chiều liên tục trong lúc load patch
Trong **VM2** (`10.0.50.12`) — server:
```bash
iperf3 -s -i 1 --logfile ~/iperf3-server.log &
```

Trong **VM1** (`10.0.50.11`) — client, chạy 40s để trùm cả 3 giai đoạn:
```bash
iperf3 -c 10.0.50.12 -t 40 -i 1 --logfile ~/iperf3-client.log &
```

> Muốn kiểm cả 2 chiều cùng lúc: dùng `--bidir` thay vì chạy 1 chiều — `iperf3 -c 10.0.50.12 -t 40 -i 1 --bidir --logfile ~/iperf3-client.log`.
### 3.5. Chờ hết baseline (15s), rồi load module trên **host** — ghi timestamp chính xác

Trên **host** (không phải trong VM):
```bash
sleep 15   # đợi đủ baseline trước khi load, khớp mốc ở bước 3.3/3.4

echo "PRE_LOAD  : $(date -u +"%Y-%m-%dT%H:%M:%S.%N")" | tee -a $TESTDIR/timeline.log
sudo kpatch load ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
echo "POST_LOAD : $(date -u +"%Y-%m-%dT%H:%M:%S.%N")" | tee -a $TESTDIR/timeline.log

kpatch list | tee -a $TESTDIR/timeline.log
dmesg -T | tail -n 40 | tee $TESTDIR/dmesg-after-load.log
```

Chờ nốt phần post-load còn lại (cho ping/iperf3 chạy xong ~25s nữa):
```bash
sleep 25
```

### 3.6. Thu log về host để lưu trữ + phân tích

```bash
scp ubuntu@10.0.50.11:~/ping.log            $TESTDIR/vm1-ping.log
scp ubuntu@10.0.50.11:~/iperf3-client.log   $TESTDIR/vm1-iperf3-client.log
scp ubuntu@10.0.50.12:~/iperf3-server.log   $TESTDIR/vm2-iperf3-server.log
ls -la $TESTDIR
```

### 3.7 Phân tích log:
Phân tích log, ta thấy trong điều kiện workload và độ phân giải đo của Lab 3, không quan sát thấy downtime của VM connectivity khi áp livepatch lên KVM host.

Livepatch transition diễn ra trong khoảng 1–2 giây theo log/tooling, nhưng transition duration không đồng nghĩa với service downtime.