# Lab 04 — Nhật ký thực hiện đầy đủ: Giả lập stalled process trong kpatch transition

> Tài liệu tổng hợp lại toàn bộ quá trình thực hiện Lab 04 từ lịch sử lệnh (`history`), bao gồm tất cả các lần thử thất bại, nguyên nhân, và hướng khắc phục. Host: `datdt113-kpatch4`, kernel `6.8.0-134-generic`, 2 VM `vm1`/`vm2` dựng từ Lab 1.

---

## 1. Mục tiêu ban đầu

Ép xác suất "stall" khi `kpatch load` **luôn > 0**, bằng cách bơm liên tục EPT violation/page-fault vào KVM MMU trong lúc load module, để quan sát hiện tượng `klp_try_switch_task: ... is running` lặp lại kéo dài — chứng minh per-task consistency model không đạt "safe state" khi vCPU thread liên tục chạy dở trong hàm bị patch.

---

## 2. Lần thử 1 — Self-migrate qua `exec:` để bật dirty-tracking (THẤT BẠI 2 lần, nguyên nhân khác nhau)

### 2.1. `virsh migrate` self-target — bị chặn bởi libvirt

```bash
virsh migrate-setspeed vm1 1
virsh migrate --live --unsafe vm1 qemu+ssh://localhost/system --verbose &
```

**Kết quả:** job bị `Stopped` liên tục mỗi lần Enter — do `SIGTTIN` (background job cố đọc host-key confirm / password từ controlling terminal). Khắc phục bằng cách setup SSH key passwordless:

```bash
ssh-keyscan -H localhost >> ~/.ssh/known_hosts
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
ssh -o BatchMode=yes localhost true && echo OK   # → OK
```

Sau khi SSH thông, `migrate` vẫn báo lỗi:

```
error: internal error: Attempt to migrate guest to the same host <uuid>
```

→ **libvirt chặn cứng việc self-migrate**, không có cờ nào lách được. Bỏ hướng này.

### 2.2. Chuyển sang `calc-dirty-rate` (QMP) — lỗi tham số

```bash
virsh qemu-monitor-command vm1 --pretty '{"execute":"calc-dirty-rate","arguments":{"calc-time":120}}'
```

```
"desc": "Calculation time is out of range [50ms, 60000ms]."
```

Thử lại với `59999` vẫn lỗi tương tự → API bị lỗi/validation bất thường trên bản QEMU này. Bỏ hướng này, chuyển sang `migrate` với đích giả.

### 2.3. `exec:cat > /dev/null` — CRASH cả 2 VM

```bash
virsh qemu-monitor-command vm1 --pretty '{"execute":"migrate-set-parameters","arguments":{"max-bandwidth":1048576}}'
virsh qemu-monitor-command vm1 --pretty '{"execute":"migrate","arguments":{"uri":"exec:cat > /dev/null"}}'
```

```
error: Unable to read from monitor: Connection reset by peer
```

**Chẩn đoán qua `dmesg`/`journalctl`:**

```
audit: ... comm="qemu-system-x86" sig=31 syscall=56 code=0x80000000
```

`sig=31`=SIGSYS, `syscall=56`=`clone` → QEMU chạy với `-sandbox on,...,spawn=deny` (seccomp cấm `fork`/`clone`). `exec:` URI bắt buộc QEMU `fork()` ra tiến trình `cat` → bị kernel giết ngay → domain `shut off` (`shutting down, reason=crashed`).

**Khắc phục:** start lại VM, chuyển hẳn sang `tcp:` URI (chỉ cần `socket()`/`connect()`, không đụng `clone`):

```bash
virsh start vm1; virsh start vm2

socat -u TCP-LISTEN:49001,reuseaddr,fork /dev/null &
socat -u TCP-LISTEN:49002,reuseaddr,fork /dev/null &
```

**Lỗi phụ:** lần đầu chạy `socat` bên trong `virsh console` (trong guest) thay vì trên host → `Connection refused` vì `127.0.0.1` của guest khác hẳn loopback của host. Sửa lại chạy `socat` đúng trên host:

```bash
virsh qemu-monitor-command vm1 --pretty '{"execute":"migrate","arguments":{"uri":"tcp:127.0.0.1:49001"}}'
virsh qemu-monitor-command vm2 --pretty '{"execute":"migrate","arguments":{"uri":"tcp:127.0.0.1:49002"}}'

virsh qemu-monitor-command vm1 --pretty '{"execute":"query-migrate"}'
# → "status": "active", remaining giảm dần theo thời gian → dirty-tracking hoạt động
```

