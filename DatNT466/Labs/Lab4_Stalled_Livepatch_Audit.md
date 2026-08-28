# LAB 4 – STALLED LIVEPATCH TRANSITION TRÊN KVM HOST

## 1. Mục tiêu

Lab 4 nhằm tái hiện và quan sát **livepatch transition bị stalled** trên KVM host đang chạy QEMU/KVM workload.

Mục tiêu audit:

- Tạo livepatch tác động vào đường `KVM_RUN`.
- Chạy CPU workload trên cả VM1 và VM2.
- Quan sát `transition=1` kéo dài.
- Xác định QEMU/vCPU thread nào chưa chuyển patch state.
- Liên hệ với transition state, safe state, per-task consistency và recovery.
- Xác nhận hai VM vẫn running sau transition/recovery.

---

## 2. Môi trường

Host:

```text
Kernel: 6.8.0-134-generic
```

VM:

```text
vm1 – running
vm2 – running
```

QEMU PID và vCPU thread:

```text
VM1 QEMU PID 10371
- TID 10380 CPU 0/KVM
- TID 10381 CPU 1/KVM

VM2 QEMU PID 10426
- TID 10434 CPU 0/KVM
- TID 10435 CPU 1/KVM
```

---

## 3. Candidate đầu tiên: `kvm_arch_vcpu_ioctl_run()`

Đường chạy:

```text
QEMU vCPU thread
    ↓
ioctl(KVM_RUN)
    ↓
kvm_vcpu_ioctl()
    ↓
kvm_arch_vcpu_ioctl_run()
    ↓
vcpu_run()
    ↓
guest execution
```

Patch thử nghiệm chỉ chèn:

```c
asm volatile("nop");
```

để buộc `kpatch-build` coi function là changed mà không đổi logic.

### Kết quả build

Build thất bại với:

```text
Found 19 unsupported jump label(s) in the patched code.
Use static_key_enabled() instead.
```

Các key liên quan gồm:

```text
kvm_has_noapic_vcpu
apic_hw_disabled
apic_sw_disabled
kvm_xen_enabled
```

### Finding

Không phải function nào compile được cũng có thể livepatch trực tiếp bằng kpatch. `kvm_arch_vcpu_ioctl_run()` chứa các jump label/static-key site mà kpatch-build hiện tại không hỗ trợ theo cách này.

---

## 4. Candidate thứ hai: wrapper `kvm_vcpu_ioctl()`

Từ `virt/kvm/kvm_main.c`, dòng gọi:

```c
r = kvm_arch_vcpu_ioctl_run(vcpu);
```

nằm trong:

```c
static long kvm_vcpu_ioctl(struct file *filp,
                           unsigned int ioctl,
                           unsigned long arg)
```

Patch:

```diff
 static long kvm_vcpu_ioctl(struct file *filp,
                            unsigned int ioctl, unsigned long arg)
 {
+        /* Lab 4: harmless instruction to exercise livepatch transition. */
+        asm volatile("nop");
+
         struct kvm_vcpu *vcpu = filp->private_data;
```

Dry-run:

```bash
patch -p1 --dry-run   < ~/kpatch-lab/patches/lab4-stall-wrapper.patch
```

Output:

```text
checking file virt/kvm/kvm_main.c
```

=> PASS.

---

## 5. Build module Lab 4

```bash
MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic' kpatch-build   -a 6.8.0-134-generic   -s ~/kpatch-lab/kernel-build/linux-source-6.8.0   -c ~/kpatch-lab/config-6.8.0-134-kpatch   -v ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic   -j 4   -n lab4-stall-wrapper   -o ~/kpatch-lab/output-lab4-wrapper   ~/kpatch-lab/patches/lab4-stall-wrapper.patch
```

Output quan trọng:

```text
changed function: kvm_vcpu_ioctl
Patched objects: arch/x86/kvm/kvm.ko
Building patch module: lab4-stall-wrapper.ko
SUCCESS
```

Module:

```text
~/kpatch-lab/output-lab4-wrapper/lab4-stall-wrapper.ko
```

Tên:

```text
lab4_stall_wrapper
```

---

## 6. Tạo workload

Trên VM1:

```bash
stress-ng --cpu 2 --cpu-method all --timeout 10m --metrics-brief
```

Trên VM2:

```bash
stress-ng --cpu 2 --cpu-method all --timeout 10m --metrics-brief
```

Mục tiêu là làm 4 guest vCPU bận, khiến QEMU vCPU thread liên tục đi qua KVM execution path.

---

## 7. Load patch đã từng stall

Kernel log:

