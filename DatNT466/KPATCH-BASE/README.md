# KPATCH KNOWLEDGE BASE

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [1. Cách đọc và bản đồ bộ tài liệu](#1-cách-đọc-và-bản-đồ-bộ-tài-liệu)
3. [2. Các khái niệm cốt lõi cần phân biệt](#2-các-khái-niệm-cốt-lõi-cần-phân-biệt)
4. [3. Liên hệ với 5 lab thực hành](#3-liên-hệ-với-5-lab-thực-hành)
5. [4. Trạng thái dự án và quy ước sử dụng tài liệu](#4-trạng-thái-dự-án-và-quy-ước-sử-dụng-tài-liệu)
6. [5. Tài liệu tham khảo](#5-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **kpatch** | kpatch Tooling | Bộ công cụ do Red Hat phát triển để tạo và quản lý bản vá livepatch kernel mà không cần reboot. |
| **KLP** | Kernel Livepatching | Subsystem / Engine chính thức trong upstream Linux kernel quản lý vòng đời và tính nhất quán của bản vá. |
| **ftrace** | Function Tracer | Hạ tầng tracing và dynamic hooking trong Linux kernel được KLP dùng để điều hướng lệnh gọi hàm. |
| **QEMU** | Quick Emulator | Trình giả lập phần cứng và quản lý máy ảo chạy ở không gian người dùng (userspace). |
| **KVM** | Kernel-based Virtual Machine | Subsystem ảo hóa phần cứng trực tiếp trong Linux kernel. |
| **CVE** | Common Vulnerabilities and Exposures | Danh mục mã định danh chuẩn hóa các lỗ hổng bảo mật. |
| **ABI** | Application Binary Interface | Giao diện nhị phân quy định cách các module/function giao tiếp ở cấp độ mã máy. |
| **CLI** | Command Line Interface | Giao diện điều khiển bằng dòng lệnh (`kpatch`, `kpatch-build`). |


## Sơ đồ kiến thức tổng thể

```text
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

## 1. Danh sách tài liệu

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
kpatch = tooling: build + CLI + helper

Linux livepatch (KLP) = infrastructure trong kernel: patch object/function, transition, consistency

ftrace = hạ tầng tracing/hooking động được livepatch dùng để đổi hướng tại đầu hàm
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


> **Kpatch nhận một source diff, build và phân tích binary để tạo livepatch module chứa các function thay thế; module đăng ký với Linux livepatch core, livepatch dùng ftrace để redirect function entry, đồng thời dùng consistency model theo từng task để chuyển old→new code an toàn mà không reboot kernel.**

---

## 4. Trạng thái dự án và quy ước sử dụng tài liệu

**Trạng thái dự án cần biết (2026)**

Kpatch vẫn rất hữu ích để hiểu và vận hành các kernel đời hiện tại/đời cũ, nhưng upstream project đã thông báo **maintenance mode từ Linux 6.19**(maintenace mode-dự án vẫn được duy trì ở mức sửa lỗi cần thiết, giữ khả năng hoạt động với các hệ thống hiện có), và hướng phát triển mới là `klp-build` trong upstream kernel. Vì vậy cần phân biệt:

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
