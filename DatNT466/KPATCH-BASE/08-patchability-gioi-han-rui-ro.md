# 08 – Patchability, Giới hạn Kỹ thuật và Quản trị Rủi ro Livepatch

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [Khung đánh giá patchability từ source đến runtime](#1-khung-đánh-giá-patchability-từ-source-đến-runtime)
3. [Các thay đổi có nguy cơ cao hoặc thường không phù hợp](#2-các-thay-đổi-có-nguy-cơ-cao-hoặc-thường-không-phù-hợp)
4. [Cơ chế nâng cao: callbacks, shadow data và patch stacking](#3-cơ-chế-nâng-cao-callbacks-shadow-data-và-patch-stacking)
5. [Rủi ro vận hành và cách hiểu đúng zero downtime](#4-rủi-ro-vận-hành-và-cách-hiểu-đúng-zero-downtime)
6. [Go/No-Go gate trước khi triển khai](#5-gono-go-gate-trước-khi-triển-khai)
7. [Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **Patchability** | Livepatch Eligibility (Tính khả vá) | Mức độ phù hợp và tính an toàn của một source patch khi chuyển đổi sang dạng livepatch module. |
| **Struct Layout** | Structure Memory Layout (Bố cục bộ nhớ của Struct) | Kích thước và thứ tự sắp xếp các trường dữ liệu trong một cấu trúc C trong RAM. |
| **Lifecycle Callbacks** | Kpatch Hook Callbacks (Hàm lắng nghe vòng đời) | Các hàm callback chạy tại các thời điểm `pre_patch`, `post_patch`, `pre_unpatch`, `post_unpatch`. |
| **ABI Mismatch** | Binary Interface Mismatch (Bất tương thích ABI nhị phân) | Sự không tương thích về chữ ký hàm, kiểu dữ liệu hoặc calling convention giữa các module. |

---

## Khung quyết định patchability

```text
               SOURCE FIX
                   │
                   ▼
        Có biểu diễn bằng function
          replacement an toàn?
              /           \
            Có             Không
            │                │
            ▼                ▼
   Data semantics       NO-GO / redesign
   có tương thích?
       /      \
     Có        Không
     │           │
     ▼           ▼
 Binary/runtime     callback/shadow data
 kiểm tra được?     hoặc maintenance path
     │
     ▼
 staging + stress + transition test
     │
     ▼
        GO / NO-GO DECISION
```

---

## 1. Khung đánh giá patchability từ source đến runtime

### Câu hỏi quan trọng nhất trước khi biên dịch

> **Fix này có thể được biểu diễn một cách an toàn bằng phương pháp Function Replacement trong một Kernel đang có dữ liệu thực thi hay không?**

Đây là câu hỏi về mặt **Data Semantics (Ý nghĩa dữ liệu)** chứ không chỉ đơn thuần là cú pháp biên dịch (`kpatch-build SUCCESS`).

---

### Khung đánh giá phân tầng (Patchability Assessment Framework)

```text
                         KHUNG ĐÁNH GIÁ PATCHABILITY 4 LỚP
                                        │
     ┌──────────────────┬───────────────┴───────────────┬──────────────────┐
     ▼                  ▼                               ▼                  ▼
 Layer A: Source    Layer B: Data Semantics          Layer C: Binary    Layer D: Runtime Consistency
 - Thay đổi hàm nào? - Đọc cùng data không?          - Hàm nào đổi?     - Task cũ/mới cùng tồn tại
 - Đổi struct không? - Lock/invariant có đổi không?  - Có static key?     có an toàn không?
```

- **Layer A (Source Change):** Kiểm tra xem file patch sửa đổi hàm nào, có thêm helper mới nào, có làm thay đổi header hay cấu trúc `struct` C hay không.
- **Layer B (Data Semantics):** Kiểm tra xem mã cũ và mã mới có đọc/ghi dữ liệu theo cùng một ý nghĩa hay không. Thứ tự Lock Ordering có bị thay đổi không.
- **Layer C (Binary Reality):** Kiểm tra kết quả trích xuất của `kpatch-build` (Changed Functions), xác nhận không có các thành phần nhị phân không hỗ trợ như Jump Labels / Static Keys.
- **Layer D (Runtime Consistency):** Kiểm tra sự cùng tồn tại đồng thời của Task mang `state = 0` và Task mang `state = 1` trong giai đoạn Transition.

---

### Các loại bản vá thường dễ chấp nhận (GO Candidates)

| Loại Fix | Vì sao dễ nạp Livepatch hơn? |
|---|---|
| **Bounds / NULL Pointer Check** | Chỉ thay đổi logic kiểm tra điều kiện cục bộ bên trong hàm. |
| **Permission Validation** | Thêm kiểm tra quyền mà không làm thay đổi bố cục dữ liệu (Data Layout). |
| **Local Calculation Fix** | Thay đổi công thức tính toán cục bộ bên trong thân hàm. |
| **Error-Path Fix** | Sửa đường xử lý lỗi không làm ảnh hưởng tới vòng đời của Object. |

---

## 2. Các thay đổi có nguy cơ cao hoặc thường không phù hợp

```text
                           6 BẪY NGUY HIỂM KHI LIVEPATCH
                                         │
    ┌──────────────┬──────────────┼──────────────┬──────────────┬──────────────┐
    ▼              ▼              ▼              ▼              ▼              ▼
1. Struct Layout 2. Data Semantic 3. ABI Change  4. Init Code   5. Static Keys 6. Lock Order
 (Đổi kích thước (Thay đổi ý     (Đổi tham số   (Hàm __init    (Jump Labels   (Đổi thứ tự
  struct C)       nghĩa biến)    hàm gốc)       đã giải phóng) tự sửa mã)     khóa lock)
```

### 1. Struct Layout Change (Thay đổi bố cục cấu trúc C)

```c
struct session {
    int state;
+   u64 generation;  // THÊM TRƯỜNG MỚI!
};
```
- **Hậu quả:** Các Object `struct session` đã được cấp phát trong RAM trước khi nạp patch vẫn mang kích thước cũ. Mã mới đọc/ghi trường `generation` sẽ ghi đè sang vùng nhớ lân cận (Memory Corruption).
- **Quy tắc:** NO-GO mặc định, trừ khi redesign bản vá bằng **Shadow Variables**.

### 2. Data Semantic Change (Thay đổi ý nghĩa dữ liệu)
- **Hậu quả:** Ngay cả khi kích thước `struct` không đổi, việc thay đổi ý nghĩa của biến (ví dụ cờ `state = 1` từ "Pending" đổi thành "Active") sẽ khiến Task chạy mã cũ và Task chạy mã mới trong giai đoạn Transition hiểu sai ý nghĩa dữ liệu của nhau.

### 3. Function Prototype / ABI Change (Thay đổi chữ ký hàm)
- **Hậu quả:** Nếu chữ ký hàm thay đổi (`foo(int)` -> `foo(int, long)`), các hàm gọi (Callers) chưa được vá vẫn truyền tham số theo chuẩn ABI cũ, gây hỏng thanh ghi Stack.

### 4. Initialization Code (`__init` functions)
- **Hậu quả:** Các hàm mang thuộc tính `__init` chỉ thực thi 1 lần lúc boot và bộ nhớ của chúng đã bị giải phóng. Vá các hàm `__init` sẽ không có bất kỳ hiệu lực nào.

### 5. Static Keys / Jump Labels (Tự sửa mã máy runtime)
- **Hậu quả:** Các nhánh điều kiện tối ưu bằng `static_branch_likely()` bị `kpatch-build` chặn lại vì mã nhị phân nhảy không thể tự động đồng bộ với trạng thái `static_key` gốc của Kernel.

### 6. Lock Order Change (Thay đổi thứ tự khóa)
- **Hậu quả:** Thay đổi thứ tự acquire locks giữa các hàm. Trong giai đoạn Transition, một Task giữ Lock A gọi Lock B (mã cũ) gặp Task khác giữ Lock B gọi Lock A (mã mới) sẽ gây ra **Deadlock hệ thống ngay lập tức**.

---

## 3. Cơ chế nâng cao: callbacks, shadow data và patch stacking

### 3.1. Shadow Variables (`klp_shadow_*`)

Để giải quyết hạn chế không được làm thay đổi `struct` layout trong RAM, Linux Livepatch cung cấp API **Shadow Variables**:

- **`klp_shadow_alloc(obj, id, size, gfp_flags, ctor, data)`:** Động gán một vùng nhớ mới (Shadow Memory) với một Object cũ đã tồn tại trong RAM dựa trên con trỏ `obj` và identifier `id`.
- **`klp_shadow_get(obj, id)`:** Trả về con trỏ tới vùng nhớ Shadow tương ứng với `obj`.
- **`klp_shadow_free(obj, id, dtor)`:** Giải phóng vùng nhớ Shadow khi Object bị hủy.

### 3.2. Lifecycle Callbacks (Hàm lắng nghe vòng đời)

Kpatch cung cấp các macro đăng ký callback để thực thi logic chuẩn bị hoặc dọn dẹp bộ nhớ tại các thời điểm nhạy cảm:

- **`pre_patch`:** Chạy trước khi đăng ký/kích hoạt patch (ví dụ: khởi tạo Shadow Variables, kiểm tra điều kiện phần cứng).
- **`post_patch`:** Chạy ngay sau khi transition hoàn tất (`transition = 0`).
- **`pre_unpatch` / `post_unpatch`:** Chạy tương ứng khi tiến hành disable/unload patch.

### 3.3. Patch Stacking và Cumulative Patch Strategy

Khi nạp nhiều Livepatch Modules chồng lên nhau (Patch Stacking), việc theo dõi và kiểm thử trở nên phức tạp. 

Kpatch khuyến nghị chiến lược **Cumulative Patch (Bản vá tổng hợp tích lũy)**: Bản vá mới chứa toàn bộ các fix từ trước tới nay để thay thế hoàn toàn (`replace = 1`) các module patch lẻ cũ.

---

## 4. Rủi ro vận hành và cách hiểu đúng zero downtime

### Định nghĩa "Zero Downtime" có trách nhiệm

> **Tuyên bố chuẩn xác:** Livepatch giúp áp dụng bản vá an ninh mà **không cần Reboot máy chủ Host** và không làm gián đoạn dịch vụ trong điều kiện Transition hội tụ thành công. Livepatch không phải là một phép thuật đảm bảo Downtime bằng 0 tuyệt đối trong mọi tình huống.

### Bảng quản trị rủi ro Livepatch (Risk Matrix)

| Loại rủi ro | Xác suất | Mức độ ảnh hưởng | Biện pháp giảm thiểu (Mitigation) |
|---|---|---|---|
| **Lệch Kernel Target** | Trung bình | **Rất cao** | Phải dùng exact `vmlinux`, `config` và kiểm tra `vermagic`. |
| **Sai lệch Data Semantics** | Thấp | **Cực kỳ cao** | Bắt buộc Human Code Review kỹ lưỡng & dùng Shadow Data. |
| **Transition Stall** | Trung bình | Trung bình | Theo dõi sysfs, dùng Signal Kick hoặc Quiesce Workload. |
| **Kernel Panic** | Thấp | **Cực kỳ cao** | Kiểm thử bắt buộc trên Staging / Canary Deployment. |
| **Phức tạp Patch Stacking** | Trung bình | Cao | Sử dụng Cumulative Patch & chính sách Reboot định kỳ. |

---

## 5. Go/No-Go gate trước khi triển khai

```text
                   CHECKLIST ĐÁNH GIÁ GO / NO-GO PRODUCTION
                                       │
         ┌─────────────────────────────┴─────────────────────────────┐
         ▼                                                           ▼
   TIÊU CHÍ ĐẠT (GO CANDIDATE)                              TIÊU CHÍ CHẶN (NO-GO CRITERIA)
 [ ] Sửa đổi logic hàm cục bộ an toàn.                    [ ] Đổi Struct Layout mà không dùng Shadow.
 [ ] Không làm thay đổi Struct Layout / ABI.              [ ] Thay đổi thứ tự Lock Ordering (Rủi ro Deadlock).
 [ ] Đã Review kỹ lưỡng changed functions.               [ ] Xuất hiện cảnh báo Jump Labels chưa sửa.
 [ ] Quy trình Rollback / Unload đã test tốt.             [ ] Chưa kiểm thử thành công trên Staging VM.
```

---

## 6. Tài liệu tham khảo

- [kpatch Patch Author Guide](https://github.com/dynup/kpatch/blob/master/doc/patch-author-guide.md)
- [Linux Kernel Livepatch Architecture Documentation](https://docs.kernel.org/livepatch/livepatch.html)
- [Linux Livepatch API Documentation](https://docs.kernel.org/livepatch/api.html)
