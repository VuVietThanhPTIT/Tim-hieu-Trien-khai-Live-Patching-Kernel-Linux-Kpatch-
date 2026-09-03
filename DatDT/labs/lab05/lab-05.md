# Lab 05 — Phương án xử lý khi transition bị stall do stalled process của qemu-kvm

## 0. Bối cảnh và điều chỉnh quan trọng so với giả định ban đầu

Trước khi vào phương án xử lý, cần chốt lại 1 điểm kỹ thuật đã được xác minh qua thực nghiệm ở Lab 4 (quan trọng để phần giải thích của bạn không bị sai khi review nhóm):

**KVM MMU thật (`direct_page_fault`, `kvm_tdp_page_fault`) là các hàm cực nhanh** (giữ `mmu_lock`/RCU trong vài micro-giây), nên trong điều kiện thực tế, `kpatch load` gần như luôn transition xong trong 1-3 giây dù workload nặng cỡ nào — vì xác suất "bắt trúng" đúng khoảnh khắc 1 vCPU thread đang chạy dở bên trong hàm đó là cực thấp. Đây không phải là thất bại của lab, mà chính là **bằng chứng thực nghiệm cho lý do vì sao các hàm KVM MMU là ứng viên livepatch an toàn trong production**.

Trường hợp "stalled process" theo đúng nghĩa Lab 4 muốn mô tả — **transition treo kéo dài, quan sát được rõ ràng** — xảy ra khi có 1 tiến trình userspace (ở đây là vCPU thread của QEMU) **thực sự nằm trong 1 đoạn code kernel dài/blocking** tại đúng lúc kiểm tra "safe state". Trong lab, điều này được **mô phỏng chủ động** bằng cách chèn delay vào code đang được patch (qua kỹ thuật `kpatch unload` với patch có busy-loop chạy ở mọi lần gọi, thay vì one-shot) — kết quả tạo ra đúng hiện tượng: `transition` giữ nguyên `1`, `dmesg` liên tục log `klp_try_switch_task: CPU X/KVM:<pid> is running`.

Về bản chất cơ chế klp, `load` (forward transition) và `unload` (reverse transition) dùng **chung 1 thuật toán per-task consistency**, chỉ khác chiều chuyển — nên mọi phân tích và phương án xử lý dưới đây áp dụng như nhau cho cả 2 tình huống thực tế: transition treo khi *load* một bản vá mới (do gặp đúng 1 hàm blocking thật trong code cũ), hoặc treo khi *unload* một bản vá đang có code chạy lâu.


## 1. Nhắc lại tại sao không có "safe state" ngay lập tức

vCPU thread của QEMU phần lớn thời gian nằm trong `ioctl(KVM_RUN)` — thực chất đang thực thi code guest ở non-root VMX, chỉ quay lại host kernel khi có VM-exit (EPT violation, MMIO, interrupt...). Điều kiện "an toàn để chuyển" của klp yêu cầu **kernel stack hiện tại của task không chứa frame nào thuộc các hàm nằm trong patch**. Nếu tại đúng thời điểm worker retry kiểm tra, vCPU thread đang chạy dở bên trong 1 hàm blocking đủ dài (hàm patch có `cond_resched()`/`msleep()` chạy lặp lại, hoặc trong thực tế production là 1 hàm kernel thật sự giữ khoá lâu / đang chờ I/O), task đó **không thể được đánh dấu chuyển**, và vì hàm đó tiếp tục được gọi lại liên tục (do `stress-ng` sinh fault liên tục), xác suất "bắt trúng" task đang unsafe **luôn ở mức cao**, không giảm dần theo thời gian — đây chính là bản chất "không có safe state": an toàn đòi hỏi 1 lát cắt thời gian task hoàn toàn ra khỏi phạm vi patch, còn workload được thiết kế để loại trừ đúng lát cắt đó.



## 2. Các phương án xử lý, xếp theo mức độ can thiệp tăng dần

### Phương án A — `kpatch signal` (rẻ nhất, thử trước, thường không đủ với chính vCPU thread)

```bash
sudo kpatch signal
```

`kpatch signal` gửi tín hiệu vô hại tới các task đang ở `TASK_INTERRUPTIBLE`, ép chúng đi qua đường xử lý signal — nơi kernel cũng kiểm tra `TIF_PATCH_PENDING` và có thể chuyển patch state ngay tại đó. Hữu ích cho các kernel thread/tiến trình host khác đang giữ transition pending, nhưng **không tác dụng trực tiếp lên vCPU thread** trong kịch bản này — vì vCPU thread ở trạng thái `TASK_RUNNING` (đang thực thi busy-loop/`cond_resched()`), không phải sleep interruptible. Vẫn nên chạy đầu tiên để loại trừ nhiễu từ các task khác:

```bash
cat /sys/kernel/livepatch/<patch_name>/transition
kpatch list
ps -eLo pid,tid,stat,wchan:32,comm | grep qemu-system
```

### Phương án B — Tạm dừng (pause) vCPU của đúng 2 VM đang gây stall

Phương án thực tế và ít rủi ro nhất, tận dụng API sẵn có của libvirt/QEMU:

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
export TESTDIR=~/lab05/$TS
mkdir -p "$TESTDIR"

