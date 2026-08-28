# 06 – QEMU, KVM và Luồng thực thi Kernel liên quan đến Livepatch

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [Kiến trúc QEMU/KVM: Phân tách vai trò Userspace và Kernel Space](#1-kiến-trúc-qemukvm-phân-tách-vai-trò-userspace-và-kernel-space)
3. [Đường thực thi lệnh: Vòng lặp KVM_RUN và VM Entry / VM Exit](#2-đường-thực-thi-lệnh-vòng-lặp-kvm_run-và-vm-entry--vm-exit)
4. [Ảo hóa bộ nhớ: KVM MMU, SPTE, EPT/NPT và TLB Flush](#3-ảo-hóa-bộ-nhớ-kvm-mmu-spte-eptnpt-và-tlb-flush)
5. [Tác động của KVM Workload tới quá trình Livepatch Transition](#4-tác-động-của-kvm-workload-tới-quá-trình-livepatch-transition)
6. [Thực hành chẩn đoán: Phân tích bài lab KVM và Checklist Audit](#5-thực-hành-chẩn-đoán-phân-tích-bài-lab-kvm-và-checklist-audit)
7. [Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **vCPU** | Virtual CPU (Bộ xử lý trung tâm ảo) | Thread trong Userspace đại diện cho một CPU ảo của máy ảo. |
| **ioctl** | Input/Output Control (Lệnh điều khiển I/O) | System Call đặc biệt dùng để giao tiếp với kernel driver (`/dev/kvm`). |
| **KVM_RUN** | KVM Run ioctl Command (Lệnh thực thi vCPU) | Lệnh `ioctl` điều khiển vCPU bắt đầu hoặc tiếp tục vòng lặp thực thi Guest. |
| **VM Entry / Exit** | Virtual Machine Entry / Exit (Chuyển đổi ngữ cảnh VM) | Sự kiện chuyển đổi thực thi giữa Host Hypervisor và Guest Virtual Machine. |
| **SPTE** | Shadow Page Table Entry (Phần tử bảng trang bóng) | Phần tử bảng phân trang bộ nhớ ảo hóa do KVM MMU quản lý. |
| **EPT / NPT** | Extended / Nested Page Tables (Bảng trang ảo hóa phần cứng) | Tính năng ảo hóa bộ nhớ 2 cấp phần cứng Intel (EPT) và AMD (NPT). |
| **TLB** | Translation Lookaside Buffer (Bộ đệm dịch địa chỉ) | Bộ đệm cache phần cứng CPU tăng tốc dịch địa chỉ ảo sang vật lý. |
| **Signal Kick** | Livepatch Fake Signal (Tín hiệu ngắt cưỡng bức) | Tín hiệu ngắt cưỡng bức vCPU thread thoát khỏi `KVM_RUN` để hoàn tất transition. |

---

## 1. Kiến trúc QEMU/KVM: Phân tách vai trò Userspace và Kernel Space

Trong mô hình ảo hóa KVM, **QEMU** và **KVM** đảm nhận hai vai trò hoàn toàn khác nhau nhưng phối hợp chặt chẽ:

```text
 USERSPACE (QEMU Process)                                     KERNEL SPACE (Linux Kernel)
┌─────────────────────────────────────────┐                  ┌────────────────────────────────────────┐
│  QEMU Management Thread                 │                  │  KVM Kernel Module (kvm.ko)            │
│  - Thiết bị ảo (VirtIO, Disk, Net)      │                  │  - Giao diện thiết bị `/dev/kvm`       │
│  - Khởi tạo RAM máy ảo                  │                  │  - Quản lý bảng trang EPT / SPTE       │
│                                         │                  │  - Xử lý sự kiện VM Exit cấp thấp      │
│  QEMU vCPU Thread (TID 1234)            │   ioctl(KVM_RUN) │                                        │
│  - Chạy vòng lặp while(1)               ├─────────────────►│  Host CPU chuyển sang VMX Root mode    │
│  - Gọi System Call ioctl(KVM_RUN)       │                  │  cho phép Guest CPU chạy trực tiếp     │
└─────────────────────────────────────────┘                  └────────────────────────────────────────┘
```

- **QEMU (Userspace Manager):** Là một Process nằm ở Userspace chịu trách nhiệm quản lý vòng đời VM, giả lập thiết bị ngoại vi và khởi tạo các vCPU Threads.
- **KVM (Kernel Hypervisor Subsystem):** Là module Kernel (`kvm.ko`, `kvm_intel.ko`) trực tiếp điều khiển các tính năng ảo hóa phần cứng của CPU (Intel VT-x / AMD-V) để Guest VM thực thi lệnh ở tốc độ tiệm cận máy thật.

---

## 2. Đường thực thi lệnh: Vòng lặp KVM_RUN và VM Entry / VM Exit

### Chuỗi chuyển đổi ngữ cảnh (Context Switching Loop)

Mỗi vCPU ảo đại diện cho một POSIX Thread ở Userspace. Vòng lặp thực thi của vCPU diễn ra như sau:

```text
               LUỒNG THỰC THI VÒNG LẶP VCPU TRONG KVM
               
 Userspace (QEMU Thread) ────> ioctl(vcpu_fd, KVM_RUN)
                                      │
                                      ▼
 Kernel Space (Host KVM) ────> kvm_vcpu_ioctl()
                                      │
                                      ▼
                               kvm_arch_vcpu_ioctl_run()
                                      │
                                      ▼
                               vcpu_run() ───> [ VM ENTRY ] ───> CPU chạy Guest VM!
                                                                        │
                                                                  (VM EXIT xảy ra)
                                                                        │
 Userspace (QEMU) <─── [ VM EXIT ] <─── Xử lý ngắt / I/O <──────────────┘
```

1. **VM Entry:** Host CPU chuyển từ `Host Mode` sang `Guest Mode`, trao quyền điều khiển cho Guest OS chạy trực tiếp trên CPU.
2. **VM Exit:** Khi Guest OS thực hiện các thao tác đòi hỏi đặc quyền (I/O tệp, ngắt phần cứng, hoặc vi phạm bộ nhớ), CPU phần cứng phát sự kiện **VM Exit**, trả quyền điều khiển về cho KVM Kernel Module trong Host.

---

## 3. Ảo hóa bộ nhớ: KVM MMU, SPTE, EPT/NPT và TLB Flush

### Quy trình dịch địa chỉ bộ nhớ 2 cấp (Two-Dimensional Paging)

```text
 Guest Virtual Address (GVA) ────> [Guest Page Table] ────> Guest Physical Address (GPA)
                                                                     │
                                                                     ▼ [Hardware EPT / NPT]
 Host Physical Address (HPA) <───────────────────────────────────────┘
```

- **SPTE (Shadow Page Table Entry):** Các phần tử bảng trang do KVM MMU quản lý để ánh xạ địa chỉ `GPA -> HPA`.
- **Zap Mapping:** Thao tác hủy/xóa một ánh xạ trang bộ nhớ không còn hợp lệ (`kpatch_zap_present_spte`).
- **TLB Flush:** Sau khi Zap một SPTE, KVM bắt buộc phải Flush (xóa cache) bộ đệm **TLB (Translation Lookaside Buffer)** của CPU để đảm bảo vCPU không đọc lại địa chỉ ô nhớ cũ.

---

## 4. Tác động của KVM Workload tới quá trình Livepatch Transition

Đây là điểm mấu chốt kỹ thuật giải thích nguyên nhân vì sao các máy chủ ảo hóa KVM (Compute Hosts) rất dễ bị kéo dài thời gian Livepatch Transition (**Transition Stall**).

---

### 4.1. Bản chất kiến trúc của vòng lặp QEMU vCPU Thread

Trong mã nguồn QEMU, mỗi CPU ảo của máy ảo (Guest VM) tương ứng với 1 POSIX Thread nằm ở Userspace Host. vCPU thread này vận hành theo một vòng lặp vô hạn `while (1)` như sau:

```c
// Mã nguồn giả định đại diện cho vòng lặp vCPU Thread trong QEMU (Userspace)
void *qemu_kvm_cpu_thread_fn(void *arg) {
    while (vCPU_is_running) {
        // 1. Gọi System Call ioctl trao quyền cho KVM Kernel để nạp vCPU vào CPU phần cứng
        int r = ioctl(vcpu_fd, KVM_RUN, 0);  // <-- [HÀM BỊ KẸT TẠI ĐÂY LÂU NGÀY!]
        
        // 2. Khi ioctl trả về (VM Exit), QEMU xử lý lý do thoát
        switch (run->exit_reason) {
            case KVM_EXIT_IO:   handle_io_emulation(); break;
            case KVM_EXIT_MMIO: handle_mmio_emulation(); break;
            case KVM_EXIT_INTR: break; // Tạm ngắt do Signal!
        }
    }
}
```

Khi máy ảo Guest đang chạy liên tục (ví dụ đang thực thi ứng dụng hoặc chịu tải stress CPU):
- CPU phần cứng lặp đi lặp lại giữa **VM Entry** (chạy mã Guest) và các **VM Exit ngắn** (xử lý ngắt phần cứng nhỏ trong KVM Kernel), rồi lập tức **VM Entry** trở lại Guest.
- vCPU thread **không bao giờ trả về khỏi System Call `ioctl(KVM_RUN)`** để trở lại Userspace QEMU! Nó nằm vĩnh viễn bên trong ranh giới System Call `ioctl`.

---

### 4.2. Hai điểm nghẽn kỹ thuật khiến vCPU Thread bị kẹt ở `patch_state = 0`

Khi người vận hành nạp một bản vá Livepatch sửa đổi các hàm KVM (như `kvm_vcpu_ioctl()`, `kvm_arch_vcpu_ioctl_run()`, hoặc các hàm KVM MMU), vCPU Thread bị chặn bởi 2 điểm nghẽn:

```text
                        2 ĐIỂM NGHẼN KHIẾN VCPU THREAD GÂY STALL
                                           │
         ┌─────────────────────────────────┴─────────────────────────────────┐
         ▼                                                                   ▼
  1. ĐIỂM NGHẼN CALLSTACK (STACK BLOCKING)                   2. ĐIỂM NGHẼN KERNEL-EXIT (BOUNDARY BLOCKING)
  Do vCPU thread nằm trong `ioctl(KVM_RUN)`,                Cơ chế chuyển đổi an toàn thứ 2 phụ thuộc vào
  các hàm KVM bị vá nằm thường trực 100%                     việc Task thoát khỏi System Call về Userspace.
  trên Callstack của Kernel.                                 Do vCPU thread nằm vĩnh viễn trong `ioctl`,
  --> Reliable Stack Check báo: UNSAFE TO SWITCH!            nó KHÔNG BAO GIỜ chạm ranh giới Kernel-Exit!
```

1. **Điểm nghẽn Callstack (Reliable Stack Check Failed):**
   - KLP Core dùng **ORC Unwinder (`klp_check_stack()`)** để kiểm tra Callstack của vCPU thread.
   - Thấy hàm bị vá nằm thường trực trên Stack của thread -> Kết luận: **Không an toàn để đổi mã**, giữ cờ `TIF_PATCH_PENDING = 1` và `patch_state = 0`.

2. **Điểm nghẽn Ranh giới Kernel-Exit (Kernel-Exit Boundary Never Touched):**
   - Cơ chế Safe State thứ hai dựa vào việc Task thoát hoàn toàn khỏi System Call về Userspace (nơi Kernel Stack = 0).
   - Nhưng vì vCPU thread nằm vĩnh viễn trong vòng lặp `while (1) { ioctl(KVM_RUN); }`, nó **không bao giờ thoát syscall về Userspace**!

**Hậu quả:** Cờ `sysfs: transition = 1` bị kẹt kéo dài. vCPU threads mang trạng thái `patch_state = 0` trở thành "kẻ cản đường" duy nhất khiến quá trình Livepatch không thể hoàn tất hội tụ (`transition = 0`).

---

### 4.3. Cơ chế giải cứu bằng Signal Kick (`klp_send_signals` / `SIGWINCH` / `kpatch signal`)

Làm thế nào để ép vCPU thread "buông" System Call `ioctl(KVM_RUN)` ra trong tích tắc mà **không làm hỏng hay crash máy ảo Guest**?

Giải pháp chính là **Signal Kick (Fake Signal)** qua 4 bước khép kín:

```text
               QUY TRÌNH XỬ LÝ SIGNAL KICK GIẢI CỨU TRANSITION STALL

  Step 1: KLP Core phát Fake Signal (SIGWINCH) tới Blocking vCPU Thread ID
                                │
                                ▼
  Step 2: CPU phần cứng VM-Exit với mã thoát `KVM_EXIT_INTR`
          `ioctl(KVM_RUN)` tạm thời TỰ ĐỘNG THOÁT VỀ USERSPACE!
                                │
                                ▼
  Step 3: Chạm ranh giới Kernel-Exit (exit_to_user_mode_prepare)
          Kernel Stack hoàn toàn rỗng -> Cập nhật `patch_state = 1` & Xóa `TIF_PATCH_PENDING`!
                                │
                                ▼
  Step 4: QEMU Userspace nhận KVM_EXIT_INTR, quay lại đầu vòng lặp while(1)
          Gọi lại `ioctl(KVM_RUN)` -> vCPU thread chạy mã mới an toàn 100%!
```

#### Chi tiết 4 bước thực thi:

- **Bước 1 (Phát Fake Signal):** Livepatch Core (hoặc lệnh `kpatch signal`) phát một tín hiệu ngắt nhẹ giả (**Pseudo-Signal** như `SIGWINCH`) tới PID/TID của vCPU thread đang kẹt.
- **Bước 2 (Ép VM-Exit `KVM_EXIT_INTR`):**
  - Tín hiệu làm cờ ngắt `signal_pending(current)` của thread đổi thành `true`.
  - KVM Kernel phát hiện có signal chờ xử lý, lập tức dừng vòng lặp `vcpu_run()`, đặt mã lý do thoát `run->exit_reason = KVM_EXIT_INTR`, và **hoàn tất trả về (return) từ system call `ioctl(KVM_RUN)` về Userspace QEMU**.
- **Bước 3 (Chạm ranh giới Kernel-Exit và Cập nhật `patch_state = 1`):**
  - Ngay tại khoảnh khắc `ioctl(KVM_RUN)` vừa trả về chuẩn bị thoát khỏi Kernel Space (`exit_to_user_mode_prepare()`), Kernel kiểm tra cờ `TIF_PATCH_PENDING`.
  - Tại ranh giới này, Kernel Stack hoàn toàn sạch sẽ (bằng 0). Kernel lập tức cập nhật:
    ```c
    current->patch_state = 1;  // Đã hội tụ sang mã mới!
    clear_tsk_thread_flag(current, TIF_PATCH_PENDING); // Xóa cờ chờ
    ```
- **Bước 4 (Tiếp tục vòng lặp vCPU mượt mà - Zero Downtime):**
  - QEMU Userspace nhận mã `KVM_EXIT_INTR`, biết đây chỉ là tín hiệu ngắt nhẹ, nó không ngắt VM mà chỉ đơn giản quay lại đầu vòng lặp `while(1)` và gọi lại `ioctl(vcpu_fd, KVM_RUN)`.
  - Từ lần gọi `ioctl` tiếp theo này, vCPU thread đã mang `patch_state = 1` và chạy hoàn toàn trên mã máy mới thông qua `ftrace redirect`! Máy ảo Guest hoàn toàn không hề nhận ra mình vừa trải qua một đợt Livepatch!

> Signal không làm patch an toàn; signal chỉ đưa task tới nơi mà livepatch consistency model có thể chuyển nó an toàn.Ý là sau khi thoát khỏi điểm nghẽn thì vẫn phải qua cơ chế kiểm tra.
---

## 5. Thực hành chẩn đoán: Phân tích bài lab KVM và Checklist Audit

### Phân tích sự khác biệt giữa Lab 3 và Lab 4

- **Lab 3 (KVM MMU Patch - Network Workload):** Vá logic KVM MMU. Khi chạy traffic ping/iperf, các VM Exits diễn ra đứt quãng, vCPU Threads thường xuyên chạm safe point giúp Transition hoàn tất gần như lập tức.
- **Lab 4 (Wrapper Patch - Stress Workload):** Vá hàm `kvm_vcpu_ioctl()`. Khi chạy `stress-ng` vắt kiệt CPU, vCPU Threads nằm vĩnh viễn trong vòng lặp `KVM_RUN`, khiến Transition rơi vào trạng thái Stall cho đến khi phát Signal Kick.

### Checklist Audit dành cho KVM Security Patches:

```text
[ ] Bản vá sửa đổi hàm nằm ở Module nào: vmlinux, kvm.ko, hay kvm_intel.ko?
[ ] Hàm bị vá có nằm trực tiếp trên đường hot path KVM_RUN / MMU hay không?
[ ] Bản vá có làm thay đổi cấu trúc dữ liệu SPTE / EPT hay không?
[ ] Đã kiểm tra trạng thái patch_state của từng QEMU vCPU thread chưa?
[ ] Có cần phát Signal Kick để ép vCPU thoát KVM_RUN hoàn tất transition không?
```

---

## 6. Tài liệu tham khảo

- [Linux Kernel KVM API Documentation](https://docs.kernel.org/virt/kvm/api.html)
- [KVM MMU Architecture & Shadow Paging](https://docs.kernel.org/virt/kvm/mmu.html)
- [Linux Kernel Livepatch Integration](https://docs.kernel.org/livepatch/livepatch.html)
