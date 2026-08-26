# 02 – Kiến trúc kpatch – hiểu theo dòng chảy của một bản vá

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [Bức tranh tổng thể](#1-bức-tranh-tổng-thể)
3. [BUILD-TIME – Nhà máy sản xuất livepatch](#2-build-time--nhà-máy-sản-xuất-livepatch)
4. [kpatch-build thực sự làm gì?](#3-kpatch-build-thực-sự-làm-gì)
5. [Livepatch .ko – "Gói hàng" được tạo ra](#4-livepatch-ko--gói-hàng-được-tạo-ra)
6. [RUNTIME – Đưa bản vá vào kernel đang chạy](#5-runtime--đưa-bản-vá-vào-kernel-đang-chạy)
7. [Module Loader – "Bảo vệ cửa vào"](#6-module-loader--bảo-vệ-cửa-vào)
8. [KLP – "Bộ nào" runtime](#7-klp--bộ-não-runtime)
9. [ftrace – "Bộ chuyển hướng"](#8-ftrace--bộ-chuyển-hướng)
10. [Consistency – "Bộ điều phối chuyển đổi"](#9-consistency--bộ-điều-phối-chuyển-đổi)
11. [Ghép tất cả lại thành một kiến trúc duy nhất](#10-ghép-tất-cả-lại-thành-một-kiến-trúc-duy-nhất)
12. [Tài liệu tham khảo](#11-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **ELF** | Executable and Linkable Format | Định dạng chuẩn cho file thực thi, object file và kernel module (`.ko`) trên Linux. |
| **Relocation** | Symbol Relocation | Thao tác nạp/tính toán địa chỉ ô nhớ thực tế cho các ký hiệu hàm/biến khi nạp module. |
| **.klp.rela** | KLP Dynamic Relocation Section | Section ELF đặc biệt trong module livepatch chứa thông tin hiệu chỉnh địa chỉ cho các ký hiệu nội bộ (static/non-exported). |
| **vermagic** | Version Magic | Chuỗi metadata mã hóa phiên bản kernel, compiler và config flags để kiểm tra tính tương thích khi nạp module. |
| **sysfs** | System Filesystem | Virtual filesystem xuất bản giao diện quan sát và điều khiển trạng thái kernel (`/sys/kernel/livepatch`). |

---

## 1. Bức tranh tổng thể

> **kpatch có 2 nửa: một nửa tạo bản vá (Build-time), một nửa đưa bản vá vào kernel đang chạy (Runtime).**

```text
                 KIẾN TRÚC KPATCH
                       │
          ┌────────────┴────────────┐
          │                         │
          ▼                         ▼
     BUILD-TIME                  RUNTIME
   "Tạo bản vá"              "Áp bản vá"
          │                         │
          │                         │
   kpatch-build                kpatch load
          │                         │
          ▼                         ▼
   livepatch.ko             Module Loader
                                    │
                                    ▼
                           Linux Livepatch Core
                              (KLP / bộ nào)
                                    │
                       ┌────────────┴───────────┐
                       │                        │
                       ▼                        ▼
                 ftrace redirect          Consistency
                "chạy code nào?"       "khi nào chuyển?"
                       │                        │
                       └──────────┬─────────────┘
                                  ▼
                           Function mới chạy
```

---

## 2. BUILD-TIME – Nhà máy sản xuất livepatch

Mục tiêu của phía này rất đơn giản:

```text
Security fix / bug fix
          ↓
      patch.diff
          ↓
     kpatch-build
          ↓
   livepatch-module.ko
```

Nhưng `kpatch-build` cần biết **kernel mà chúng ta muốn vá trông chính xác như thế nào trong bộ nhớ nhị phân**.

Vì vậy đầu vào thực tế là:

```text
                  ┌── patch.diff
                  │
                  ├── kernel source
                  │
                  ├── kernel .config
                  │
                  ├── vmlinux + debug info
                  │
                  └── compiler / binutils
                  │
                  ▼
             ┌──────────────┐
             │ kpatch-build │
             └──────┬───────┘
                    │
                    ▼
              livepatch.ko
```

Ví dụ trong môi trường thực hành / lab:

```text
kvm-mmu.patch
       +
linux-source-6.8.0
       +
config-6.8.0-134-kpatch
       +
vmlinux-6.8.0-134-generic
       ↓
   kpatch-build
       ↓
kvm-mmu-livepatch.ko
```

---

## 3. kpatch-build thực sự làm gì?

Đừng hình dung `kpatch-build` đơn giản là compiler chạy `make`.

Nó hoạt động giống một **máy so sánh sự khác biệt nhị phân giữa hai kernel build**:

```text
                Kernel Source
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
     BUILD GỐC             APPLY PATCH
          │                     │
          │                     ▼
          │                BUILD MỚI
          │                     │
          ▼                     ▼
      old objects          new objects
          │                     │
          └──────────┬──────────┘
                     ▼
                  SO SÁNH
                     │
                     ▼
             Function nào đổi?
                     │
                     ▼
           Tạo metadata cần thiết
                     │
                     ▼
              livepatch.ko
```

Quy trình chi tiết của `kpatch-build`:
1. Chuẩn bị source tree và build baseline unpatched.
2. Apply `patch.diff` vào source.
3. Build lại phiên bản patched với cờ `-ffunction-sections` và `-fdata-sections`.
4. So sánh nhị phân giữa old objects và new objects nhờ công cụ helper `create-diff-object`.
5. Xác định các hàm bị thay đổi (changed functions) và các hàm bổ sung mới.
6. Tạo metadata, section relocation động `.klp.rela.*` và link ra file `.ko`.

Ví dụ nếu patch chỉ sửa một hàm `function_A()`, mục tiêu không phải nhét toàn bộ kernel mới vào module, mà chỉ trích xuất đúng mã mới của `function_A()`:

```text
Kernel cũ                       livepatch.ko

function_A_old()  <----------  function_A_new()
function_B()
function_C()
function_D()
...
```

Đây là lý do file module livepatch có kích thước rất nhỏ so với toàn bộ kernel image.

---

## 4. Livepatch `.ko` – "Gói hàng" được tạo ra

Sau khi build hoàn tất, ta nhận được một file artifact kiểu `kvm-mmu-livepatch.ko`.

Nó vẫn là một **kernel module dạng ELF**, nhưng mang cấu trúc đặc biệt chứa mã mới và hướng dẫn ghép nối:

```text
┌───────────────────────────────────┐
│          livepatch.ko             │
├───────────────────────────────────┤
│                                   │
│  CODE MỚI                         │
│  ─────────                        │
│  function_A_new()                 │
│  function_B_new()                 │
│                                   │
├───────────────────────────────────┤
│  METADATA & RELOCATIONS           │
│  ──────────────────────           │
│  function nào cần thay            │
│  function thuộc object nào        │
│  relocation info (.klp.rela.*)    │
│  symbol / version info            │
│                                   │
└───────────────────────────────────┘
```

Trong livepatch artifact, các section ELF quan trọng bao gồm:
- `.kpatch.funcs`: Bảng danh sách các hàm cần thay thế và địa chỉ tương ứng.
- `.kpatch.strings`: Chuỗi tên hàm và tên object owner (`vmlinux`, `kvm.ko`).
- `.klp.rela.<obj>.<sec>`: Section hiệu chỉnh địa chỉ động cho các ký hiệu nội bộ (static/non-exported symbols) của kernel mà module mới cần gọi tới.
- `__versions`: Metadata kiểm tra modversions ABI.

Ghi nhớ ngắn gọn:

> **File `.ko` livepatch = Code mới + Metadata/Relocation chỉ định code mới phải thay cho hàm cũ nào.**

---

## 5. RUNTIME – Đưa bản vá vào kernel đang chạy

Đây là nửa thứ hai của hệ thống.

Khi người vận hành thực thi:

```bash
sudo kpatch load patch.ko
```

Kernel không lập tức "đè" code mới lên RAM. Nó trải qua một chuỗi xử lý phân tầng nghiêm ngặt:

```text
                   patch.ko
                      │
                      ▼
              ┌───────────────┐
              │ Module Loader │
              └───────┬───────┘
                      │
                 "Có load được
                  module không?"
                      │
                      ▼
              ┌───────────────┐
              │ Livepatch Core│
              │      KLP      │
              └───────┬───────┘
                      │
              "Cần thay function
                  nào?"
                      │
            ┌─────────┴──────────┐
            ▼                    ▼
         ftrace              Consistency
     "redirect đâu?"      "chuyển lúc nào?"
            │                    │
            └─────────┬──────────┘
                      ▼
                 CODE MỚI
```

---

## 6. Module Loader – "Bảo vệ cửa vào"

Đây là lớp kiểm duyệt đầu tiên của Linux kernel.

Module Loader không quan tâm bản vá sửa bug KVM hay Filesystem. Nó chỉ đặt câu hỏi:

> **Module này có hợp lệ và đủ điều kiện tương thích để được nạp vào kernel không?**

```text
patch.ko
   │
   ▼
┌────────────────────┐
│   MODULE LOADER    │
├────────────────────┤
│ ELF hợp lệ?        │
│                    │
│ vermagic đúng?     │
│                    │
│ symbols resolve?   │
│                    │
│ modversions?       │
│                    │
│ signature policy?  │
└─────────┬──────────┘
          │
        PASS
          │
          ▼
       KLP Core
```

Các rào cản compatibility tại Module Loader:
- **`vermagic`**: Chuỗi phiên bản kernel (ví dụ: `6.8.0-134-generic SMP preempt`). Nếu module build ra mang `6.8.12` mà host chạy `6.8.0-134-generic`, Module Loader sẽ từ chối nạp ngay lập tức.
- **Symbol Resolution**: Kiểm tra các exported symbol mà module tham chiếu đến.
- **Module Signing**: Kiểm tra chữ ký số của module theo policy của kernel (nếu chưa ký, kernel sẽ log cảnh báo taint hoặc từ chối).

---

## 7. KLP – "Bộ nào" runtime

Đây là điểm quan trọng cần phân biệt rõ:

> **kpatch không tự phát minh toàn bộ cơ chế livepatch bên trong kernel. Linux kernel đã tích hợp sẵn hạ tầng Livepatch Core (KLP) từ bản phát hành Linux 4.14+ (do Red Hat và SUSE đóng góp).**

Mối quan hệ giữa kpatch và KLP:

```text
             USER / OPERATOR
                    │
                    ▼
                 kpatch
            (Tooling CLI)
                    │
════════════════════╪════════════════════
              KERNEL SPACE
                    │
                    ▼
          Linux Livepatch Core
                 (KLP)
           (Engine trong Kernel)
                    │
```

KLP chịu trách nhiệm:
- Quản lý cấu trúc `struct klp_patch` và đối tượng bị vá (`vmlinux`, `kvm.ko`).
- Đăng ký hàm thay thế với ftrace.
- Điều phối trạng thái chuyển đổi (`transition`) của từng task.
- Tạo và xuất bản giao diện quan sát qua `/sys/kernel/livepatch/<patch>/`.

---

### Vì sao KLP đã quản lý livepatch trong kernel nhưng vẫn cần kpatch?

Đây là câu hỏi kiến trúc cốt lõi. Để hiểu rõ, cần phân biệt ranh giới không gian và trách nhiệm:

> **KLP sống BÊN TRONG Kernel Space (Engine thực thi); kpatch sống BÊN NGOÀI Userspace (Bộ công cụ sản xuất & vận hành).**

KLP rất mạnh mẽ ở runtime nhưng **KLP KHÔNG THỂ tự làm 3 việc sau**:

1. **KLP không thể tự TẠO bản vá nhị phân từ source diff (Bài toán Build)**:
   - KLP chỉ là người tiếp nhận file `.ko` đã được đóng gói chuẩn metadata KLP.
   - Nếu không có `kpatch-build` (và helper `create-diff-object`), lập trình viên sẽ phải **tự tay viết code C thủ công** cho từng livepatch module, tự tra địa chỉ symbol nội bộ, tự khai báo cấu trúc `klp_object` / `klp_func`, và tự tính toán mã máy relocation `.klp.rela`. Công việc thủ công này tốn hàng tuần và rất dễ gây kernel panic. `kpatch-build` tự động hóa toàn bộ khâu này chỉ từ file `patch.diff` và `vmlinux`.

2. **KLP không có giao diện CLI vận hành thân thiện cho con người/Automation**:
   - KLP chỉ cung cấp giao diện sysfs cấp thấp (`/sys/kernel/livepatch/`).
   - `kpatch` CLI cung cấp tập lệnh vận hành chuẩn (`kpatch load`, `unload`, `list`, `install`, `signal`), hỗ trợ kiểm tra tương thích pre-flight và tự động gửi signal gỡ stall cho SRE.

3. **KLP không tự quản lý việc duy trì bản vá khi Reboot (Persistence)**:
   - Khi host reboot, KLP trong RAM biến mất hoàn toàn.
   - `kpatch` cung cấp dịch vụ systemd (`kpatch.service`) để tự động nạp lại các bản vá đã `install` ngay khi máy chủ khởi động lại.

**Bảng so sánh phân công trách nhiệm KLP vs kpatch**:

| Tiêu chí | KLP (Linux Livepatch Core) | kpatch (kpatch Tooling) |
|---|---|---|
| **Vị trí** | Inside Kernel Space (Upstream từ Linux 4.14+) | Userspace (Tooling bên ngoài do Red Hat phát triển) |
| **Bản chất** | Engine thực thi & Subsystem hạt nhân | Bộ công cụ tự động hóa biên dịch & CLI vận hành |
| **Khâu tạo bản vá** | ❌ Không biết tạo (Chỉ nhận file `.ko` sẵn có) | ✅ Tự động hóa 100% từ `patch.diff` → `livepatch.ko` nhờ `kpatch-build` |
| **Điều khiển runtime** | Cung cấp giao diện sysfs cấp thấp (`/sys/kernel/livepatch/`) | Cung cấp lệnh CLI thân thiện (`kpatch load`, `unload`, `list`, `install`) |
| **Nhiệm vụ chính** | Trực tiếp điều phối ftrace redirect & per-task transition | Sản xuất artifact nhị phân, kiểm tra compatibility & duy trì boot persistence |

Tóm lại: **`kpatch` là nhà máy sản xuất gói hàng và đội xe giao hàng ở Userspace; `KLP` là ban quản lý điều phối bên trong tòa nhà Kernel Space.**

---

## 8. ftrace – "Bộ chuyển hướng"

Sau khi KLP tiếp nhận bản vá, nó dùng **ftrace** để điều hướng luồng thực thi.

Trước khi patch:

```text
Caller ────> old_function()
```

Sau khi livepatch được enable:

```text
Caller ────> [Function Entry] ────> [ftrace handler] ────> new_function()
```

Hình dung ftrace như một **ngã rẽ giao thông động tại đầu mỗi hàm**:

```text
                 function call
                       │
                       ▼
                    [ftrace]
                    /      \
                   /        \
          chưa patch        đã patch
              │                │
              ▼                ▼
         old_func()        new_func()
```

Khi cuộc gọi hàm diễn ra, ftrace handler (`klp_ftrace_handler`) can thiệp vào thanh ghi con trỏ lệnh Instruction Pointer (`IP modify`), thay đổi địa chỉ trả về để CPU nhảy thẳng sang `new_function()` mà không thực thi `old_function()`.

Đây là lý do livepatch hoạt động theo đơn vị **toàn bộ hàm (function-level replacement)** chứ không phải thay đổi từng dòng code lẻ ở giữa hàm.

---

## 9. Consistency – "Bộ điều phối chuyển đổi"

Đây là phần phức tạp nhất đảm bảo tính an toàn của livepatch.

Giả sử hệ thống đang có 3 task đang chạy:

```text
Task A ───── đang ở giữa old_function() ─────>

Task B ───────── đang chạy trong kernel ──────>

Task C ───── đang ở giữa old_function() ─────>
```

Khi người vận hành kích hoạt patch, kernel **không thể ép tất cả task chuyển sang code mới ngay lập tức**, vì Task A và Task C có thể vi phạm tính nhất quán dữ liệu nếu bị nhảy giữa chừng.

Vì vậy, KLP sử dụng **Per-Task Consistency Model**:

```text
                    ENABLE PATCH
                         │
                         ▼
                  transition = 1
                         │
           ┌─────────────┼─────────────┐
           │             │             │
         Task A        Task B        Task C
           │             │             │
       state = 0     state = 1     state = 0
       (old code)    (new code)    (old code)
           │             │             │
       safe point        │         safe point
           │             │             │
           ▼             │             ▼
       state = 1         │         state = 1
           └─────────────┼─────────────┘
                         ▼
                 tất cả hội tụ
                         │
                         ▼
                  transition = 0
```

Ý nghĩa các trạng thái sysfs:
- **`enabled=1, transition=1`**: Patch đã được kích hoạt, nhưng hệ thống đang trong quá trình chuyển đổi (chưa tất cả các task đạt safe point).
- **`enabled=1, transition=0`**: Tất cả các task đã hội tụ sang `state=1`. Bản vá đã hoàn toàn ổn định.

---

## 10. Ghép tất cả lại thành một kiến trúc duy nhất

Sơ đồ tổng thể toàn bộ luồng hoạt động từ Build-time đến Runtime:

```text
                  KPATCH ARCHITECTURE
                         │
                         │
════════════════ BUILD TIME ═══════════════════

 patch.diff       kernel source       .config
     │                 │                 │
     └────────────┬────┴────────┬────────┘
                  │             │
               vmlinux     compiler/binutils
                  │             │
                  └──────┬──────┘
                         ▼
                 ┌──────────────┐
                 │ kpatch-build │
                 └───────┬──────┘
                         │
              build original kernel
                         │
                  apply source patch
                         │
               build patched kernel
                         │
                  compare objects
                         │
                 changed functions
                         │
                         ▼
              ┌───────────────────┐
              │ livepatch.ko      │
              │                   │
              │ • new functions   │
              │ • metadata        │
              │ • relocations     │
              │ • versions        │
              └─────────┬─────────┘
                        │
                        │ kpatch load
                        ▼

═════════════════ RUNTIME ═════════════════════

                ┌───────────────┐
                │ Module Loader │
                └───────┬───────┘
                        │
                 compatibility OK
                        │
                        ▼
                ┌───────────────┐
                │ Linux KLP Core│
                └───────┬───────┘
                        │
              ┌─────────┴──────────┐
              │                    │
              ▼                    ▼
           ftrace              consistency
         redirect              transition
              │                    │
              └─────────┬──────────┘
                        ▼
                patched function
                        │
                        ▼
                transition = 0
                        │
                        ▼
                 PATCH ACTIVE
```

---

## Tóm tắt vai trò các thành phần trong 1 câu

```text
kpatch-build
    = "TẠO bản vá nhị phân từ source patch"

Module Loader
    = "KIỂM TRA module có đủ điều kiện nạp vào kernel không"

KLP (Linux Livepatch Core)
    = "QUẢN LÝ vòng đời và đối tượng livepatch trong kernel"

ftrace
    = "CHUYỂN HƯỚNG cuộc gọi từ hàm cũ sang hàm mới"

Consistency Engine
    = "QUYẾT ĐỊNH thời điểm chuyển đổi safe-state cho từng task"

sysfs (/sys/kernel/livepatch)
    = "XUẤT BẢN TRẠNG THÁI cho người vận hành quan sát"
```

---

## Checklist kiểm toán kiến trúc

Một reviewer kiến trúc cần kiểm tra:

```text
[ ] Artifact build ra target đúng exact vmlinux và kernel release của host.
[ ] Danh sách changed functions khớp với phạm vi sửa đổi dự kiến của patch.
[ ] Section .klp.rela chứa đầy đủ relocation cho các ký hiệu tĩnh/nội bộ.
[ ] Sysfs entry /sys/kernel/livepatch/<patch> xuất hiện sau kpatch load.
[ ] Trạng thái transition chuyển từ 1 về 0 hoàn tất.
[ ] dmesg không ghi nhận lỗi Oops, BUG hay Kernel Panic.
[ ] Workload/VM tiếp tục vận hành bình thường đáp ứng cam kết SLO.
```

---

## 11. Tài liệu tham khảo

- [kpatch repository](https://github.com/dynup/kpatch)
- [Linux Livepatch API Documentation](https://docs.kernel.org/livepatch/api.html)
- [Linux Kernel Livepatch Architecture](https://docs.kernel.org/livepatch/livepatch.html)