echo "PRE_PAUSE  : $(date -u +%FT%T.%N)" | tee -a "$TESTDIR/timeline.log"
virsh suspend vm1
virsh suspend vm2
```

`virsh suspend` gửi `stop` qua QMP — QEMU ngưng vòng lặp `KVM_RUN` của mọi vCPU thread (chúng rời `ioctl`, không tiếp tục sinh EPT violation mới, và nếu đang ở giữa 1 lần gọi hàm patch thì vòng `cond_resched()` bên trong vẫn tiếp tục chạy đến hết — nhưng vì guest không còn sinh fault mới, lần gọi hiện tại sẽ là lần cuối). Ngay khi hết fault mới, worker retry của klp (chạy định kỳ, thường mỗi ~100ms) sẽ bắt được lúc stack sạch và chuyển state.

```bash
until [ "$(cat /sys/kernel/livepatch/<patch_name>/transition)" = "0" ]; do
  sleep 0.1
done
echo "TRANSITION_DONE : $(date -u +%FT%T.%N)" | tee -a "$TESTDIR/timeline.log"

kpatch list | tee -a "$TESTDIR/timeline.log"

virsh resume vm1
virsh resume vm2
echo "POST_RESUME : $(date -u +%FT%T.%N)" | tee -a "$TESTDIR/timeline.log"
```

**Đo downtime thực tế** bằng đúng phương pháp Lab 3 (ping `-D` + `ts`, iperf3 `--logfile`) chạy song song trước/trong/sau, đối chiếu gap trong `ping.log` với `timeline.log`.

Điểm mạnh: downtime chỉ giới hạn trong khoảng `PRE_PAUSE → POST_RESUME`, thường vài trăm ms đến 1-2s. Cần lưu ý: đây là **service downtime thật** (guest ngưng thực thi hoàn toàn), khác với "transition duration" ở Lab 3 vốn không gây downtime — nêu rõ khác biệt này khi báo cáo.

### Phương án C — Huỷ patch, hoãn sang cửa sổ bảo trì khác (an toàn tuyệt đối)

```bash
sudo kpatch unload <patch_name>
kpatch list   # xác nhận đã gỡ sạch
```

Vì reverse transition cũng kiểm tra stack sạch từng task, nếu forward-transition đang stall thì lệnh huỷ này bản thân nó cũng có thể cần kết hợp Phương án B để chốt được. Phù hợp khi SLA không cho phép bất kỳ downtime chủ động nào — chấp nhận hoãn patch, dời sang giờ tải thấp hoặc sau khi drain VM.

### Phương án D — Live-migrate VM ra khỏi host trước khi patch (chuẩn production)

```bash
virsh migrate --live vm1 qemu+ssh://<host-khac>/system --verbose
virsh migrate --live vm2 qemu+ssh://<host-khac>/system --verbose

# host giờ không còn vCPU thread nào -> transition chốt ngay lập tức
sudo kpatch load <path-to.ko>
kpatch list

# tuỳ chọn: migrate VM quay lại sau khi patch xong
virsh migrate --live vm1 qemu+ssh://<host-nay>/system --verbose
virsh migrate --live vm2 qemu+ssh://<host-nay>/system --verbose
```

Downtime guest gần như bằng 0 (dark period ngắn cuối chu kỳ migrate, tách biệt hoàn toàn với vấn đề livepatch). Chi phí là cần host đích dự phòng và thời gian migrate tỉ lệ RAM/tốc độ dirty page. Đây là phương án chuẩn khi có nhiều host trong cluster.

> Lưu ý kỹ thuật đã rút ra trong quá trình thực hành: libvirt **chặn cứng việc migrate 1 domain về chính host của nó** (`Attempt to migrate guest to the same host <uuid>`) — nên phương án D chỉ khả thi khi thực sự có host đích khác, không thể mô phỏng bằng self-migrate trên cùng 1 máy.

---

## 3. Bảng so sánh 

| Phương án | Downtime guest | Độ phức tạp | Cần hạ tầng thêm | Khi nào dùng |
|---|---|---|---|---|
| A. `kpatch signal` | 0 | Thấp | Không | Luôn thử đầu tiên, loại trừ nguyên nhân từ task khác vCPU |
| B. `virsh suspend/resume` | Có, ngắn (đo được) | Trung bình | Không | Lab, hoặc prod chấp nhận downtime ngắn có kiểm soát |
| C. `kpatch unload`, hoãn patch | 0 (không patch) | Thấp | Không | SLA zero-downtime tuyệt đối, dời lịch |
| D. Live-migrate rồi patch host trống | ~0 (dark period rất ngắn) | Cao | Cần host đích | Production nhiều host, không chấp nhận downtime do patch |

---

## 4. Quy trình thực hành đề xuất (dùng lại patch stall đã build ở Lab 4)

```bash
# 1. Xác nhận đang ở trạng thái stall (transition = 1 kéo dài) sau kpatch unload
cat /sys/kernel/livepatch/<patch_name>/transition
kpatch list
dmesg -T | tail -10   # phải thấy klp_try_switch_task lặp lại cho vCPU thread

# 2. Thử phương án A trước
sudo kpatch signal
sleep 2
cat /sys/kernel/livepatch/<patch_name>/transition   # kỳ vọng: vẫn = 1 (vì vCPU không interruptible)

# 3. Áp dụng phương án B
TS=$(date -u +%Y%m%dT%H%M%SZ)
export TESTDIR=~/lab05/$TS
mkdir -p "$TESTDIR"

echo "PRE_PAUSE : $(date -u +%FT%T.%N)" | tee -a "$TESTDIR/timeline.log"
virsh suspend vm1
virsh suspend vm2

until [ "$(cat /sys/kernel/livepatch/<patch_name>/transition)" = "0" ]; do sleep 0.1; done
echo "TRANSITION_DONE : $(date -u +%FT%T.%N)" | tee -a "$TESTDIR/timeline.log"

virsh resume vm1
virsh resume vm2
echo "POST_RESUME : $(date -u +%FT%T.%N)" | tee -a "$TESTDIR/timeline.log"
```

