# 04 – ftrace và cơ chế Function Redirect: Bộ điều hướng luồng thực thi hàm động

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [Bức tranh tổng thể: ftrace làm nhiệm vụ gì trong Livepatch?](#1-bức-tranh-tổng-thể-ftrace-làm-nhiệm-vụ-gì-trong-livepatch)
3. [Nền tảng biên dịch: Compiler Instrumentation (__fentry__ / NOP site)](#2-nền-tảng-biên-dịch-compiler-instrumentation-__fentry__--nop-site)
4. [Cách Livepatch dùng ftrace để bẻ hướng luồng hàm (Function Redirect)](#3-cách-livepatch-dùng-ftrace-để-bẻ-hướng-luồng-hàm-function-redirect)
5. [So sánh ftrace vs kprobes vs eBPF trong bài toán Livepatch](#4-so-sánh-ftrace-vs-kprobes-vs-ebpf-trong-bài-toán-livepatch)
6. [Sự phối hợp giữa ftrace Redirect Engine và Consistency Engine](#5-sự-phối-hợp-giữa-ftrace-redirect-engine-và-consistency-engine)
7. [6. Lệnh kiểm tra ftrace support trên hệ thống](#6-lệnh-kiểm-tra-ftrace-support-trên-hệ-thống)
8. [7. Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **IP** | Instruction Pointer (Con trỏ lệnh CPU) | Thanh ghi chỉ định địa chỉ lệnh tiếp theo CPU thực thi (`pt_regs->ip` / `%rip`). |
| **NOP** | No Operation (Lệnh không thao tác) | Lệnh mã máy "trống" được compiler/kernel chèn làm vị trí chờ để ghi đè hook. |
| **__fentry__ / mcount** | Compiler Profiling Hooks (Điểm hook đầu hàm) | Điểm hook được chèn ở đầu mỗi hàm (Function Entry) phục vụ dynamic tracing. |
| **FTRACE_OPS_FL_IPMODIFY** | Ftrace IP Modify Flag | Cờ cho phép ftrace handler thay đổi trực tiếp thanh ghi IP để bẻ hướng luồng thực thi sang hàm mới. |
| **kprobe** | Kernel Probe (Trình thăm dò Kernel động) | Cơ chế tracing linh hoạt cho phép đặt breakpoint hook tại địa chỉ lệnh bất kỳ trong kernel. |

---

## 1. Bức tranh tổng thể: ftrace làm nhiệm vụ gì trong Livepatch?

Để vá một Kernel đang chạy mà **không cần dừng máy chủ**, hệ thống bắt buộc phải có một cơ chế ngắt các cuộc gọi hàm cũ và chuyển hướng sang mã mới.

**ftrace** đóng vai trò là một **Bộ chuyển hướng giao thông động (Dynamic Traffic Switch)** nằm ở ngay điểm đầu tiên của hàm cũ (`Function Entry`):

```text
               LUỒNG THỰC THI HÀM KHI CHƯA KHÓA LIVEPATCH (TRƯỚC PATCH)
               
 Caller ───────────────────────────────────────────> old_function()
                                                     (Mã máy hàm cũ)


               LUỒNG THỰC THI HÀM SAU KHI KÍCH HOẠT LIVEPATCH
               
 Caller ────> [Function Entry Site]
                     │
                     ▼ (Bị ftrace ngắt và chuyển hướng)
             ┌─────────────────────────┐
             │  klp_ftrace_handler()   │  <-- [KLP Handler kiểm tra patch_state của Task]
             └───────────┬─────────────┘
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
  Task State = 0 (Unpatched)      Task State = 1 (Patched)
  (Tiếp tục chạy mã cũ)           (Sửa IP register nhảy sang mã mới)
         │                               │
         ▼                               ▼
    old_function()                  new_function()
```

Ghi nhớ nguyên lý cốt lõi:
- **ftrace** chịu trách nhiệm bẻ hướng luồng thực thi ở ranh giới đầu mỗi hàm.
- **KLP (Linux Livepatch Core)** chịu trách nhiệm quản lý tính nhất quán (`patch_state`) cho từng Task.

---

## 2. Nền tảng biên dịch: Compiler Instrumentation (__fentry__ / NOP site)

### Làm sao ftrace có thể ngắt cuộc gọi hàm mà không làm chậm hệ thống?

Khi Kernel được biên dịch với cờ `CONFIG_DYNAMIC_FTRACE`, Compiler (GCC/Clang) tự động chèn một điểm hook tên là **`__fentry__`** (trên x86_64) hoặc `mcount` ngay tại câu lệnh đầu tiên của **mọi hàm Kernel**.

```c
// Mã nguồn C gốc
void kvm_mmu_zap_page(struct kvm *kvm) {
    // Logic của hàm...
}

// Mã máy biên dịch sinh ra ở Function Entry Site (x86_64)
kvm_mmu_zap_page:
    call __fentry__        <-- [Compiler tự động chèn 5-byte call instruction!]
    push %rbp
    mov  %rsp, %rbp
    ...
```

### Cơ chế Dynamic Ftrace (Thay thế NOP runtime)

Khi Kernel boot xong, nếu chưa bật tracing hay livepatch, việc gọi `call __fentry__` ở hàng nghìn hàm sẽ gây sụt giảm hiệu năng (overhead).

Do đó, Kernel thực hiện một thao tác tinh tế: **Ghi đè lệnh `call __fentry__` thành lệnh `NOP` (No Operation - Lệnh 5-byte không làm gì)**.

```text
Trạng thái 1: TRACING OFF (Hoạt động bình thường - Zero Overhead)
Function Entry Site ────> [ NOP NOP NOP NOP NOP ] ────> Thực thi mã hàm gốc

Trạng thái 2: LIVEPATCH ACTIVE (Bật chuyển hướng)
Function Entry Site ────> [ call ftrace_caller ] ────> Nhảy vào klp_ftrace_handler()
```

---

## 3. Cách Livepatch dùng ftrace để bẻ hướng luồng hàm (Function Redirect)

### Sự khác biệt giữa Tracing thông thường và Livepatch Redirect

- **Tracing thông thường (Logging / Performance Tracking):** ftrace ghi lại log cuộc gọi hàm, sau đó **cho phép CPU quay lại chạy tiếp hàm cũ**.
- **Livepatch Redirect (Code Swapping):** ftrace can thiệp trực tiếp vào thanh ghi CPU để **bỏ qua hoàn toàn hàm cũ và nhảy sang hàm mới**.

```text
               TRACING THÔNG THƯỜNG                               LIVEPATCH REDIRECT
               
 old_function()                                      old_function() entry
       │                                                    │
       ▼                                                    ▼
 ftrace_callback()                                   klp_ftrace_handler()
       │ (Ghi log event)                                    │ (Kiểm tra patch_state)
       ▼                                                    ▼
 Quay lại chạy tiếp old_function()                  Sửa thanh ghi CPU IP register
                                                            │
                                                            ▼
                                                    Nhảy thẳng sang new_function()!
```

### Chi tiết thao tác sửa thanh ghi Instruction Pointer (IP Modify)

Handler của Livepatch được đăng ký với ftrace bằng hai cờ đặc biệt: `FTRACE_OPS_FL_IPMODIFY` và `FTRACE_OPS_FL_SAVE_REGS`.

Khi `klp_ftrace_handler()` được gọi:
1. Nó tra cứu cấu trúc `struct klp_func` tương ứng với hàm bị vá.
2. Kiểm tra `current->patch_state` của Task hiện tại.
3. **Nếu `patch_state == 1` (Task đã được patched):** Handler thực hiện câu lệnh ghi đè thanh ghi con trỏ lệnh CPU:
   ```c
   regs->ip = (unsigned long)func->new_func;
   ```
   Khi ftrace trampoline kết thúc và phát lệnh `ret` / `iret`, CPU đọc thanh ghi `%rip` và nhảy thẳng tới byte đầu tiên của `new_func()`. Hàm `old_function()` không được thực thi dù chỉ 1 lệnh!
4. **Nếu `patch_state == 0` (Task chưa được patched):** Handler không sửa thanh ghi `regs->ip`, CPU quay lại thực thi tiếp `old_function()`.

```text
                  CƠ CHẾ REDIRECT TRONG KLP_FTRACE_HANDLER
                                      │
                                      ▼
                      Caller gọi hàm old_function()
                                      │
                                      ▼
                      Nhảy vào klp_ftrace_handler()
                                      │
                                      ▼
                  Kiểm tra patch_state của Task hiện tại
                                      │
               ┌──────────────────────┴──────────────────────┐
               ▼                                             ▼
     Task patch_state = 0                          Task patch_state = 1
   (Chưa an toàn / Mã cũ)                        (Đã an toàn / Mã mới)
               │                                             │
               ▼                                             ▼
  Không sửa thanh ghi IP                         Ghi đè thanh ghi IP CPU:
  (Trả luồng về chạy old_function)               pt_regs->ip = (unsigned long)new_function
               │                                             │
               ▼                                             ▼
       Thực thi old_function()                        Thực thi new_function()!
                                                  (Bỏ qua 100% mã của old_function)
```

---

### Các câu hỏi kỹ thuật cốt lõi về Function Redirect:

#### 1. Hàm cũ (`old_function`) có bị xóa khỏi bộ nhớ RAM không?
- **Không!** Trong suốt quá trình chuyển đổi (**Transition Phase**), cả `old_function` và `new_function` bắt buộc phải **cùng tồn tại đồng thời trong RAM**. Lý do: các Task mang `patch_state = 0` vẫn cần gọi `old_function` cho đến khi chúng đạt điểm Safe State.

#### 2. Vì sao Livepatch thay đổi ở cấp độ toàn bộ hàm (Function Granularity)?
- Vì ftrace ngắt cuộc gọi hàm ngay tại điểm **Function Entry Site** (trước khi hàm cũ kịp tạo Stack Frame hay thay đổi các thanh ghi tham số). Do đó, đơn vị thay thế tự nhiên và an toàn nhất là **nguyên cả hàm (Whole Function Replacement)** chứ không thể sửa lẻ vài câu lệnh ở giữa hàm.

#### 3. Điều gì xảy ra khi nạp nhiều bản vá chồng lên nhau (Patch Stacking)?
- KLP Core quản lý một danh sách liên kết (Stack) các bản vá cho cùng một hàm. Hàm thuộc livepatch module nạp sau cùng sẽ nằm ở đầu Stack ftrace và được ưu tiên thực thi.

---

## 4. So sánh ftrace vs kprobes vs eBPF trong bài toán Livepatch

| Tiêu chí | Dynamic ftrace | kprobes | eBPF (`fentry` / `fexit`) |
|---|---|---|---|
| **Vị trí Hook** | **Function Entry** (Đầu hàm) | Bất kỳ vị trí lệnh nào trong Kernel | Function Entry / Exit |
| **Cơ chế Hook** | NOP 5-byte replacement (`__fentry__`) | Breakpoint Exception (`int3` / `brk`) | ftrace trampoline / BPF JIT |
| **Khả năng IP Modify** | ✅ **Rất cao & An toàn** (via `FTRACE_OPS_FL_IPMODIFY`) | ❌ Không thiết kế để thay đổi toàn bộ hàm | ❌ Chủ yếu dùng cho Tracing / Filtering |
| **Overhead khi OFF** | **Gần như bằng 0** (Chỉ là NOP bytes) | Nhỏ (Chỉ thay đổi khi probe active) | Gần như bằng 0 |
| **Mục đích phù hợp** | **Live Kernel Patching (KLP)** | Dynamic Debugging / Troubleshooting | Monitoring, Tracing & Networking (XDP) |

> **Vì sao Livepatch chọn ftrace?** Vì ftrace can thiệp ở **Function Entry Site trước khi hàm cũ kịp thay đổi Stack Frame hay tham số thanh ghi**, giúp việc chuyển hướng luồng sang `new_function()` diễn ra an toàn tuyệt đối.

---

## 5. Sự phối hợp giữa ftrace Redirect Engine và Consistency Engine

Một hiểu lầm phổ biến là: *"Bật Livepatch là ftrace tự động ép tất cả cuộc gọi hàm sang mã mới"*.

Thực tế, **ftrace Redirect Engine** và **Consistency Engine** phối hợp chặt chẽ với nhau:

```text
                  CẶP ĐÔI PHỐI HỢP TRONG LIVEPATCH
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       ftrace Redirect Engine            Consistency Engine
         "Chạy đường nào?"               "Task nào được phép chạy?"
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
              Luồng thực thi an toàn theo từng Task
```

- **ftrace** trả lời câu hỏi: *"Nếu Task được phép dùng code mới, địa chỉ `new_function` nằm ở đâu?"*
- **Consistency Engine** trả lời câu hỏi: *"Task A hiện tại đã đạt điểm Safe State để nhận `patch_state = 1` hay chưa?"*

### Luồng phối hợp hoàn chỉnh từ khi `kpatch load`:

```text
 kpatch load patch.ko
       │
       ▼
 KLP Core đăng ký hàm thay thế với ftrace
       │
       ▼
 ftrace handler được gắn vào Function Entry (`FTRACE_OPS_FL_IPMODIFY`)
       │
       ▼
 KLP thiết lập cờ `transition = 1`
       │
       ▼
 Mọi cuộc gọi hàm đi qua ftrace: Task state = 0 -> chạy old_func | Task state = 1 -> chạy new_func
       │
       ▼
 Tất cả các Task hội tụ về state = 1
       │
       ▼
 KLP thiết lập cờ `transition = 0` (PATCH ACTIVE HOÀN TOÀN)
```

---

## 6. Lệnh kiểm tra ftrace support trên hệ thống

```bash
# 1. Kiểm tra cờ cấu hình Kernel hỗ trợ ftrace và livepatch
cat /boot/config-$(uname -r) | grep -E \
'CONFIG_FUNCTION_TRACER|CONFIG_DYNAMIC_FTRACE|CONFIG_LIVEPATCH'

# 2. Kiểm tra thư mục giao diện tracefs trong Kernel
mount | grep tracefs
ls -la /sys/kernel/tracing
```

---

## 7. Tài liệu tham khảo

- [Linux Kernel ftrace Documentation](https://docs.kernel.org/trace/ftrace.html)
- [Using ftrace to hook functions](https://docs.kernel.org/trace/ftrace-uses.html)
- [Linux Kernel Livepatch Architecture](https://docs.kernel.org/livepatch/livepatch.html)