```text
[Tue Aug 25 19:59:26 2026]
livepatch: enabling patch 'lab4_stall_wrapper'

[Tue Aug 25 19:59:26 2026]
livepatch: 'lab4_stall_wrapper': starting patching transition

[Tue Aug 25 19:59:41 2026]
livepatch: signaling remaining tasks

[Tue Aug 25 19:59:42 2026]
livepatch: 'lab4_stall_wrapper': patching complete
```

Timeline:

```text
19:59:26 start transition
19:59:41 signal remaining tasks
19:59:42 complete
```

=> Transition không hoàn tất ngay và đã cần signaling.

---

## 8. Reverse transition khi unload

Command:

```bash
sudo kpatch unload lab4_stall_wrapper
```

Output:

```text
disabling patch module: lab4_stall_wrapper
waiting (up to 15 seconds) for patch transition to complete...

patch transition has stalled!

kpatch: Livepatch process signaling is performed automatically on your system.
kpatch: Skipping manual process signaling.

waiting (up to 60 seconds) for patch transition to complete...
transition complete (2 seconds)
unloading patch module: lab4_stall_wrapper
```

Đây là bằng chứng trực tiếp rằng transition đã bị stalled.

---

## 9. Kernel log của reverse transition

```text
[Tue Aug 25 20:01:01 2026]
livepatch: 'lab4_stall_wrapper': starting unpatching transition

[Tue Aug 25 20:01:16 2026]
livepatch: signaling remaining tasks

[Tue Aug 25 20:01:18 2026]
livepatch: 'lab4_stall_wrapper': unpatching complete
```

=> Transition bị giữ khoảng 15 giây trước khi signaling remaining tasks.

---

## 10. Quan sát `transition=1`

Monitor ghi nhận nhiều lần:

```text
transition=1
```

=> kernel đang trong livepatch transition state và chưa hội tụ toàn bộ task về target state.

---

## 11. Per-task consistency: bắt đúng vCPU thread

Tại khoảng `20:00:54.977`, monitor ghi:

```text
VM1:
TID=10380 state=1 comm=CPU 0/KVM
TID=10381 state=1 comm=CPU 1/KVM

VM2:
TID=10434 state=1 comm=CPU 0/KVM
TID=10435 state=1 comm=CPU 1/KVM
```

Trong khi nhiều QEMU thread khác đã:

```text
state=0
```

Vì đây là **unload/reverse transition**, target state là:

```text
0 = unpatched
```

Do đó các vCPU còn:

```text
state=1
```

chính là các task chưa chuyển về unpatched state.

---

## 12. Quan sát chuyển state theo thời gian

Khoảng `20:00:55.606`:

```text
VM2 CPU 1/KVM:
state 1 → 0
```

Khoảng `20:00:56.225`:

```text
VM1 CPU 1/KVM:
state 1 → 0
```

Còn lại lâu hơn:

```text
VM1 CPU 0/KVM = 1
VM2 CPU 0/KVM = 1
```

Tới khoảng `20:01:04.061`, hai thread này vẫn còn:

```text
TID 10380 CPU 0/KVM state=1
TID 10434 CPU 0/KVM state=1
```

Đến khoảng `20:01:10.587`, các QEMU vCPU thread quan sát được đều đã về:

```text
state=0
```

---

## 13. Giải thích transition state

Trong transition, các task khác nhau có thể ở trạng thái khác nhau:

```text
task A: patch_state=0
task B: patch_state=1
```

Đây không phải inconsistency của cùng một task.

Đó là:

```text
per-task consistency
```

Mỗi task vẫn chạy nhất quán theo patch state của chính nó.

---

## 14. Giải thích safe state

Safe state không có nghĩa toàn bộ VM phải dừng.

Nó có nghĩa task phải đến điểm mà livepatch framework có thể chuyển patch state an toàn.

Function được patch là:

```text
kvm_vcpu_ioctl()
```

QEMU vCPU thread có thể đang nằm sâu trong:

```text
kvm_vcpu_ioctl()
    ↓
kvm_arch_vcpu_ioctl_run()
    ↓
vcpu_run()
    ↓
guest execution
```

Khi affected execution path vẫn liên quan đến stack/context của task, livepatch không đổi state ngay lập tức.

Task phải đạt điểm phù hợp để chuyển.

---

## 15. Vì sao workload làm stall rõ hơn?

`stress-ng` giữ guest CPU-bound:

```text
guest CPU busy
    ↓
QEMU vCPU thread
    ↓
KVM_RUN
    ↓
kvm_vcpu_ioctl()
```

Kết quả quan sát thực tế cho thấy các thread:

```text
CPU 0/KVM
CPU 1/KVM
```

giữ `patch_state=1` lâu hơn nhiều thread QEMU khác trong reverse transition.

---

## 16. Recovery

Recovery lần này diễn ra tự động:

