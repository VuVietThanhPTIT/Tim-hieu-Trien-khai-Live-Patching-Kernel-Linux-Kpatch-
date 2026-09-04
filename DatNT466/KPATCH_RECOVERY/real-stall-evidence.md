# Evidence controlled pending transition bằng exact mentor patch

## 1. Kết luận

Controlled Userfaultfd harness đã giữ cùng một KVM vCPU task ở old patch state trong ít nhất 10 giây:

```text
TID 2250370
→ QEMU PID 2250361
→ domain vm1
→ patch_state=0
→ transition=1
→ direct_page_fault nằm trên cùng task stack
```

Condition này đủ để kích hoạt và so sánh recovery tại `T=10s`. Nó không đạt long-stall gate 75 giây: no-action validation hoàn tất ở `17.22s`, sau khi kernel ghi `livepatch: signaling remaining tasks`.

```text
CONTROLLED_PENDING_CONDITION_10S = PASS
SAME_TID_AFFECTED_STACK          = PASS
BLOCKER_DOMAIN_IDENTIFICATION    = PASS
LONG_STALL_75S                   = NOT REPRODUCED
```

## 2. Quy ước thời gian

| Mốc | Cách sử dụng |
|---|---|
| `10s` | Recovery trigger của scoped experiment |
| `75s` | Long-stall validation theo yêu cầu gốc |

Tài liệu không gọi run 10 giây là stall 75 giây.

## 3. Step 1 — Khóa environment và artifact

**Mục đích:** chứng minh lab dùng đúng host, kernel và patch mentor.

**Lệnh:**

```bash
hostname
uname -r
sha256sum /home/ubuntu/kpatch-recovery-lab/patches/trilogy-cve-2026-64561_git-diff-patch_noble.patch
sha256sum /home/ubuntu/kpatch-recovery-lab/output-mentor/trilogy-cve-2026-64561.ko
modinfo /home/ubuntu/kpatch-recovery-lab/output-mentor/trilogy-cve-2026-64561.ko \
  | grep -E '^(name|vermagic|livepatch):'
```

**Output thực tế:**

```text
datnt466-kpatch
6.8.0-134-generic
5b155448ad83ce9b3183be9ae272dc75bd058c579bcb71feb8f0204a7ce4edec  ...noble.patch
582d5f874fedf92ca5977b66055fca2f83f17170ba0db37227ce204f0c60d011  ...64561.ko
livepatch: Y
name: trilogy_cve_2026_64561
vermagic: 6.8.0-134-generic SMP preempt mod_unload modversions
```

Mentor patch thay đổi hoặc bổ sung các hàm:

```text
paging64_page_fault
paging32_page_fault
ept_page_fault
kvm_mmu_zap_child_spte_if_mismatch
kvm_mmu_get_child_sp
direct_page_fault
```

**Gate:** `EXACT_ARTIFACT=PASS`.

### Vì sao affected function được đổi sang `direct_page_fault`

Nested-L2 trial trước đó đã hit đường:

```text
handle_ept_violation
→ kvm_mmu_page_fault
→ kvm_mmu_do_page_fault
→ ept_page_fault
→ kvm_mmu_get_child_sp
→ kvm_mmu_zap_child_spte_if_mismatch
```

Nhưng counter quyết định vẫn là:

```text
direct_helper_to_zap = 0
```

Nghĩa là workload đã đi qua helper nhưng chưa tạo được child shadow SPTE có GFN/role mismatch để gọi `mmu_page_zap_pte()`. Exitless-L2, freeze và generic memslot overlap không bổ sung đúng stale-child condition đó. Phase sau cho phép đổi affected function nhưng không cho sửa mentor patch; vì vậy `direct_page_fault` được chọn do có thể chứng minh cùng TID giữ chính affected frame bằng UFFD. Báo cáo không claim nhánh mismatch cũ đã được tái hiện.

## 4. Step 2 — Tạo controlled blocker

**Mục đích:** giữ vCPU trong synchronous KVM page-fault path mà không sửa mentor patch hay livepatch state.

Hai helper nằm tại:

- host: [`inject_uffd.c`](inject_uffd.c);
- guest: [`touch_cli.c`](touch_cli.c).

Harness đăng ký một trang 4KB trong QEMU address space bằng Userfaultfd missing mode. Guest chạm GPA tương ứng; controller giữ fault chưa resolve.

**Lệnh theo run:**

```bash
# Host L0
sudo ./inject_uffd <QEMU_PID> <TARGET_HVA_HEX> <HOLD_SECONDS>

# Trong vm1
sudo insmod touch_cli.ko gpa=<TARGET_GPA>
```

`TARGET_HVA_HEX` và `TARGET_GPA` phải được resolve theo memory mapping của từng run; không dùng lại một địa chỉ cũ nếu chưa kiểm tra.

**Output đánh dấu fault đã hit:**

```text
EVENT: UFFD_PAGEFAULT_TRIGGERED
HOLDING vCPU IN direct_page_fault
```

