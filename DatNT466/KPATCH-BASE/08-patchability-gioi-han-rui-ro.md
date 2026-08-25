# 08 – Patchability, giới hạn và rủi ro

## Mục lục

1. [1. Khung đánh giá patchability từ source đến runtime](#1-khung-đánh-giá-patchability-từ-source-đến-runtime)
2. [2. Các thay đổi có nguy cơ cao hoặc thường không phù hợp](#2-các-thay-đổi-có-nguy-cơ-cao-hoặc-thường-không-phù-hợp)
3. [3. Cơ chế nâng cao: callbacks, shadow data và patch stacking](#3-cơ-chế-nâng-cao-callbacks-shadow-data-và-patch-stacking)
4. [4. Rủi ro vận hành và cách hiểu đúng zero downtime](#4-rủi-ro-vận-hành-và-cách-hiểu-đúng-zero-downtime)
5. [5. Go/No-Go gate trước khi triển khai](#5-gono-go-gate-trước-khi-triển-khai)
6. [6. Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

## Khung quyết định patchability

```text
               SOURCE FIX
                   |
                   v
        Có biểu diễn bằng function
          replacement an toàn?
              /           \
            Có             Không
            |                |
            v                v
   Data semantics       NO-GO / redesign
   có tương thích?
       /      \
     Có        Không
     |           |
     v           v
 Binary/runtime     callback/shadow data
 kiểm tra được?     hoặc maintenance path
     |
     v
 staging + stress + transition test
     |
     v
        GO / NO-GO DECISION
```

## 1. Khung đánh giá patchability từ source đến runtime

**Câu hỏi quan trọng nhất trước khi build**

> **Fix này có thể được biểu diễn an toàn bằng function replacement trong một kernel đang có live state hay không?**

Đây là câu hỏi semantic, không phải chỉ syntax/build.

---

**Patchability assessment framework**

**Layer A – Source change**

- đổi function nào?
- thêm helper nào?
- đổi header/inline không?
- đổi struct không?

**Layer B – Data semantics**

- old/new code có đọc cùng data theo cùng nghĩa không?
- lifecycle của object có thay đổi không?
- lock/invariant có đổi không?

**Layer C – Binary reality**

- kpatch-build phát hiện function nào?
- có unexpected changes không?
- có static key/jump label/special sections không?

**Layer D – Runtime consistency**

- old/new task state cùng tồn tại có an toàn không?
- function có nằm trên long-running stack/hot path không?

---

**Thường thuận lợi**

| Loại fix | Vì sao dễ hơn |
|---|---|
| Bounds/NULL check | Thay logic cục bộ. |
| Permission validation | Thường không đổi data layout. |
| Local calculation | Function replacement đủ biểu diễn fix. |
| Error-path fix | Ít state migration. |
| Helper mới + caller changed | Có thể đóng gói helper trong module. |

---

## 2. Các thay đổi có nguy cơ cao hoặc thường không phù hợp

**Struct layout change**

```c
struct session {
  int state;
+ u64 generation;
};
```

Object đã tồn tại trước patch không tự tăng kích thước trong RAM.

New code đọc `generation` có thể đọc garbage/out-of-bounds.

→ No-go mặc định, trừ khi redesign patch bằng shadow variable/callback hoặc cơ chế khác đã phân tích kỹ.

---

**Data semantic change**

Nguy hiểm ngay cả khi struct không đổi.

Ví dụ field `state` cũ nghĩa A/B, code mới đổi semantics thành A/B/C. Task old và new cùng truy cập object có thể hiểu khác nhau.

Build có thể vẫn `SUCCESS`, nên đây là pitfall cần human reasoning.

---

**Prototype / ABI change**

Nếu function signature đổi, caller đã compile sẵn theo ABI cũ.

Không nên coi whole-function redirect là giải pháp tự động cho ABI mismatch.

---

**Init code**

Fix ở module/device initialization có thể không có tác dụng đầy đủ nếu init đã chạy từ boot/load trước đó.

Function replacement không “replay” initialization state.

---

**Inline function**

Inline code đã được copy vào caller. Patch helper inline có thể làm nhiều caller đổi binary.

Phải audit changed function list.

---

**Assembly / `notrace` / ftrace limitations**

Livepatch dựa trên ftrace function entry, nên function không traceable theo required model là no-go hoặc cần architecture-specific solution.

---

**Static keys / jump labels / static calls**

Đây là code runtime-specialized. Kpatch Patch Author Guide có hướng dẫn riêng vì copy binary patched function sang module có thể không phản ánh runtime static-key state.

Lab đã gặp exact build gate này ở `kvm_arch_vcpu_ioctl_run()`.

---

**Locking change**

Nếu patch thay lock order hoặc chia critical section thành semantics mới, old/new task cùng tồn tại có thể tạo deadlock/invariant mismatch.

Cần vẽ lock graph trước/sau patch.

---

**Shared tables / per-CPU data / hardware state**

Function replacement không tự cập nhật data đã khởi tạo ở runtime. Các fix thay register programming hoặc table schema cần callback/reinit strategy.

---

## 3. Cơ chế nâng cao: callbacks, shadow data và patch stacking

**Shadow Variables (`klp_shadow_*`)**:
Để khắc phục hạn chế không được làm thay đổi `struct` layout trong RAM, Linux Livepatch cung cấp API **Shadow Variables**:
- `klp_shadow_alloc(obj, id, size, gfp_flags, ctor, data)`: Động gán một vùng nhớ mới (shadow memory) với một object cũ đã tồn tại trong RAM dựa trên con trỏ `obj` và identifier `id`.
- `klp_shadow_get(obj, id)`: Trả về con trỏ tới vùng nhớ shadow tương ứng với `obj`.
- `klp_shadow_free(obj, id, dtor)`: Giải phóng vùng nhớ shadow khi object bị destroy.

**Lifecycle Callbacks**:
Kpatch cung cấp các macro đăng ký callback để thực thi logic chuẩn bị hoặc dọn dẹp bộ nhớ trước/sau khi nạp hoặc gỡ patch:
- `pre_patch`: Chạy trước khi đăng ký/kích hoạt patch (ví dụ: khởi tạo shadow variables, kiểm tra điều kiện phần cứng).
- `post_patch`: Chạy ngay sau khi transition hoàn tất (`transition = 0`).
- `pre_unpatch` / `post_unpatch`: Chạy tương ứng khi tiến hành disable/unload patch.

---

**Patch stacking và cumulative patch**

Nhiều livepatch chồng nhau làm reasoning khó hơn. Kpatch guide khuyến nghị patch mới nên cumulative/superset khi hệ thống đã được patched, tận dụng replace behavior khi phù hợp.

---

## 4. Rủi ro vận hành và cách hiểu đúng zero downtime

**Build success chưa đủ**

Ba lớp review bắt buộc:

```text
1. Source review
2. Binary/livepatch review
3. Runtime validation
```

---

**Định nghĩa “zero downtime” có trách nhiệm**

Nên nói:

> Không reboot host và không quan sát service interruption vượt quá độ phân giải phép đo trong successful transition.

Không nên nói:

> Kpatch đảm bảo mọi patch có downtime bằng 0 tuyệt đối.

---

**Risk matrix**

| Risk | Xác suất | Impact | Mitigation |
|---|---|---|---|
| Wrong target kernel | Trung bình | Cao | exact source/vmlinux/vermagic gate |
| Semantic data mismatch | Thấp–TB | Rất cao | human review/callback/shadow design |
| Transition stall | TB | TB–cao | monitor + quiesce/signal/reverse |
| Kernel panic | Thấp | Rất cao | staging/canary/rollback |
| Patch stacking complexity | TB theo thời gian | Cao | cumulative patch + reboot debt policy |
| Unsigned artifact | TB ở lab | Policy-dependent | signing/trust pipeline |

---

## 5. Go/No-Go gate trước khi triển khai

**Go / No-Go checklist**

**GO candidate**

```text
[ ] localized function logic
[ ] no incompatible struct layout change
[ ] no incompatible ABI change
[ ] old/new semantics can coexist
[ ] changed function list understood
[ ] runtime path testable
[ ] rollback/fallback exists
```

**NO-GO / escalation**

```text
[ ] unclear data migration
[ ] hardware re-init required
[ ] unsupported jump-label/static-call issue unresolved
[ ] critical locking semantics unclear
[ ] patch touches ftrace/livepatch internals unsafely
[ ] target binary cannot be reproduced/matched
```

---

## 6. Tài liệu tham khảo

- https://github.com/dynup/kpatch/blob/master/doc/patch-author-guide.md
- https://docs.kernel.org/livepatch/livepatch.html
- https://docs.kernel.org/livepatch/api.html
