# 03 – `kpatch-build` và giải phẫu livepatch module: Từ file patch nguồn đến gói hàng .ko

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [Bức tranh tổng thể của quy trình biên dịch livepatch](#1-bức-tranh-tổng-thể-của-quy-trình-biên-dịch-livepatch)
3. [Đầu vào bắt buộc – "Nguyên liệu" để tái sản xuất nhị phân](#2-đầu-vào-bắt-buộc--nguyên-liệu-để-tái-sản-xuất-nhị-phân)
4. [Vì sao phải biên dịch hai phiên bản? (Baseline vs Patched)](#3-vì-sao-phải-biên-dịch-hai-phiên-bản-baseline-vs-patched)
5. [create-diff-object – "Trái tim" trích xuất sự khác biệt nhị phân](#4-create-diff-object--trái-tim-trích-xuất-sự-khác-biệt-nhị-phân)
6. [Giải phẫu file livepatch .ko – "Gói hàng" hoàn chỉnh chứa những gì?](#5-giải-phẫu-file-livepatch-ko--gói-hàng-hoàn-chỉnh-chứa-những-gì)
7. [Các bẫy patchability – Khi biên dịch thành công chưa chắc đã an toàn](#6-các-bẫy-patchability--khi-biên-dịch-thành-công-chưa-chắc-đã-an-toàn)
8. [Quy trình kiểm tra (Audit) file .ko trước khi nạp](#7-quy-trình-kiểm-tra-audit-file-ko-trước-khi-nạp)
9. [Tóm tắt lệnh tối thiểu & Mindset ghi nhớ](#8-tóm-tắt-lệnh-tối-thiểu--mindset-ghi-nhớ)
10. [Tài liệu tham khảo](#9-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **create-diff-object** | Create Diff Object Tool | Công cụ phân tích ELF nhị phân cốt lõi so sánh original `.o` và patched `.o` để trích xuất hàm bị thay đổi. |
| **-ffunction-sections** | GCC/Clang Compiler Flag | Cờ biên dịch ép đặt mỗi function vào một ELF section `.text.<func>` riêng biệt phục vụ so sánh hàm lẻ. |
| **vmlinux** | Unstripped Kernel Binary | Image kernel chưa bị xóa ký hiệu (unstripped) chứa DWARF debuginfo dùng để phân tích địa chỉ và relocation. |
| **Jump Labels / Static Keys** | Dynamic Code Patching Feature | Cơ chế tự sửa mã máy runtime (nop/jmp) tối ưu hiệu năng nhánh điều kiện của Linux kernel. |
| **Shadow Variables** | Livepatch Shadow Memory API | Cơ chế liên kết dữ liệu mới vào một object đang tồn tại trong RAM mà không thay đổi bố cục (layout) của struct. |

---

## 1. Bức tranh tổng thể của quy trình biên dịch livepatch

Tạo ra một livepatch module **không phải** là việc biên dịch file nguồn đơn thuần (`gcc -c patch.c`). Đây là một **bài toán tái sản xuất sự khác biệt nhị phân (Reproducible Binary Comparison Problem)**.

Hãy hình dung `kpatch-build` là một dây chuyền tự động:

```text
                  NGUYÊN LIỆU ĐẦU VÀO
   (patch.diff + kernel source + .config + vmlinux + compiler)
                         │
                         ▼
             ┌──────────────────────┐
             │ BUILD Baseline (.o)  │  <-- Phiên bản gốc chưa vá
             └───────────┬──────────┘
                         │
                   Apply patch.diff
                         │
                         ▼
             ┌──────────────────────┐
             │  BUILD Patched (.o)  │  <-- Phiên bản đã sửa code
             └───────────┬──────────┘
                         │
                         ▼
             ┌──────────────────────┐
             │  create-diff-object  │  <-- So sánh nhị phân trích
             │   (Binary Diffing)   │      xát duy nhất hàm đổi
             └───────────┬──────────┘
                         │
                         ▼
             ┌──────────────────────┐
             │  LIVEPATCH MODULE    │  <-- Gói hàng .ko chuẩn
             │    (patch-name.ko)   │      KLP metadata
             └──────────────────────┘
```

---

## 2. Đầu vào bắt buộc – "Nguyên liệu" để tái sản xuất nhị phân

Để `kpatch-build` tạo ra một livepatch module an toàn và khớp 100% với kernel đang chạy, bạn phải cung cấp chính xác 5 "nguyên liệu" đầu vào:

| Nguyên liệu | Tên file / Thành phần | Vì sao bắt buộc phải chuẩn xác tuyệt đối? |
|---|---|---|
| **1. Source Patch** | `fix.patch` | File mô tả các thay đổi mã nguồn C (semantic fix). |
| **2. Kernel Source** | `linux-source-<ver>` | Mã nguồn kernel trùng khớp chính xác với phiên bản target. |
| **3. Kernel Config** | `.config` (`/boot/config-*`) | Cấu hình kernel quyết định các nhánh code, layout struct và cờ ftrace. |
| **4. vmlinux Debug** | `vmlinux` (unstripped) | File binary nén gốc chứa bảng ký hiệu DWARF và offset ô nhớ của kernel target. |
| **5. Toolchain** | `gcc` / `binutils` | Compiler trùng phiên bản với compiler đã build kernel gốc để tránh sai lệch mã máy giả. |

> **Lưu ý quan trọng:** Nếu dùng kernel distro (như Ubuntu/RHEL), bạn không thể lấy mã nguồn upstream ngẫu nhiên. Phải dùng đúng gói nguồn và file `vmlinux` debug tương ứng với `uname -r` của host.

---

## 3. Vì sao phải biên dịch hai phiên bản? (Baseline vs Patched)

Đây là nguyên lý cốt lõi nhất của `kpatch-build`. Để hiểu vì sao bắt buộc phải biên dịch 2 lần, hãy phân tích vấn đề từ gốc:

---

### Vấn đề "Nếu chỉ biên dịch 1 lần" (Single Build Problem)

Giả sử bạn chỉ áp dụng file patch vào mã nguồn rồi chạy `make` biên dịch 1 lần duy nhất để lấy file `patched.o`. Sau đó bạn đem `patched.o` đi so sánh với file nhị phân gốc lấy từ kernel đang chạy trên máy chủ.

Bạn sẽ gặp ngay rắc rối lớn: **Xuất hiện hàng nghìn điểm khác biệt nhị phân giả!**

Những khác biệt giả (nhiễu nhị phân - binary noise) này đến từ:
- Phiên bản GCC / Clang lệch một vài bản vá nhỏ.
- Cờ tối ưu hóa của compiler (`-O2`, `-O3`) sắp xếp địa chỉ thanh ghi ngẫu nhiên.
- Thời gian biên dịch (timestamp) và đường dẫn thư mục build (build path string) được nhúng vào file `.o`.
- Các macro mở rộng (`#define`) hoặc file header chung bị thay đổi phụ thuộc môi trường.

Nếu chỉ có `patched.o`, công cụ **không thể phân biệt được**: *Điểm khác biệt nhị phân nào là do bản vá `fix.patch` tạo ra, và điểm khác biệt nào là do nhiễu môi trường biên dịch (build environment drift)!*

---

### Nguyên lý Triệt tiêu Nhiễu Môi trường (Environment Noise Cancellation)

Để giải quyết triệt để vấn đề trên, `kpatch-build` áp dụng nguyên lý triệt tiêu nhiễu bằng cách biên dịch **cả hai phiên bản trong CÙNG MỘT MÔI TRƯỜNG BIÊN DỊCH DUY NHẤT**:

```text
                  CÙNG MỘT MÔI TRƯỜNG BUILD (SAME TOOLCHAIN & ENVIRONMENT)
                                             │
               ┌─────────────────────────────┴─────────────────────────────┐
               ▼                                                           ▼
     Mã nguồn GỐC (Unpatched)                                Mã nguồn MỚI (Patched)
               │                                                           │
        Biên dịch lần 1                                             Biên dịch lần 2
               │                                                           │
               ▼                                                           ▼
          original.o                                                   patched.o
   (Mang nhiễu môi trường K)                                  (Mang nhiễu môi trường K
                                                               + Mã máy do patch)
               │                                                           │
               └─────────────────────────────┬─────────────────────────────┘
                                             ▼
                                SO SÁNH NHỊ PHÂN (patched.o - original.o)
                                             │
                                             ▼
                                Nhiễu môi trường K bị TRIỆT TIÊU!
                                Chỉ còn lại: MÃ MÁY DO FIX.PATCH
```

Vì cả `original.o` và `patched.o` cùng được sinh ra bởi một compiler, một tập cờ biên dịch và một timestamp context, nên **mọi nhiễu môi trường sẽ tác động giống hệt nhau lên cả hai file và bị triệt tiêu hoàn toàn khi làm phép trừ nhị phân**.

Bất kỳ byte mã máy nào còn khác nhau giữa `original.o` và `patched.o` **chắc chắn 100% xuất phát từ `fix.patch`**.

---

### Quy trình 2 bước chi tiết của `kpatch-build`

```text
Original Source ───────── Compile (Lần 1) ────────> original.o  (Baseline)
       │
       └── Apply fix.patch ──> Patched Source ─── Compile (Lần 2) ──> patched.o  (Patched)

                                    original.o vs patched.o
                                              │
                                              ▼ (So sánh nhị phân ELF)
                                      create-diff-object
                                              │
                                              ▼
                                     Trích xuất Changed Functions
```

1. **Bước 1 (Baseline Build - `original.o`)**: 
   - `kpatch-build` gọi `make` biên dịch mã nguồn kernel nguyên bản (chưa áp dụng patch).
   - Các file object `.o` sinh ra được lưu trữ lại làm mốc đối chứng nhị phân chuẩn.

2. **Bước 2 (Patched Build - `patched.o`)**:
   - `kpatch-build` thực thi lệnh `patch -p1 < fix.patch` để sửa mã nguồn C.
   - Gọi `make` lần thứ hai. Compiler sẽ biên dịch lại các file `.c` chịu ảnh hưởng của bản vá, tạo ra các file `.o` mới đã chứa fix.

Hai file `.o` này sau đó được chuyển giao cho công cụ **`create-diff-object`** để tiến hành mổ xẻ nhị phân ở cấp độ hàm.

---

### Ví dụ thực tế trực quan (Minh họa lọc nhị phân)

Giả sử file mã nguồn `mmu.c` chứa **50 hàm**. Bạn tạo một file `fix.patch` chỉ thêm đúng **1 dòng check NULL** vào hàm `kvm_mmu_zap_page()`:

- Khi `kpatch-build` biên dịch 2 lần:
  - 49 hàm không bị đụng tới trong `mmu.c` sẽ sinh ra mã nhị phân **giống hệt nhau 100%** giữa `original.o` và `patched.o`.
  - Duy nhất 1 hàm `kvm_mmu_zap_page()` có mã nhị phân khác biệt.
- Công cụ `create-diff-object` so sánh `original.o` và `patched.o`:
  - Nó lập tức **loại bỏ mã máy của 49 hàm trùng lặp**.
  - Nó **chỉ trích xuất duy nhất 1 hàm `kvm_mmu_zap_page()` đã sửa** để đưa vào gói `livepatch.ko`.

**Kết quả**: Kích thước file livepatch module cực kỳ nhỏ gọn (chỉ vài KB thay vì hàng trăm MB của toàn bộ kernel), an toàn và hoàn toàn loại bỏ được rủi ro mang mã thừa vào kernel đang chạy.

---

## 4. create-diff-object – "Trái tim" trích xuất sự khác biệt nhị phân

### Vai trò của cờ `-ffunction-sections` và `-fdata-sections`

Mặc định, compiler nhồi tất cả các hàm trong một file C vào chung một khối section `.text`. 

Để so sánh được từng hàm lẻ, `kpatch-build` ép compiler bật hai cờ:
- `-ffunction-sections`: Đưa mỗi hàm vào một section ELF riêng biệt (ví dụ: `.text.kvm_mmu_page_fault`).
- `-fdata-sections`: Đưa mỗi biến toàn cục vào một section dữ liệu riêng biệt.

### Cách `create-diff-object` làm việc

```text
  original.o (chứa .text.foo, .text.bar)
                     +
   patched.o (chứa .text.foo, .text.bar_modified)
                     │
                     ▼
             create-diff-object
                     │
    • Bỏ qua các section giống nhau hoàn toàn (.text.foo)
    • Giữ lại section bị thay đổi (.text.bar_modified)
    • Phát hiện các hàm helper mới thêm vào
    • Kiểm tra quy tắc an toàn (Jump labels, inline callers)
    • Tự động tạo bảng hiệu chỉnh địa chỉ động (.klp.rela.*)
                     │
                     ▼
             Output: ELF object chỉ chứa hàm đổi
```

### Quy tắc vàng: Changed Function ≠ Changed Line

Một thay đổi chỉ **1 dòng code C** trong file header có thể khiến:
- Hàng loạt hàm `inline` trong nhiều file `.o` bị thay đổi mã máy.
- Compiler thay đổi cách phân bổ thanh ghi (register allocation) của hàm gọi nó (caller).

Do đó, danh sách **Changed Functions** do `create-diff-object` phát hiện ra mới là **phạm vi thay đổi nhị phân thực sự** sẽ được đưa vào livepatch module.

---

## 5. Giải phẫu file livepatch `.ko` – "Gói hàng" hoàn chỉnh chứa những gì?

Sau khi `create-diff-object` lọc ra các hàm bị thay đổi, `kpatch-build` đóng gói tất cả thành file kernel module `.ko`.

Cấu trúc bên trong một file `livepatch.ko`:

```text
┌────────────────────────────────────────────────────────┐
│               livepatch-module.ko                      │
├────────────────────────────────────────────────────────┤
│  1. MÃ MÁY HÀM MỚI (New Code Sections)                 │
│     .text.foo_patched()  (Mã máy mới của hàm foo)      │
│     .text.bar_helper()   (Hàm bổ trợ mới thêm vào)     │
│                                                        │
│  2. METADATA CHỈ ĐỊNH (KLP Metadata)                   │
│     .kpatch.funcs   (Danh sách hàm cần thay + offset)  │
│     .kpatch.strings (Tên hàm & object owner: vmlinux)  │
│                                                        │
│  3. BẢNG HIỆU CHỈNH ĐỊA CHỈ (Dynamic Relocations)      │
│     .klp.rela.vmlinux.text.foo_patched                 │
│     (Chỉ định địa chỉ cho các ký hiệu nội bộ/static)   │
│                                                        │
│  4. KIỂM TRA TƯƠNG THÍCH (Compatibility Data)          │
│     __versions & vermagic (Chuỗi kiểm tra phiên bản)   │
└────────────────────────────────────────────────────────┘
```

### Giải thích các section cốt lõi:
- **`.kpatch.funcs`**: Chứa mảng cấu trúc khai báo cho KLP: *"Hàm cũ X nằm trong object Y sẽ được thay thế bằng hàm mới Z tại địa chỉ này"*.
- **`.klp.rela.<obj>.<sec>`**: Chứa danh sách các relocation dành riêng cho các hàm static/non-exported. Khi nạp module, KLP Core dùng bảng này để điền chính xác địa chỉ các biến/hàm nội bộ của kernel vào mã máy hàm mới.
- **`vermagic`**: Chuỗi metadata mã hóa phiên bản kernel (ví dụ: `6.8.0-134-generic`). Nếu `vermagic` của module khác với `uname -r` của hệ thống đang chạy, Module Loader sẽ ném lỗi từ chối nạp.

---

## 6. Các bẫy patchability – Khi biên dịch thành công chưa chắc đã an toàn

Lệnh `kpatch-build` báo `SUCCESS` chỉ có nghĩa là: **Tool đã đóng gói thành công file nhị phân**. Nó **KHÔNG** đảm bảo bản vá an toàn 100% khi chạy thực tế!

Người phát triển bản vá phải lưu ý 4 bẫy phổ biến:

### 1. Bẫy Jump Labels / Static Keys
- **Hiện tượng**: Biên dịch thất bại với lỗi `Found unsupported jump labels...`.
- **Nguyên nhân**: Mã nguồn sử dụng cơ chế `static_branch_likely()` tự sửa mã máy runtime (jump label). Kpatch-build chặn lỗi này vì mã máy nhảy trong module mới không thể tự động đồng bộ trạng thái với jump label gốc của kernel.
- **Giải pháp**: Thay thế bằng kiểm tra biến thông thường (`static_key_enabled()`).

### 2. Bẫy Inline Function
- **Hiện tượng**: Sửa 1 hàm `static inline` nhưng danh sách hàm bị thay đổi kéo theo hàng chục hàm khác.
- **Giải pháp**: Phải review lại toàn bộ danh sách changed functions để đảm bảo không bỏ sót caller nào.

### 3. Bẫy Thay đổi Cấu trúc Dữ liệu (Struct Layout Change)
- **Hiện tượng nguy hiểm nhất**: Thêm một trường dữ liệu mới vào `struct` C:
  ```c
  struct vcpu {
      int id;
  +   u64 new_metric;  // THÊM TRƯỜNG MỚI!
  };
  ```
- **Hậu quả**: Các object `struct vcpu` đã được cấp phát trong RAM trước khi nạp patch vẫn mang kích thước cũ. Hàm mới truy cập vào `new_metric` sẽ ghi đè lên vùng nhớ lân cận (Memory Corruption / Kernel Panic)!
- **Giải pháp**: Không được sửa struct layout trực tiếp. Sử dụng **Shadow Variables (`klp_shadow_alloc` / `klp_shadow_get`)** để gán thêm dữ liệu phụ vào object đang chạy.

### 4. Bẫy Hàm Khởi tạo (`__init`)
- Các hàm mang thuộc tính `__init` đã bị kernel giải phóng bộ nhớ (free) ngay sau khi boot xong. Việc cố gắng vá các hàm `__init` sẽ thất bại hoặc không có hiệu lực.

---

## 7. Quy trình kiểm tra (Audit) file `.ko` trước khi nạp

Trước khi chạy lệnh `kpatch load`, luôn thực hiện 5 bước audit file nhị phân:

```text
┌────────────────────────────────────────────────────────┐
│               CHECKLIST AUDIT ARTIFACT                 │
├────────────────────────────────────────────────────────┤
│ [ ] 1. Kiểm tra sự tồn tại & kích thước file .ko       │
│ [ ] 2. Đối chiếu vermagic với `uname -r` của host     │
│ [ ] 3. Kiểm tra danh sách changed functions            │
│ [ ] 4. Kiểm tra sự tồn tại của section .klp.rela       │
│ [ ] 5. Xác nhận không có lỗi Jump Label / Static Key   │
└────────────────────────────────────────────────────────┘
```

---

## 8. Tóm tắt lệnh tối thiểu & Mindset ghi nhớ

### Tập lệnh vận hành biên dịch & kiểm tra

```bash
# 1. Kiểm tra thử patch nguồn xem có apply sạch không
patch -p1 --dry-run < fix.patch

# 2. Biên dịch livepatch module với kpatch-build
MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic' \
kpatch-build \
  -a 6.8.0-134-generic \
  -s /path/to/kernel-source \
  -c /boot/config-$(uname -r) \
  -v /path/to/vmlinux \
  -n my-first-patch \
  fix.patch

# 3. Kiểm tra metadata tương thích của file .ko tạo ra
modinfo -F vermagic my-first-patch.ko
uname -r

# 4. Kiểm tra các section livepatch trong ELF
readelf -SW my-first-patch.ko | grep -E 'kpatch|klp|__versions'
```

### Mindset ghi nhớ cốt lõi

> **`kpatch-build` không chỉ là một công cụ compile; nó là một "Patchability Gate" kiểm tra tính an toàn nhị phân trước khi cho phép bản vá tiến vào kernel đang chạy.**

---

## 9. Tài liệu tham khảo

- [kpatch-build source code & documentation](https://github.com/dynup/kpatch/tree/master/kpatch-build)
- [kpatch Patch Author Guide](https://github.com/dynup/kpatch/blob/master/doc/patch-author-guide.md)
- [Linux Livepatch Module Layout & Relocations](https://docs.kernel.org/livepatch/module-elf-format.html)
