# 05 – Transition, Safe State và Per-Task Consistency: Cơ chế hội tụ an toàn

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [Bức tranh tổng thể: Vấn đề nhất quán dữ liệu (Data Consistency Problem)](#1-bức-tranh-tổng-thể-vấn-đề-nhất-quán-dữ-liệu-data-consistency-problem)
3. [Per-Task Consistency Model – Mô hình chuyển đổi theo từng Task](#2-per-task-consistency-model--mô-hình-chuyển-đổi-theo-từng-task)
4. [Safe State và 3 cơ chế kiểm tra điểm chuyển đổi an toàn](#3-safe-state-và-3-cơ-chế-kiểm-tra-điểm-chuyển-đổi-an-toàn)
5. [Stalled Transition – Nguyên nhân tắc nghẽn và cách xử lý](#4-stalled-transition--nguyên-nhân-tắc-nghẽn-và-cách-xử-lý)
6. [Reverse Transition vs Force Transition – Cơ chế và Rủi ro](#5-reverse-transition-vs-force-transition--cơ-chế-và-rủi-ro)
7. [Mental Model & Checklist chẩn đoán sự cố Transition](#6-mental-model--checklist-chẩn-đoán-sự-cố-transition)
8. [Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **Per-Task Consistency** | Hybrid Consistency Model (Mô hình nhất quán theo từng Task) | Mô hình chuyển đổi trạng thái patch độc lập trên từng process/thread, đảm bảo mỗi task chỉ thấy một view duy nhất. |
| **TIF_PATCH_PENDING** | Thread Information Flag (Cờ báo hiệu patch đang chờ) | Cờ trong `task_struct->flags` đánh dấu task đang ở giữa quá trình transition chưa đạt Safe State. |
| **Safe State** | Safe Transition Point (Điểm chuyển đổi an toàn) | Trạng thái trong luồng thực thi mà tại đó task có thể chuyển đổi `patch_state` mà không làm hỏng dữ liệu. |
| **ORC Unwinder** | Oops Rewind Capability Unwinder (Bộ giải mã Callstack ORC) | Cơ chế unwind callstack đáng tin cậy trên x86_64 (`CONFIG_UNWINDER_ORC`) phục vụ kiểm tra stack an toàn. |
| **Kernel-Exit** | Kernel to User Transition (Ranh giới thoát khỏi Kernel về Userspace) | Điểm chuyển đổi khi task hoàn tất syscall/IRQ/signal handler và chuẩn bị quay về Userspace. |
| **Stall** | Transition Stall (Tắc nghẽn chuyển đổi) | Hiện tượng quá trình transition bị kéo dài do có task chưa đạt Safe State. |

---

## 1. Bức tranh tổng thể: Vấn đề nhất quán dữ liệu (Data Consistency Problem)

Giả sử một bản vá lỗi thay đổi logic của hàm `foo()` và cấu trúc dữ liệu liên quan. Tại thời điểm người vận hành kích hoạt bản vá:

```text
CPU 0: Task A đang thực thi dở ở giữa mã của foo_old()
CPU 1: Task B vừa hoàn tất syscall và chuẩn bị gọi foo()
```

Nếu ép **Global Switch (Chuyển đổi toàn hệ thống tức thì)**:
- Task A tiếp tục thực thi mã cũ nhưng các hàm con (nested functions) được gọi ở đoạn sau lại nhảy sang thực thi mã mới.
- Kết quả: Task A rơi vào trạng thái "nửa cũ - nửa mới" (Inconsistent State), dẫn tới sai lệch dữ liệu, vi phạm điều kiện khóa (locking violation) hoặc gây Kernel Panic!

```text
            VẤN ĐỀ NẾU ÉP GLOBAL SWITCH TỨC THÌ (KHÔNG CÓ CONSISTENCY)
            
  Task A ───> [foo_old() đang chạy] ───> (Ép chuyển đổi giữa chừng!) ───> [bar_new()] ───> ERRROR / PANIC!
```

---

## 2. Per-Task Consistency Model – Mô hình chuyển đổi theo từng Task

Để giải quyết triệt để rủi ro trên, Linux Livepatch Core (KLP) áp dụng **Per-Task Consistency Model (Mô hình nhất quán theo từng tiến trình)** do Red Hat và SUSE đề xuất.

### Nguyên lý hoạt động:
1. Mỗi tiến trình/thread (`task_struct`) trong Kernel mang một thuộc tính riêng tên là **`patch_state`**:
   - `patch_state = 0`: Task đang sử dụng phiên bản mã cũ (**Unpatched**).
   - `patch_state = 1`: Task đã chuyển sang sử dụng phiên bản mã mới (**Patched**).
2. Trong quá trình chuyển đổi (**Transition Phase**), Task A và Task B có thể tạm thời mang hai `patch_state` khác nhau, nhưng **mỗi Task đều nhìn thấy một góc nhìn mã nhất quán (Consistency View)** theo đúng trạng thái của chính nó.

```text
               QUÁ TRÌNH HỘI TỤ CHUYỂN ĐỔI (PATCHING TRANSITION)

  Trạng thái ban đầu:         sysfs: enabled=1, transition=1           Sysfs: enabled=1, transition=0
  (Chưa kích hoạt)            (Quá trình chuyển đổi đang diễn ra)      (Hoàn tất hội tụ)

  Task A: state=0 ──────────> Task A: state=1 (Đạt safe point) ───────> Task A: state=1
  Task B: state=0 ──────────> Task B: state=0 (Chưa safe point) ──────> Task B: state=1 (Đạt safe point)
  Task C: state=0 ──────────> Task C: state=1 (Đạt safe point) ───────> Task C: state=1

                              (Các task dần dần chuyển trạng thái)     (Tất cả task đã hội tụ = 1)
```

### Hai chiều chuyển đổi (Transition Directions):
- **Patching Transition (0 → 1):** Chuyển từ mã cũ sang mã mới (`sysfs: enabled=1, transition=1`). Mục tiêu hội tụ là toàn bộ các Task chuyển sang `state = 1`. Khi hoàn tất, cờ chuyển về `transition = 0`.
- **Unpatching Transition (1 → 0):** Khi gỡ bản vá (`kpatch unload` / `sysfs: enabled=0, transition=1`). Mục tiêu hội tụ là toàn bộ các Task quay về `state = 0`. When complete, patch module is unregistered.

---

## 3. Safe State và 3 cơ chế kiểm tra điểm chuyển đổi an toàn

### Safe State là gì?

> **Safe State (Trạng thái an toàn)** không phải là "dừng Task", mà là điểm trong luồng thực thi mà tại đó Task không nằm trong bất kỳ hàm bị vá nào (cả hàm cũ và hàm mới), giúp Task chuyển đổi `patch_state` an toàn.

Khi bắt đầu transition, KLP Core thiết lập cờ **`TIF_PATCH_PENDING`** trong `task_struct->flags` cho tất cả các task. Kernel sử dụng 3 cơ chế chính để chuyển đổi trạng thái của task:

```text
                         3 CƠ CHẾ CHUYỂN ĐỔI SAFE STATE
                                       │
     ┌─────────────────────────────────┼─────────────────────────────────┐
     ▼                                 ▼                                 ▼
 1. Reliable Stack Checking    2. Kernel-Exit Switching          3. Idle Loop Patch Points
 (Dành cho Sleeping Tasks)     (Dành cho Running/User Tasks)     (Dành cho Idle/Swapper Threads)
```

### 1. Reliable Stack Checking (Sleeping Tasks)
- **Áp dụng cho:** Các Task đang ở trạng thái ngủ (`TASK_INTERRUPTIBLE` / `TASK_UNINTERRUPTIBLE`).
- **Cơ chế:** KLP Core sử dụng bộ giải mã Callstack đáng tin cậy (**ORC Unwinder** `CONFIG_UNWINDER_ORC` trên x86_64) để duyệt qua danh sách hàm trên Stack (`klp_check_stack()`).
- **Điều kiện:** Nếu **KHÔNG CÓ** bất kỳ hàm bị vá nào nằm trong Callstack, Kernel xóa cờ `TIF_PATCH_PENDING` và cập nhật `patch_state = target`.

### 2. Kernel-Exit Switching (Running / Userspace Tasks)
- **Áp dụng cho:** Các Task đang thực thi chương trình người dùng ở Userspace hoặc đang gọi System Calls.
- **Cơ chế:** Khi Task hoàn tất System Call, xử lý ngắt (IRQ) hoặc xử lý Tín hiệu (Signal) và chuẩn bị quay trở lại Userspace (`exit_to_user_mode_prepare()`), Kernel kiểm tra cờ `TIF_PATCH_PENDING`.
- **Điều kiện:** Tại ranh giới Kernel-Exit, Task hoàn toàn không còn mã Kernel nào trên Stack. Kernel tự động cập nhật `patch_state = target`.

### 3. Idle Task & Kernel Threads Update
- **Áp dụng cho:** Tiến trình nhàn rỗi (`swapper/idle`) và các Kernel Threads hệ thống không bao giờ thoát về Userspace.
- **Cơ chế:** Livepatch chèn các điểm kiểm tra chủ động (`klp_update_patch_state(current)`) bên trong vòng lặp Idle (`cpu_idle_loop`).

---

## 4. Stalled Transition – Nguyên nhân tắc nghẽn và cách xử lý

### Tại sao Transition lại bị tắc nghẽn (Stall)?

Hiện tượng **Transition Stall** xảy ra khi cờ `sysfs` báo `transition = 1` kéo dài bất thường.

```text
    Task X kẹt trong vòng lặp long-running
    hoặc liên tục gọi lại hàm bị vá
                  │
                  ▼
    Không bao giờ đạt điểm Kernel-Exit
    hoặc Callstack luôn chứa hàm bị vá
                  │
                  ▼
    cờ TIF_PATCH_PENDING không thể xóa
                  │
                  ▼
    Quá trình Transition bị tắc nghẽn (STALL)!
```

### Phương pháp theo dõi và xác định Task bị kẹt (Observability):

```bash
# 1. Kiểm tra trạng thái transition chung
cat /sys/kernel/livepatch/<patch_name>/transition

# 2. Quét tìm các Task chưa đạt target state (ví dụ target = 1)
for f in /proc/*/task/*/patch_state; do
  [ -r "$f" ] || continue
  state=$(cat "$f")
  if [ "$state" -eq 0 ]; then
    echo "Task kẹt: $f | patch_state=$state"
  fi
done

# 3. Kiểm tra Callstack của Task bị kẹt
sudo cat /proc/<PID>/task/<TID>/stack
```

### Cơ chế gỡ kẹt bằng Signal Kick (`klp_send_signals` / `kpatch signal`)
Khi một Task (ví dụ: QEMU vCPU thread) kẹt trong vòng lặp `KVM_RUN` không chịu thoát ra, Livepatch core hoặc câu lệnh `kpatch signal` sẽ gửi một tín hiệu giả (**Fake Signal** `SIGWINCH`). Tín hiệu này ngắt syscall `KVM_RUN`, ép vCPU thread quay về ranh giới **Kernel-Exit**, giúp cờ `TIF_PATCH_PENDING` được kiểm tra và cập nhật `patch_state = target` thành công!

---

## 5. Reverse Transition vs Force Transition – Cơ chế và Rủi ro

Khi một transition bị stall kéo dài hoặc phát hiện bản vá có lỗi, người vận hành có 2 lựa chọn xử lý:

```text
                         CÁC PHƯƠNG ÁN XỬ LÝ KHI TRANSITION STALL
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    ▼                                               ▼
         Reverse Transition (Hủy bỏ an toàn)             Force Transition (Cưỡng bức)
  • Đảo ngược target: `enabled = 0`.               • Ghi đè `transition = 0` bằng tay (`echo 1 > sysfs/force`).
  • Chờ các Task quay về `state = 0` an toàn.      • Bỏ qua kiểm tra Safe State / Stack.
  • Được khuyến nghị sử dụng.                      • ⚠️ RỦI RO CAO: Bắt buộc Reboot sau đó!
```

> **Cảnh báo Kỹ thuật về `force`:** Việc ép cờ `force = 1` có thể làm cho một số Task đang thực thi dở bị nhảy giữa hai phiên bản mã, gây hỏng bộ nhớ ẩn (Silent Corruption). Chuẩn vận hành Enterprise yêu cầu phải lên kế hoạch Reboot máy chủ ngay sau khi dùng `force`.

---

## 6. Mental Model & Checklist chẩn đoán sự cố Transition

### Mô hình tư duy 1 dòng (Mental Model):

```text
Function Redirect = "Mã mới nằm ở đâu?"
Patch State       = "Task này được phép chạy mã nào?"
Transition        = "Các Task đang trong quá trình hội tụ"
Safe State        = "Thời điểm Task được phép đổi Patch State an toàn"
Transition Stall  = "Có ít nhất 1 Task chưa chịu rời khỏi hàm bị vá"
```

### Checklist chẩn đoán sự cố cho Sysadmin / SRE:

```text
[ ] Kiểm tra chiều chuyển đổi: Patching (0 -> 1) hay Unpatching (1 -> 0)?
[ ] Xác định chính xác PID/TID của các Task chưa hội tụ.
[ ] Kiểm tra Callstack của TID bị kẹt qua /proc/<PID>/task/<TID>/stack.
[ ] Workload có thể tạm thời giảm tải (Quiesce) để giải phóng stack không?
[ ] Đã thử kích hoạt Fake Signal (`kpatch signal` / `klp_send_signals`) chưa?
[ ] Có nên chọn Reverse Transition (`enabled = 0`) thay vì dùng Force không?
```

---

## 7. Tài liệu tham khảo

- [Linux Kernel Livepatch Consistency Model](https://docs.kernel.org/livepatch/livepatch.html#consistency-model)
- [Reliable Stacktrace in Linux Kernel](https://docs.kernel.org/livepatch/reliable-stacktrace.html)
- [System Call Exit & Kernel Transition Points](https://docs.kernel.org/x86/entry.html)