Harness không sửa mentor patch, không ghi `patch_state`, không ghi `transition` và không chèn delay vào affected kernel function.

## 5. Step 3 — Load patch và quan sát

**Mục đích:** chứng minh memory fault thực sự chặn livepatch transition.

```bash
sudo python3 kpatch_recovery.py \
  --module /home/ubuntu/kpatch-recovery-lab/output-mentor/trilogy-cve-2026-64561.ko \
  --expected-sha256 582d5f874fedf92ca5977b66055fca2f83f17170ba0db37227ce204f0c60d011 \
  --patch-name trilogy_cve_2026_64561 \
  --deadline 10 \
  --poll-interval 0.5 \
  --total-timeout 120 \
  --log automation-run.log \
  --output-format both
```

**Output thực tế tại recovery trigger:**

```text
stall_deadline_reached deadline_seconds=10.0 observed_seconds=10.246
pending_task pid=2250361 tid=2250370 patch_state=0 comm="CPU 0/KVM"
qemu_pid=2250361 domain="vm1"
```

## 6. Step 4 — Chứng minh same-TID affected stack

**Mục đích:** tránh ghép `patch_state` của một task với stack của task khác.

**Lệnh kiểm tra tại mỗi checkpoint:**

```bash
TID=2250370
PATCH=/sys/kernel/livepatch/trilogy_cve_2026_64561

cat /proc/$TID/comm
cat /proc/$TID/patch_state
awk '/^Tgid:/ {print $2}' /proc/$TID/status
cat /proc/$TID/cgroup
cat "$PATCH/transition"
cat "$PATCH/enabled"
sudo cat /proc/$TID/stack
```

**Output rút gọn:**

```text
comm:          CPU 0/KVM
TID:           2250370
patch_state:   0
TGID/QEMU_PID: 2250361
domain:        vm1
transition:    1
enabled:       1

handle_userfault
...
kvm_faultin_pfn [kvm]
direct_page_fault+0x89/0x140 [kvm]
kvm_tdp_page_fault [kvm]
kvm_mmu_page_fault [kvm]
handle_ept_violation [kvm_intel]
```

Raw file [`synchronized-blocker.log`](../Docs/FINAL_EVIDENCE/same-tid/synchronized-blocker.log) ghi cùng condition tại các checkpoint:

| Checkpoint | TID | `patch_state` | `transition` | `direct_page_fault` |
|---:|---:|---:|---:|---|
| 1s | 2250370 | 0 | 1 | Có |
| 3s | 2250370 | 0 | 1 | Có |
| 5s | 2250370 | 0 | 1 | Có |
| 8s | 2250370 | 0 | 1 | Có |
| 10s | 2250370 | 0 | 1 | Có |

Đây là evidence quyết định cho controlled condition; không chỉ là một function-hit counter.

## 7. Step 5 — Mapping blocker domain

**Mục đích:** bảo đảm recovery chỉ tác động VM sở hữu pending task.

```bash
TID=2250370
QEMU_PID=$(awk '/^Tgid:/ {print $2}' /proc/$TID/status)
tr '\0' ' ' < /proc/$QEMU_PID/cmdline
cat /proc/$TID/cgroup
virsh domstate vm1
```

**Output thực tế:**

```text
TID 2250370
→ QEMU PID 2250361
→ domain vm1
→ running
```

**Gate:** `BLOCKER_DOMAIN_IDENTIFICATION=PASS`.

## 8. Step 6 — Long-stall validation

**Mục đích:** kiểm tra riêng condition có giữ `transition=1` tới 75 giây khi không recovery hay không.

Các state files được đọc lặp lại cho đến khi transition hoàn tất hoặc chạm 75 giây.

**Output thực tế rút gọn:**

```text
t= 0.04s | transition=1 | vcpu_patch_state=0
t=10.15s | transition=1 | vcpu_patch_state=0
t=15.20s | transition=1 | vcpu_patch_state=0
t=16.21s | transition=1 | vcpu_patch_state=1
t=17.22s | transition=0 | vcpu_patch_state=-1

livepatch: signaling remaining tasks
livepatch: 'trilogy_cve_2026_64561': patching complete
```

Kernel source evidence của environment có:

```c
#define SIGNALS_TIMEOUT 15
```

Observed completion trùng cửa sổ kernel signaling. Evidence này không chứng minh mọi loại blocker trên Linux 6.8 đều không thể vượt 75 giây; nó chỉ chứng minh UFFD condition hiện tại không đạt mốc đó.

**Gate:** `LONG_STALL_75S=NOT_REPRODUCED`.

## 9. Kết luận và nguồn raw

| Gate | Trạng thái |
|---|---|
| Exact mentor patch/module | **PASS** |
| Pending vCPU trên affected stack tới 10s | **PASS** |
| Same-TID correlation | **PASS** |
| TID → QEMU PID → domain | **PASS** |
| Condition đủ cho recovery comparison tại 10s | **PASS** |
| Continuous transition ≥75s | **NOT REPRODUCED** |
