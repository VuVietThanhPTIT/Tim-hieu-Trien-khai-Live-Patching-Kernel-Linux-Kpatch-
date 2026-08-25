# KPATCH KNOWLEDGE BASE

## Mục lục

1. [1. Cách đọc và bản đồ bộ tài liệu](#1-cách-đọc-và-bản-đồ-bộ-tài-liệu)
2. [2. Các khái niệm cốt lõi cần phân biệt](#2-các-khái-niệm-cốt-lõi-cần-phân-biệt)
3. [3. Liên hệ với 5 lab thực hành](#3-liên-hệ-với-5-lab-thực-hành)
4. [4. Trạng thái dự án và quy ước sử dụng tài liệu](#4-trạng-thái-dự-án-và-quy-ước-sử-dụng-tài-liệu)
5. [5. Tài liệu tham khảo](#5-tài-liệu-tham-khảo)

> Bộ tài liệu nghiên cứu có hệ thống về **kpatch / Linux livepatch (KLP) / ftrace / QEMU-KVM**, được viết theo cấu trúc “problem → architecture → mechanism → implementation → operation → production”.
>
> Mục tiêu: sau khi đọc xong, người học không chỉ biết chạy `kpatch load`, mà phải giải thích được **vì sao công cụ tồn tại, nó thay code bằng cách nào, điều kiện để patch an toàn, lịch sử từ `stop_machine()` sang per-task consistency model, vì sao transition có thể stall, và cách vận hành trong môi trường KVM compute**.


---

## Sơ đồ kiến thức tổng thể

```text
BÀI TOÁN CLOUD / KERNEL CVE
          |
          v
   SOURCE PATCH / CVE FIX
          |
          v
     kpatch-build
          |
          v
  LIVEPATCH MODULE (.ko)
          |
          v
      kpatch CLI
          |
          v
+-----------------------------+
| Linux kernel đang chạy      |
|  Module loader              |
|       |                     |
|       v                     |
|  Livepatch Core (KLP)       |
|       |                     |
|       v                     |
|  ftrace redirect            |
|       |                     |
|       v                     |
|  patched kernel functions   |
+-----------------------------+
          |
          v
 transition / safe state / per-task consistency
          |
          v
      vận hành + recovery
```

## 1. Cách đọc và bản đồ bộ tài liệu

**Cách đọc bộ tài liệu**

```text
WHY?
  ↓
01. Bài toán & tổng quan
  ↓
WHAT IS INSIDE?
  ↓
02. Kiến trúc
  ↓
HOW IS A PATCH BUILT?
  ↓
03. kpatch-build + .ko
  ↓
HOW DOES EXECUTION GET REDIRECTED?
  ↓
04. ftrace
  ↓
HOW DOES THE KERNEL STAY CONSISTENT?
  ↓
05. transition / safe state / per-task consistency
  ↓
WHERE DOES KVM FIT?
  ↓
06. QEMU / KVM / KVM_RUN / MMU
  ↓
HOW DO I USE IT?
  ↓
07. cài đặt / build / load / unload
  ↓
CAN THIS FIX BE LIVE-PATCHED?
  ↓
08. patchability / giới hạn / rủi ro
  ↓
WHAT IF IT STALLS OR FAILS?
  ↓
09. observability / troubleshooting / recovery
  ↓
HOW SHOULD A CLOUD TEAM OPERATE IT?
  ↓
10. production design / audit / best practices
```

---

**Danh sách tài liệu**

| File | Câu hỏi chính |
|---|---|
| [01-bai-toan-va-tong-quan-kpatch.md](01-bai-toan-va-tong-quan-kpatch.md) | Vì sao cần kpatch? Kpatch là gì và không phải gì? |
| [02-kien-truc-kpatch.md](02-kien-truc-kpatch.md) | Các layer và component bên trong phối hợp thế nào? |
| [03-kpatch-build-va-livepatch-module.md](03-kpatch-build-va-livepatch-module.md) | Source diff biến thành `.ko` bằng cách nào? |
| [04-ftrace-va-co-che-function-redirect.md](04-ftrace-va-co-che-function-redirect.md) | Code cũ được redirect sang code mới thế nào? |
| [05-transition-safe-state-per-task-consistency.md](05-transition-safe-state-per-task-consistency.md) | Vì sao old/new code có thể cùng tồn tại nhưng vẫn nhất quán? |
| [06-kvm-qemu-va-duong-thuc-thi-kernel.md](06-kvm-qemu-va-duong-thuc-thi-kernel.md) | QEMU/KVM/KVM_RUN/MMU liên quan livepatch ra sao? |
| [07-cai-dat-build-va-su-dung-kpatch.md](07-cai-dat-build-va-su-dung-kpatch.md) | Cài, build, kiểm tra, load/unload như thế nào? |
| [08-patchability-gioi-han-rui-ro.md](08-patchability-gioi-han-rui-ro.md) | Patch nào nên/không nên livepatch? |
| [09-observability-troubleshooting-recovery.md](09-observability-troubleshooting-recovery.md) | Theo dõi và xử lý transition stall thế nào? |
| [10-production-design-best-practices-audit.md](10-production-design-best-practices-audit.md) | Đưa livepatch vào quy trình cloud production ra sao? |

---

## 2. Các khái niệm cốt lõi cần phân biệt

**Phân biệt 3 khái niệm dễ nhầm**

```text
kpatch
= tooling: build + CLI + helper

Linux livepatch (KLP)
= infrastructure trong kernel: patch object/function, transition, consistency

ftrace
= hạ tầng tracing/hooking động được livepatch dùng để đổi hướng tại đầu hàm
```

Nói ngắn gọn:

```text
kpatch       = bộ công cụ (kpatch-build CLI, create-diff-object)
KLP          = “engine” trong kernel (đăng ký patch, chuyển đổi per-task, quản lý sysfs)
ftrace       = cơ chế function-entry redirect nền tảng (dùng IP-modify callback)
```

**Sự tiến hóa về mô hình nhất quán (Consistency Model)**:
- **Kpatch ban đầu (2014)**: Sử dụng `stop_machine()` để tạm dừng tất cả các CPU trên hệ thống, kiểm tra callstack của từng task, rồi swap pointer hàm ngay lập tức. Cơ chế này gây ra độ trễ (latency spike) ngắn cho toàn hệ thống.
- **Upstream Linux Livepatch / KLP (từ Linux 4.14+)**: Thay thế hoàn toàn `stop_machine()` bằng **Per-Task Consistency Model** (do Red Hat & SUSE hợp tác phát triển). Hệ thống không bị pause toàn bộ; từng task chuyển đổi trạng thái patch (`state 0 → 1`) độc lập tại các điểm safe state (như khi quay lại userspace hoặc qua reliable stack checking). Công cụ `kpatch` hiện đại biên dịch module nhắm trực tiếp vào hạ tầng KLP này.

---

**Một câu mô tả toàn bộ hệ thống**

> **Kpatch nhận một source diff, build và phân tích binary để tạo livepatch module chứa các function thay thế; module đăng ký với Linux livepatch core, livepatch dùng ftrace để redirect function entry, đồng thời dùng consistency model theo từng task để chuyển old→new code an toàn mà không reboot kernel.**

---

## 3. Liên hệ với 5 lab thực hành

**Mapping với 5 lab**

| Lab | Kiến thức cần đối chiếu |
|---|---|
| Lab 1 – KVM host | File 06 + 07 |
| Lab 2 – kpatch-build | File 02 + 03 + 07 + 08 |
| Lab 3 – load khi VM chạy | File 04 + 05 + 06 + 09 |
| Lab 4 – stalled transition | File 05 + 06 + 09 |
| Lab 5 – recovery | File 09 + 10 |

---

## 4. Trạng thái dự án và quy ước sử dụng tài liệu

**Trạng thái dự án cần biết (2026)**

Kpatch vẫn rất hữu ích để hiểu và vận hành các kernel đời hiện tại/đời cũ, nhưng upstream project đã thông báo **maintenance mode từ Linux 6.19**, và hướng phát triển mới là `klp-build` trong upstream kernel. Vì vậy cần phân biệt:

- **Kernel 6.8 trong bộ lab:** tiếp tục dùng kpatch hợp lý.
- **Thiết kế mới cho kernel 6.19+:** cần đánh giá `klp-build` và tooling của distro/vendor.

---

**Quy ước đọc**

- **Mental model:** giải thích dễ nhớ.
- **Audit checkpoint:** thứ cần chứng minh bằng output/log.
- **Pitfall:** lỗi tư duy hoặc lỗi kỹ thuật hay gặp.
- **Production note:** khác biệt giữa lab và hệ thống thật.

---

## 5. Tài liệu tham khảo

1. [kpatch repository / README](https://github.com/dynup/kpatch) — kiến trúc, `kpatch-build`, trạng thái maintenance mode.
2. [kpatch Patch Author Guide](https://github.com/dynup/kpatch/blob/master/doc/patch-author-guide.md) — patchability, data changes, jump labels, callbacks, symbol versioning.
3. [Linux Kernel Livepatch documentation](https://docs.kernel.org/livepatch/livepatch.html) — consistency model, transition, lifecycle, sysfs, force.
4. [Linux Livepatch API](https://docs.kernel.org/livepatch/api.html) — `klp_enable_patch`, objects/functions, callbacks/shadow variables.
5. [Linux ftrace documentation](https://docs.kernel.org/trace/ftrace.html) — dynamic ftrace, function tracing.
6. [Using ftrace to hook functions](https://docs.kernel.org/trace/ftrace-uses.html) — callback và IP-modify.
7. [KVM API](https://docs.kernel.org/virt/kvm/api.html) — `/dev/kvm`, fd/ioctl model, `KVM_RUN`.
8. [Red Hat Enterprise Linux documentation](https://docs.redhat.com/) — vendor/operational context.