✅ **Kết quả:** dirty-page tracking (write-protect toàn bộ RAM guest) đã bật thành công qua `tcp:` migration giả, không crash VM.

---

## 3. Lần thử 2 — Load `kvm-mmu-livepatch.ko` (patch Lab 2) trong lúc workload chạy — KHÔNG STALL

```bash
stress-ng --vm 2 --vm-bytes 80% --vm-keep --vm-method flip --timeout 0 &   # cả vm1, vm2
sudo kpatch load ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

```
transition complete (2 seconds)
```

Dù workload nặng và dirty-tracking active, transition vẫn nhanh. Nghi vấn: `direct_page_fault` (hàm Lab 2 patch) không phải đường xử lý fault thực tế đang dùng.

**Xác nhận qua các lệnh tra cứu:**

```bash
cat /sys/module/kvm/parameters/tdp_mmu        # → Y
grep -n -A30 'kvm_tdp_page_fault(struct kvm_vcpu *vcpu' arch/x86/kvm/mmu/mmu.c
grep -n -A25 'kvm_tdp_mmu_page_fault(struct kvm_vcpu *vcpu' arch/x86/kvm/mmu/mmu.c
```

→ Với `tdp_mmu=Y`, mọi EPT violation đi qua **`kvm_tdp_page_fault()`** (dispatcher cấp cao), không phải `direct_page_fault()` (chỉ dùng khi shadow MMU/legacy). Đây là target sai từ đầu.

---

## 4. Lần thử 3 — Build patch demo `msleep` vào `direct_page_fault` — SAI TARGET, không stall

```bash
cp arch/x86/kvm/mmu/mmu.c /tmp/mmu.c.lab4.orig
nano arch/x86/kvm/mmu/mmu.c   # chèn msleep vào direct_page_fault
git diff -- arch/x86/kvm/mmu/mmu.c > ~/kpatch-lab/patches/lab4-stall.patch

kpatch-build -a 6.8.0-134-generic -s ~/kpatch-lab/patches/noble \
  -c ~/kpatch-lab/config-6.8.0-134-kpatch \
  -v .../vmlinux-6.8.0-134-generic \
  -n lab4-stall-qemu -o ~/kpatch-lab/output-lab4 \
  ~/kpatch-lab/patches/lab4-stall.patch
```

Build thành công (`lab4-stall-qemu.ko`), load thử → vẫn "êm", không stall — đúng như dự đoán vì `direct_page_fault` gần như không được gọi khi `tdp_mmu=Y`.

---

## 5. Lần thử 4 — Trace xác nhận hàm thực sự chạy: `lab4-trace.patch`

```bash
cp arch/x86/kvm/mmu/mmu.c /tmp/mmu.c.lab4.clean
nano arch/x86/kvm/mmu/mmu.c   # thêm pr_warn_ratelimited vào kvm_tdp_mmu_page_fault
git diff -- arch/x86/kvm/mmu/mmu.c > ~/kpatch-lab/patches/lab4-trace.patch

kpatch-build ... -n lab4-trace -o ~/kpatch-lab/output-lab4-trace \
  ~/kpatch-lab/patches/lab4-trace.patch