```text
transition stalled
    ↓
signaling remaining tasks
    ↓
vCPU threads lần lượt đạt safe state
    ↓
patch_state 1 → 0
    ↓
unpatching complete
    ↓
module unload
```

Kernel log xác nhận:

```text
signaling remaining tasks
unpatching complete
```

---

## 17. Trạng thái VM sau recovery

```bash
virsh list
```

Output:

```text
 Id   Name   State
----------------------
 2    vm1    running
 3    vm2    running
```

=> Hai VM vẫn hoạt động.

Không cần:

```text
host reboot
VM restart
VM migration
```

---

## 18. So sánh Lab 3 và Lab 4

| Hạng mục | Lab 3 | Lab 4 |
|---|---|---|
| Patch target | KVM MMU | KVM_RUN wrapper |
| Workload | ping + iperf3 | stress-ng CPU |
| Transition | nhanh | stalled |
| `transition=1` kéo dài | không đáng kể | có |
| Per-task `patch_state` | không cần | quan sát trực tiếp |
| QEMU vCPU task chậm | không | có |
| Recovery | bình thường | signaling remaining tasks |
| Host reboot | không | không |
| VM migration | không | không |

---

## 19. Testcase bổ sung: MMU-specific unpatching stall

Testcase bổ sung được thực hiện để kiểm chứng trực tiếp trường hợp patch nằm
trong `arch/x86/kvm/mmu/mmu.c`, trong khi một QEMU vCPU thread chưa quay về
QEMU userspace và patched function vẫn còn trên kernel stack.

### 19.1 Controlled patch

Function được patch:

```text
kvm_mmu_page_fault()
```

Patch chỉ giữ TID `10380` (`VM1 CPU 0/KVM`) trong function khoảng 25 giây.
Vòng `msleep(20)` nhường scheduler nhưng vẫn giữ MMU stack frame, tránh
busy-spin khóa cứng CPU host:

```c
if (unlikely(current->pid == 10380)) {
        lab4d_deadline = jiffies + msecs_to_jiffies(25000);
        pr_info("lab4d: enter kvm_mmu_page_fault tid=%d\n", current->pid);
        while (time_before(jiffies, lab4d_deadline))
                msleep(20);
        pr_info("lab4d: exit kvm_mmu_page_fault tid=%d\n", current->pid);
}
```

Đây là controlled fault injection phục vụ lab, không phải patch production.

### 19.2 Build gate

```text
arch/x86/kvm/mmu/mmu.o: changed function: kvm_mmu_page_fault
Patched objects: arch/x86/kvm/kvm.ko
Building patch module: lab4d-mmu-stall.ko
SUCCESS
```

Artifact:

```text
Module   : lab4d_mmu_stall
Vermagic : 6.8.0-134-generic SMP preempt mod_unload modversions
SHA-256  : 2a9c718daadc13a285677e2d75695a1009dff5892c6282db7016ef879b7ba958
```

ELF chứa `.kpatch.funcs`, `__versions` và
`.klp.rela.kvm..text.kvm_mmu_page_fault`.

### 19.3 Workload và trigger condition

VM1 chạy memory workload pin vào guest CPU 0:

```bash
taskset -c 0 stress-ng \
  --vm 1 \
  --vm-bytes 2G \
  --vm-keep \
  --timeout 60s
```

Chỉ bắt đầu unpatch sau khi kernel xác nhận:

```text
kvm: lab4d: enter kvm_mmu_page_fault tid=10380
```

### 19.4 Evidence stalled transition

Kpatch CLI:

```text
disabling patch module: lab4d_mmu_stall
waiting (up to 15 seconds) for patch transition to complete...
patch transition has stalled!
waiting (up to 60 seconds) for patch transition to complete...
transition complete (6 seconds)
unloading patch module: lab4d_mmu_stall
```

Tổng thời gian unload khoảng 22 giây. Kernel log ghi nhận:

```text
starting unpatching transition
signaling remaining tasks
kvm: lab4d: exit kvm_mmu_page_fault tid=10380
unpatching complete
```

Trong chiều unpatching, target state là `0`. Monitor root ghi nhận khoảng 20
giây liên tục:

```text
enabled=0 transition=1
tid10380=1
tid10381=0
tid10434=0
tid10435=0
```

Khi patched function trả về, TID `10380` chuyển `1 → 0` và transition hoàn
tất.

Kernel stack của blocker:

```text
msleep
kvm_mmu_page_fault [lab4d_mmu_stall]
handle_ept_violation [kvm_intel]
__vmx_handle_exit [kvm_intel]
vcpu_enter_guest [kvm]
vcpu_run [kvm]
kvm_arch_vcpu_ioctl_run [kvm]
kvm_vcpu_ioctl [kvm]
```

Evidence này liên kết trực tiếp:

