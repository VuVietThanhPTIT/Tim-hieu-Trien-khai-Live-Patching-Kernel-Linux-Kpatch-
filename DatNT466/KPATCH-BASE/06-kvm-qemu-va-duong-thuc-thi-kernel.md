# 06 – QEMU, KVM và đường thực thi kernel liên quan livepatch

## Mục lục

1. [1. QEMU/KVM architecture, file descriptor và vCPU thread](#1-qemukvm-architecture-file-descriptor-và-vcpu-thread)
2. [2. Đường thực thi: VM Entry/Exit, syscall và KVM_RUN](#2-đường-thực-thi-vm-entryexit-syscall-và-kvm_run)
3. [3. Memory virtualization, KVM MMU, SPTE và TLB](#3-memory-virtualization-kvm-mmu-spte-và-tlb)
4. [4. Vì sao KVM workload ảnh hưởng livepatch transition](#4-vì-sao-kvm-workload-ảnh-hưởng-livepatch-transition)
5. [5. Liên hệ Lab 3/Lab 4 và câu hỏi audit cho KVM CVE](#5-liên-hệ-lab-3lab-4-và-câu-hỏi-audit-cho-kvm-cve)
6. [6. Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

##  Đường thực thi QEMU/KVM liên quan livepatch

```text
Guest application
      |
      v
Guest kernel
      |
      | (VM Exit khi cần hypervisor xử lý)
      v
QEMU vCPU thread (userspace host)
      |
      | ioctl(KVM_RUN)
      v
/dev/kvm
      |
      v
Host kernel KVM
      |
      +--> kvm_vcpu_ioctl()
      |       |
      |       v
      |  kvm_arch_vcpu_ioctl_run()
      |       |
      |       v
      |    vcpu_run()
      |
      +--> KVM MMU / EPT-NPT / SPTE / TLB
      |
      v
VM Entry -> guest tiếp tục chạy
```

## 1. QEMU/KVM architecture, file descriptor và vCPU thread

**QEMU và KVM không phải một thứ**

**QEMU**

Process userspace quản lý VM:

- device emulation;
- VM lifecycle;
- vCPU threads;
- memory mapping;
- gọi KVM ioctl.

**KVM**

Kernel virtualization subsystem/module:

- expose `/dev/kvm`;
- quản lý VM/vCPU state;
- dùng hardware virtualization VT-x/AMD-V;
- xử lý VM exit;
- quản lý memory virtualization.

Mental model:

```text
QEMU = userspace VM manager
KVM  = kernel accelerator/hypervisor subsystem
CPU  = thực thi guest khi VM Entry
```

---

**KVM API là fd + ioctl model**

```text
open('/dev/kvm')
      ↓
KVM_CREATE_VM
      ↓
VM fd
      ↓
KVM_CREATE_VCPU
      ↓
vCPU fd
      ↓
ioctl(vcpu_fd, KVM_RUN)
```

`KVM_RUN` là vCPU ioctl để chạy guest virtual CPU.

---

**QEMU vCPU thread**

Thông thường mỗi virtual CPU có userspace thread tương ứng, ví dụ:

```text
CPU 0/KVM
CPU 1/KVM
```

Thread gọi `KVM_RUN`, vào host kernel, CPU chạy guest cho đến khi có lý do exit.

---

## 2. Đường thực thi: VM Entry/Exit, syscall và KVM_RUN

**VM Entry và VM Exit**

**VM Entry**

Host/KVM yêu cầu CPU bắt đầu guest execution.

**VM Exit**

CPU trả control về host do event cần hypervisor xử lý, tùy architecture/config:

- privileged/intercepted operation;
- I/O;
- interrupt/window condition;
- memory virtualization event;
- signal/kick;
- nested virtualization event;
- nhiều lý do khác.

---

**Guest syscall không đồng nghĩa VM Exit**

```text
Guest App
  ↓ syscall
Guest Kernel
```

Nếu guest kernel xử lý hoàn toàn trong guest context, **không cần VM Exit chỉ vì có syscall**.

VM Exit xảy ra khi hardware/KVM cần can thiệp theo virtualization controls.

---

**Host syscall path và driver/hardware**

Một userspace syscall trên host có thể:

```text
app → syscall → kernel subsystem
```

Chỉ khi operation cần device/hardware mới đi tiếp:

```text
kernel → driver → MMIO/DMA/interrupt → hardware
```

Không phải syscall nào cũng chạm driver/hardware.

---

**`kvm_vcpu_ioctl()` và `KVM_RUN`**

Trong host kernel, generic KVM ioctl wrapper xử lý nhiều command. Với `KVM_RUN`, trên x86 có path:

```text
kvm_vcpu_ioctl()
    ↓
kvm_arch_vcpu_ioctl_run()
    ↓
vcpu_run()
```

Đây là path phù hợp để nghiên cứu livepatch transition với QEMU vCPU thread.

---

## 3. Memory virtualization, KVM MMU, SPTE và TLB

**Memory virtualization**

```text
GVA = Guest Virtual Address
  ↓ guest page tables
GPA = Guest Physical Address
  ↓ EPT/NPT hoặc KVM MMU machinery
HPA = Host Physical Address
```

Modern x86 thường dùng hardware-assisted second-level translation:

- Intel EPT;
- AMD NPT.

KVM vẫn quản lý table/mapping lifecycle.

---

**SPTE**

Trong KVM MMU source, SPTE thường được dùng cho page-table entries mà KVM quản lý, không chỉ nghĩa hẹp “classic shadow paging”.

---

**Zap mapping**

“Zap” nghĩa là invalidate/remove mapping/page-table entry/page structure không còn hợp lệ.

Nếu mapping đổi nhưng CPU/vCPU vẫn giữ translation cũ trong TLB, có thể dùng stale mapping.

---

**TLB flush**

TLB cache translation. Khi mapping thay đổi cần invalidation, KVM phải bảo đảm relevant CPU/vCPU không tiếp tục dùng stale translation.

---

**Mapping patch MMU của lab**

Patch nghiên cứu thay đổi logic quanh:

```text
kvm_mmu_get_child_sp()
__link_shadow_page()
```

và thêm:

```text
kpatch_child_sp_matches()
kpatch_zap_present_spte()
```

High-level:

- kiểm tra existing child mapping có khớp target GFN/role không;
- nếu mapping present nhưng không phù hợp thì zap;
- bảo đảm TLB consistency khi mapping bị loại.

---

**`RELOC_HIDE`**

Trong kpatch context, một số reference/relocation cần được trình bày theo cách giúp build tooling xử lý symbol/address đúng khi function được tách sang livepatch module.

---

## 4. Vì sao KVM workload ảnh hưởng livepatch transition

**Cơ chế tác động chi tiết của vCPU Thread đến Transition**:

1. **Vòng lặp `KVM_RUN` liên tục**:
   Mỗi vCPU thread trong QEMU thực thi một vòng lặp `while (1)` gọi `ioctl(vcpu_fd, KVM_RUN)`. Khi guest OS chạy liên tục (ví dụ stress CPU), vCPU thread chỉ luân chuyển giữa hardware guest context (VM Entry) và KVM exit handler trong host kernel mà **không bao giờ thoát hẳn syscall `ioctl` để quay lại userspace**.

2. **Ảnh hưởng đến điểm Safe State**:
   - Nếu hàm bị vá nằm trực tiếp trên đường thực thi của vCPU (như `kvm_vcpu_ioctl()`, `vcpu_run()` hoặc các hàm KVM MMU), hàm đó sẽ nằm thường trực trên callstack của vCPU thread.
   - Do vCPU thread không thoát syscall, điểm chuyển đổi safe state tại ranh giới userspace (`exit_to_user_mode_prepare()`) không bao giờ được chạm tới.

3. **Cơ chế gỡ stall bằng Signal Kick (`klp_send_signals`)**:
   Khi phát hiện transition bị kéo dài, Livepatch core (hoặc lệnh `kpatch signal`) sẽ gửi signal giả (fake signal / `SIGWINCH` hoặc poke) tới vCPU thread. Signal này kích hoạt VM-Exit với mã thoát `KVM_EXIT_INTR`, ép `ioctl(KVM_RUN)` tạm thời ngắt và quay về ranh giới userspace. Tại đây, cờ `TIF_PATCH_PENDING` được kiểm tra và xử lý, cập nhật `patch_state = target` thành công cho vCPU thread trước khi nó tiếp tục vòng lặp `KVM_RUN`.

---

## 5. Liên hệ Lab 3/Lab 4 và câu hỏi audit cho KVM CVE

**Lab 3 vs Lab 4**

**Lab 3**

Patch KVM MMU, ping/iperf workload. Transition hoàn tất nhanh và không thấy downtime ở độ phân giải đo.

**Lab 4**

Patch wrapper `kvm_vcpu_ioctl()`, chạy stress-ng. Quan sát transition kéo dài và vCPU thread patch_state chưa hội tụ.

Kết luận:

```text
runtime behavior phụ thuộc function + workload + timing
```

---

**Audit questions cho KVM CVE**

```text
1. Fix nằm ở vmlinux, kvm.ko, kvm_intel.ko hay kvm_amd.ko?
2. Function có nằm trên KVM_RUN/MMU hot path không?
3. Fix đổi struct/shared data không?
4. QEMU vCPU thread có thể giữ affected function trên stack lâu không?
5. Workload nào exercise đúng code path?
6. VM Exit nào thực sự dẫn tới function đó?
```

---

## 6. Tài liệu tham khảo

- https://docs.kernel.org/virt/kvm/api.html
- https://docs.kernel.org/livepatch/livepatch.html