sudo kpatch load ~/kpatch-lab/output-lab4-trace/lab4-trace.ko
```

**Lỗi vận hành:** chạy `sudo dmesg -C` (xoá buffer) trước khi kịp kiểm tra kết quả trace → mất bằng chứng, phải làm lại.

---

## 6. Lần thử 5 — Kprobe đếm hits để xác nhận đúng dispatcher (không cần build)

```bash
cd /sys/kernel/debug/tracing
echo 'p:direct_pf direct_page_fault' >> kprobe_events
echo 'p:tdp_disp kvm_tdp_page_fault' >> kprobe_events
echo 'p:tdp_mmu_pf kvm_tdp_mmu_page_fault' >> kprobe_events
echo 1 > events/kprobes/direct_pf/enable
echo 1 > events/kprobes/tdp_disp/enable
echo 1 > events/kprobes/tdp_mmu_pf/enable
echo 1 > tracing_on; sleep 3; echo 0 > tracing_on
grep -c 'direct_pf:' trace; grep -c 'tdp_disp:' trace; grep -c 'tdp_mmu_pf:' trace
```

**Lần đầu:** cả 3 đều 0 hits, và bị lỗi `write error: Invalid argument` khi tạo probe cho `kvm_tdp_mmu_page_fault`.

**Chẩn đoán:**

```bash
grep -w 'kvm_tdp_page_fault\|kvm_tdp_mmu_page_fault\|direct_page_fault' /proc/kallsyms
```

→ `kvm_tdp_mmu_page_fault` **không tồn tại** trong kallsyms (tên hàm khác ở bản kernel này). `direct_page_fault` và `kvm_tdp_page_fault` tồn tại hợp lệ. 0 hits ở cả 2 hàm còn lại → nghi ngờ **workload đã ngừng chạy** (VM sống >1 ngày không reboot, `unattended-upgrades`/`needrestart` có thể đã âm thầm restart `libvirtd`/gián đoạn `stress-ng` qua console session cũ).

**Lần sau (sau khi khôi phục lại `tcp:` migrate + `stress-ng --vm-method flip`):**

```bash
grep -c 'tdp_disp:' trace   # → 24 hits trong 5s, xác nhận workload đã hoạt động
```

---

## 7. Lần thử 6 — Build patch busy-loop trực tiếp vào `kvm_tdp_page_fault` — LỖI BUILD

```bash
cp arch/x86/kvm/mmu/mmu.c /tmp/mmu.c.lab4-stall-clean
nano arch/x86/kvm/mmu/mmu.c   # thêm atomic_t one-shot guard + while-loop busy wait trực tiếp trong thân hàm
git diff -- arch/x86/kvm/mmu/mmu.c > ~/kpatch-lab/patches/lab4-stall-tdp.patch

kpatch-build ... -n lab4-stall-tdp -o ~/kpatch-lab/output-lab4-stall-tdp \
  ~/kpatch-lab/patches/lab4-stall-tdp.patch
```

```
ERROR: changed section .altinstr_replacement not selected for inclusion
ERROR: arch/x86/kvm/mmu/mmu.o: 1 unsupported section change(s)
create-diff-object: unreconcilable difference
```

→ Chèn quá nhiều dòng trực tiếp vào thân hàm gốc làm compiler sắp xếp lại CPU-alternative instructions, `kpatch-build` không đối chiếu được. **Khắc phục:** tách logic ra hàm `noinline` riêng, chỉ chèn 1 dòng gọi hàm vào vị trí gốc (kỹ thuật đã dùng thành công ở Lab 2).

---

## 8. Lần thử 7 — Patch `lab4-kvm-tdp-livepatch.patch` (trace-only qua helper `noinline`) — BUILD OK, nhưng LOAD VẪN KHÔNG STALL

```bash
cp arch/x86/kvm/mmu/mmu.c /root/kpatch-lab/mmu.c.before-lab4
nano arch/x86/kvm/mmu/mmu.c   # thêm hàm noinline chỉ pr_info, gọi ở đầu kvm_tdp_page_fault
git diff -- arch/x86/kvm/mmu/mmu.c > ~/kpatch-lab/patches/lab4-kvm-tdp-livepatch.patch
patch -p1 --dry-run < ~/kpatch-lab/patches/lab4-kvm-tdp-livepatch.patch   # OK

kpatch-build ... -n lab4-kvm-tdp -o ~/kpatch-lab/output-lab4-tdp \
  ~/kpatch-lab/patches/lab4-kvm-tdp-livepatch.patch
```

```bash
LP=~/kpatch-lab/output-lab4-tdp/lab4-kvm-tdp.ko
modinfo -F vermagic "$LP"   # 6.8.0-134-generic SMP preempt mod_unload modversions — khớp
readelf -s "$LP" | grep kvm_tdp_page_fault   # FUNC LOCAL, tồn tại đúng