```text
QEMU vCPU thread
    ↓
KVM_RUN / EPT violation
    ↓
kvm_mmu_page_fault() còn trên stack
    ↓
TID 10380 giữ patch_state=1
    ↓
unpatching transition bị stalled
```

### 19.5 Recovery và trạng thái cuối

Không dùng `force`, không reboot, không kill QEMU và không migrate VM.
Transition tự hội tụ khi controlled function trả về.

```text
Livepatch module      : đã unload
Livepatch sysfs entry : đã biến mất
VM1 / VM2             : running
Ping VM1 / VM2        : 0% packet loss
Kernel Oops/BUG/lockup: không có
```

Testcase này chứng minh MMU-specific stall ở **chiều unpatching**. Nó không
được dùng để khẳng định patching stall hoặc suy rộng rằng mọi patch MMU đều
gây stall.

---

## 20. Audit findings

### Finding 1
Không phải function nào compile được cũng livepatch được. `kvm_arch_vcpu_ioctl_run()` bị kpatch-build từ chối do 19 unsupported jump labels.

### Finding 2
CPU load cao không bảo đảm transition chắc chắn stall, nhưng trong Lab 4 đã tái hiện được transition kéo dài tới ngưỡng signaling.

### Finding 3
Stall có thể xảy ra ở cả hai chiều:
- patching transition,
- unpatching transition.

### Finding 4
Trong reverse transition:
```text
target state = 0
```
nên task còn:
```text
patch_state=1
```
là task chưa quay về unpatched state.

### Finding 5
MMU workload hoặc function activity không tự động gây stall. Testcase bổ sung
chỉ stall khi `kvm_mmu_page_fault()` thực sự còn trên vCPU stack trong lúc
unpatching; đây là evidence trực tiếp cho mối quan hệ giữa call stack, safe
switching opportunity và per-task consistency.

---

## 21. Checklist Lab 4

| Hạng mục | Trạng thái |
|---|---|
| Tìm KVM_RUN path | PASS |
| Candidate `kvm_arch_vcpu_ioctl_run` | FAIL do jump labels |
| Candidate wrapper `kvm_vcpu_ioctl` | PASS |
| Patch dry-run | PASS |
| kpatch-build | PASS |
| Livepatch module | PASS |
| VM1 stress-ng | PASS |
| VM2 stress-ng | PASS |
| `transition=1` kéo dài | PASS |
| kpatch báo stalled | PASS |
| Kernel signal remaining tasks | PASS |
| Xác định QEMU PID | PASS |
| Xác định vCPU TID | PASS |
| Bắt per-task `patch_state` | PASS |
| Quan sát `1 → 0` | PASS |
| Unpatching complete | PASS |
| Controlled patch trực tiếp trong `mmu.c` | PASS |
| Bắt stack `kvm_mmu_page_fault` của blocker | PASS |
| MMU-specific unpatching stall | PASS |
| MMU-specific patching stall | CHƯA KIỂM CHỨNG |
| Không dùng force/reboot/kill QEMU | PASS |
| vm1 sau lab | running |
| vm2 sau lab | running |

---

## 22. Kết luận

Lab 4 đã tái hiện thành công **stalled livepatch transition** trên KVM host.

Hai testcase đã tái hiện stall bằng các target:

```text
Lab 4A: kvm_vcpu_ioctl()
Lab 4D: kvm_mmu_page_fault()
```

Trong khi hai VM chạy CPU-bound workload, kernel ghi nhận transition kéo dài và phải:

```text
signaling remaining tasks
```

Kpatch CLI trực tiếp báo:

```text
patch transition has stalled!
```

Trong thời gian `transition=1`, per-task state cho thấy các QEMU vCPU thread vẫn ở:

```text
patch_state=1
```

trong khi reverse transition yêu cầu:

```text
patch_state=0
```

Các thread lần lượt đạt trạng thái phù hợp và chuyển:

```text
1 → 0
```

sau đó:

```text
unpatching complete
```

Trong testcase MMU bổ sung, stack trực tiếp chứng minh TID `10380` đang nằm
trong `kvm_mmu_page_fault()` trên đường EPT violation/KVM_RUN. TID này giữ
`patch_state=1` trong khi ba vCPU khác đã về target `0`, rồi chỉ chuyển `1 → 0`
khi function trả về.

Hai VM vẫn `running`.

### Kết luận kỹ thuật

Linux livepatch không ép mọi task đổi code ngay lập tức. Hệ thống duy trì **per-task consistency** và chờ từng task đạt trạng thái an toàn để chuyển patch state.

Nếu một task chưa thể chuyển, toàn bộ transition có thể bị giữ ở:

```text
transition=1
```

cho tới khi task đạt safe state hoặc livepatch framework thực hiện recovery như signaling remaining tasks.
