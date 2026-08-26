# 01 – Bài toán và tổng quan về kpatch

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [Bài toán, ràng buộc và yêu cầu kỹ thuật](#1-bài-toán-ràng-buộc-và-yêu-cầu-kỹ-thuật)
3. [Kpatch là gì và nằm ở đâu trong hệ sinh thái livepatch](#2-kpatch-là-gì-và-nằm-ở-đâu-trong-hệ-sinh-thái-livepatch)
4. [Phạm vi sử dụng, giới hạn và loại bản vá phù hợp](#3-phạm-vi-sử-dụng-giới-hạn-và-loại-bản-vá-phù-hợp)
5. [Lựa chọn vận hành và tiêu chí đánh giá công cụ](#4-lựa-chọn-vận-hành-và-tiêu-chí-đánh-giá-công-cụ)
6. [Tài liệu tham khảo](#5-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **VM** | Virtual Machine | Máy ảo chạy trên hypervisor / compute host chứa workload của người dùng. |
| **SLO** | Service Level Objective | Mục tiêu mức độ dịch vụ và cam kết thời gian hoạt động liên tục (uptime/availability). |

## Từ bài toán vận hành đến lựa chọn kpatch

```text
Compute host đang chạy nhiều VM
              |
        Kernel có CVE
              |
      +-------+--------+
      |                |
      v                v
Migrate + reboot    Live kernel patch
      |                |
      |             kpatch
      |                |
      v                v
Kernel sạch mới    Thay function khi
nhưng có chi phí   kernel vẫn chạy
vận hành/downtime      |
                       v
            phải giữ consistency
            + có rollback/fallback
```
> Reboot ưu tiên tính đơn giản, trạng thái sạch và phạm vi cập nhật đầy đủ nhưng phải đánh đổi availability và chi phí vận hành. Livepatch ưu tiên availability bằng cách thay đổi code kernel khi hệ thống vẫn chạy, nhưng phải đánh đổi bằng complexity, yêu cầu compatibility nghiêm ngặt, giới hạn loại thay đổi có thể áp dụng và rủi ro transition.
## 1. Bài toán, ràng buộc và yêu cầu kỹ thuật

**Bài toán gốc: kernel cần vá nhưng workload không được dừng**

Kernel Linux là lớp điều khiển tài nguyên cốt lõi: CPU scheduling, memory, filesystem, networking, device driver và virtualization. Khi kernel có CVE hoặc bug nghiêm trọng, cách truyền thống là:

```text
cài kernel mới
    ↓
reboot host
    ↓
boot kernel mới hoàn toàn
```

Cách này đơn giản về consistency: code cũ biến mất sau reboot, data structures được khởi tạo lại theo kernel mới. Nhưng trên một **compute host chứa nhiều VM**, reboot có nghĩa phải:

```text
evacuate / live-migrate VM
        hoặc
chấp nhận downtime của VM
```

Trong cloud, điều này kéo theo băng thông migration, thời gian orchestration, rủi ro migration failure và cửa sổ bảo trì.

**Problem statement**

> Làm sao áp một security/bug fix vào **kernel đang chạy**, không reboot host, không restart process/VM, nhưng vẫn giữ được consistency của kernel?

---

**Vì sao “thay code đang chạy” là bài toán khó**

Ứng dụng user-space có thể restart một process khi deploy. Kernel thì khác:

- hàng nghìn task/context có thể đang ở kernel;
- interrupt có thể xảy ra bất kỳ lúc nào;
- kernel thread có vòng lặp dài;
- cùng một function có thể được gọi đồng thời trên nhiều CPU;
- một function có thể giữ lock hoặc thay đổi shared state;
- một thay đổi nhỏ ở source có thể kéo theo nhiều thay đổi binary do inline/optimization.

Do đó không thể tư duy đơn giản:

```text
“copy code mới đè lên code cũ”
```

Bài toán thực tế là **code replacement + consistency + lifecycle management**.

---

**Yêu cầu của một giải pháp livepatch tốt**

Một hệ thống livepatch production phải thỏa nhiều mục tiêu đồng thời:

1. **Security** – fix phải thật sự chặn lỗ hổng.
2. **Consistency** – task không được rơi vào trạng thái nửa logic cũ/nửa logic mới nguy hiểm.
3. **Availability** – không reboot trong successful path.
4. **Compatibility** – artifact phải đúng kernel/ABI/toolchain target.
5. **Observability** – biết patch đang enabled, transitioning hay stalled.
6. **Recoverability** – có reverse/unload/fallback.
7. **Auditability** – biết patch nào, function nào, host nào, thời điểm nào.

---

## 2. Kpatch là gì và nằm ở đâu trong hệ sinh thái livepatch

**Kpatch là gì?**

Kpatch là bộ công cụ live kernel patching được khởi đầu tại Red Hat. Nó cho phép tạo và quản lý các **livepatch kernel module** để thay thế implementation của một số kernel function mà không cần reboot.

Ba thành phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| `kpatch-build` | Chuyển source diff thành livepatch `.ko` bằng cách build/so sánh object binary. |
| Livepatch module `.ko` | Chứa function mới, metadata và relocation để đăng ký với Linux livepatch core. |
| `kpatch` CLI | `load`, `unload`, `list`, `info`, `install`, `signal`... |

Mental model:

```text
source fix
  ↓
kpatch-build
  ↓
livepatch.ko
  ↓
kpatch load
  ↓
Linux livepatch core
  ↓
ftrace redirect
  ↓
new function executes
```

---

**Lịch sử và vị trí của kpatch**

Live kernel patching từng có nhiều hướng tiếp cận, trong đó kpatch (Red Hat) và kGraft (SUSE) đóng góp vào consistency model của upstream Linux livepatch. Ngày nay cần phân biệt rõ:

```text
kpatch = toolchain
Linux Livepatch/KLP = upstream kernel infrastructure
ftrace = runtime function tracing/redirect infrastructure
```

Linux livepatch upstream sử dụng per-task consistency kết hợp nhiều cách xác định safe switching point như stack checking và kernel-exit switching.

---

**Trạng thái dự án năm 2026**

Repository chính thức của kpatch thông báo dự án **maintenance mode bắt đầu từ Linux 6.19**. `kpatch-build` đang được thay thế dần bởi `klp-build` upstream.

Điều này không làm mất giá trị của kpatch đối với:

- kernel cũ hơn 6.19;
- distro/vendor vẫn đang dùng kpatch tooling;
- học cơ chế Linux livepatch;
- các môi trường hiện hữu như kernel 6.8 của bộ lab.

Production design mới phải theo dõi hướng `klp-build` và vendor support matrix.

---

## 3. Phạm vi sử dụng, giới hạn và loại bản vá phù hợp

**Kpatch không phải là gì?**

**Không phải full kernel upgrade**

Kpatch làm việc ở function granularity. Nó không biến kernel đang chạy thành một kernel release hoàn toàn khác.

**Không phải cơ chế vá mọi CVE**

Fix đổi struct layout, ABI, init semantics, static keys hoặc data lifetime có thể không phù hợp hoặc cần thiết kế livepatch chuyên biệt.

**Không tự động đảm bảo zero downtime**

Kpatch tránh reboot trong đường thành công, nhưng transition có thể stall, patch có thể bị từ chối hoặc operator có thể phải fallback sang migration/reboot.

**Không thay thế human review**

Patch Author Guide của kpatch nhấn mạnh build success không đủ để khẳng định an toàn. Mỗi patch phải được phân tích semantic.

---

**Kpatch phù hợp nhất với loại fix nào?**

Thường thuận lợi:

- thêm bounds check;
- sửa NULL dereference;
- sửa kiểm tra permission;
- thay calculation cục bộ;
- sửa logic trong một vài function mà không đổi ABI/data lifetime.

Cần phân tích sâu:

- struct layout;
- data semantic shared giữa old/new function;
- lock ordering;
- inline function;
- jump labels/static calls;
- module init/hardware init;
- function prototype/exported ABI.

---

## 4. Lựa chọn vận hành và tiêu chí đánh giá công cụ

**So sánh quyết định vận hành**

| Phương án | Reboot | Migration | Patch scope | Consistency baseline |
|---|---:|---:|---|---|
| Normal kernel update | Có | Có thể | Toàn kernel | Rất rõ sau reboot |
| Live migrate + reboot | Có | Có | Toàn kernel | Rất rõ |
| kpatch/livepatch | Không trong successful path | Không bắt buộc | Function-level | Phải quản lý transition |

Không có phương án “luôn tốt nhất”. Livepatch là trade-off giữa uptime và độ phức tạp engineering.

---

**Definition of Done khi nghiên cứu một công cụ như kpatch**

Không dừng ở “cài được và chạy lệnh”. Cần trả lời được:

```text
WHY      – bài toán gì?
WHAT     – component nào?
HOW      – cơ chế runtime/build?
INPUT    – material nào bắt buộc?
OUTPUT   – artifact gì?
LIMIT    – patch nào không được?
OBSERVE  – biết nó đang làm gì bằng gì?
FAIL     – fail ở đâu?
RECOVER  – rollback/fallback thế nào?
PROD     – audit/rollout/canary ra sao?
```

Đó cũng là cấu trúc của toàn bộ Knowledge Base này.

---

## 5. Tài liệu tham khảo

- https://github.com/dynup/kpatch
- https://github.com/dynup/kpatch/blob/master/doc/patch-author-guide.md
- https://docs.kernel.org/livepatch/livepatch.html