time kpatch load "$LP"
```

```
transition complete (2 seconds)
real  0m2.045s
```

**Kết luận quan trọng rút ra tại đây:** patch chỉ có `pr_info` (không delay) nên load luôn nhanh — đúng dự đoán. Cơ chế klp: task chỉ được kiểm tra "an toàn để chuyển" **1 lần** lúc `load`; code MỚI (dù có delay) không ảnh hưởng transition của chính lần `load` đó, vì task chỉ chạm code mới **sau khi** đã được đánh dấu patched. → Cần chuyển chiến lược sang **`kpatch unload`** (reverse transition, kiểm tra liên tục xem task có đang ở code mới hay không) để delay trong code mới thực sự gây stall.

---

## 9. Lần thử 8 — Kprobe riêng biệt với `cpu_relax()` busy-loop — STALL THẬT NHƯNG NGUY HIỂM (RCU stall + soft lockup)

Do lần thử 7 dùng `kpatch unload` với patch không có delay nên vẫn không đủ, chuyển sang giải pháp tách biệt: viết 1 kernel module riêng dùng **kprobe** để inject delay vào `kvm_tdp_page_fault`, độc lập với kpatch:

```bash
mkdir -p ~/lab4/kprobe-test && cd ~/lab4/kprobe-test
cat > kprobe_stall.c <<'EOF'
... (kprobe pre_handler, busy-loop bằng cpu_relax() trong deadline = jiffies + msecs_to_jiffies(stall_ms))
EOF
cat > Makefile <<'EOF'
obj-m += kprobe_stall.o
all:
	make -C /lib/modules/$(shell uname -r)/build M=$(PWD) modules
EOF
make
insmod ./kprobe_stall.ko pid1="$VM1_PID" pid2="$VM2_PID" stall_ms=90000
```

Sau nhiều lần thử (module bị latch one-shot `atomic_cmpxchg` khiến các lần `insmod` sau không fire lại, phải `rmmod`/`insmod` lại nhiều lần), cuối cùng khi cả dirty-tracking + `stress-ng --vm-method flip` đang chạy:

```
LAB4: STALL START target=kvm_tdp_page_fault pid=499249 tgid=499241
LAB4: STALL START target=kvm_tdp_page_fault pid=499454 tgid=499444
```

Đồng thời chạy background watcher tự động load patch ngay khi phát hiện stall:

```bash
( while true; do
    if dmesg | grep -q 'LAB4: STALL START target=kvm_tdp_page_fault'; then
        time kpatch load "$LP"
        break
    fi
    sleep 0.05
done ) &
```

**Kết quả quan sát được (đúng hiện tượng Lab 4 cần):**

```
livepatch: starting patching transition
livepatch: klp_try_switch_task: CPU 0/KVM:499249 is running   ← lặp lại mỗi ~1s
livepatch: klp_try_switch_task: CPU 1/KVM:499454 is running   ← suốt ~53 giây
...
livepatch: 'lab4_kvm_tdp': completing patching transition     ← chỉ ngay sau khi STALL END
```

**NHƯNG đồng thời xuất hiện lỗi kernel nghiêm trọng:**

```
watchdog: BUG: soft lockup - CPU#1 stuck for 23s! [CPU 1/KVM:499454]
watchdog: BUG: soft lockup - CPU#11 stuck for 26s/49s/75s/82s!
rcu: INFO: rcu_preempt self-detected stall on CPU
```

**Nguyên nhân:** kprobe pre-handler chạy với `preempt_disable()` tự động — `cpu_relax()` busy-loop 90 giây bên trong đó khoá cứng CPU vật lý, không nhường cho RCU callback/timer tick/watchdog → RCU stall thật, không phải hiện tượng klp mong muốn. Nếu host bật `panic_on_rcu_stall`/`softlockup_panic`, có thể đã crash toàn bộ host.

---

## 10. Khắc phục và dọn dẹp sau sự cố

```bash
# xác nhận host ổn định trước khi thao tác
uptime; dmesg -T | tail -30
dmesg -T | grep -iE 'rcu.*stall|panic|hard lockup|nmi watchdog'
cat /proc/loadavg
virsh domstate vm1; virsh domstate vm2
virsh qemu-monitor-command vm1 --pretty '{"execute":"query-status"}'

# gỡ patch và module theo đúng thứ tự
sudo kpatch unload lab4_kvm_tdp
lsmod | grep kprobe_stall
sudo rmmod kprobe_stall
dmesg -C
```

Kernel bị taint vĩnh viễn (`Tainted: G OELK`, chữ `L` = đã từng soft-lockup) cho tới lần reboot tiếp theo — không ảnh hưởng chức năng nhưng cần ghi nhận trong audit.

---
