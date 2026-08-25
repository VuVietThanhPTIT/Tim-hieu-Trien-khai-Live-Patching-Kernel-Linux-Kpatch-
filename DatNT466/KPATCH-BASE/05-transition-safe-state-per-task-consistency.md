# 05 – Transition, safe state và per-task consistency

## Mục lục

1. [1. Consistency model và hai chiều transition](#1-consistency-model-và-hai-chiều-transition)
2. [2. Safe-state và các switching mechanism của kernel livepatch](#2-safe-state-và-các-switching-mechanism-của-kernel-livepatch)
3. [3. Stalled transition, observability và case KVM](#3-stalled-transition-observability-và-case-kvm)
4. [4. Reverse/cancel và force: cơ chế cùng rủi ro](#4-reversecancel-và-force-cơ-chế-cùng-rủi-ro)
5. [5. Mental model và checklist chẩn đoán](#5-mental-model-và-checklist-chẩn-đoán)
6. [6. Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

##  Mô hình transition theo từng task

```text
PATCHING: target = 1

Task A: 0 ---------> 1
Task B: 0 -----> 1
Task C: 0 -----------------> 1
             ^
             |
       transition = 1

Khi tất cả task đã hội tụ:
             |
             v
       transition = 0

UNPATCHING làm ngược lại: 1 -> 0

Một task chỉ đổi state tại điểm kernel cho là an toàn
(stack/switching mechanism phù hợp), không bị ép đổi giữa
một execution context không nhất quán.
```

## 1. Consistency model và hai chiều transition

**Vấn đề consistency**

Giả sử `foo()` thay semantics. Tại thời điểm enable patch:

```text
CPU0: Task A đang ở giữa foo_old()
CPU1: Task B chuẩn bị gọi foo()
```

Nếu ép global switch tức thời, Task A có thể tiếp tục với state cũ nhưng nested call lại dùng semantics mới. Một số patch sẽ phá invariant.

Linux livepatch giải quyết bằng **per-task consistency**.

---

**Per-task consistency là gì?**

Mỗi task có patch state trong transition:

```text
0 = unpatched
1 = patched
```

Task A và Task B có thể tạm thời khác state, nhưng **mỗi task phải nhìn thấy một view nhất quán** theo state của chính nó.

---

**Patching transition**

```text
initial:
Task A = 0
Task B = 0
Task C = 0

transition=1:
Task A = 1
Task B = 0   ← chưa safe
Task C = 1

complete:
Task A = 1
Task B = 1
Task C = 1
transition=0
```

---

**Unpatching transition**

Khi disable/unload:

```text
1 → 0
```

Điểm dễ nhầm:

- patching: `state=0` là task chưa hội tụ;
- unpatching: `state=1` là task chưa hội tụ.

---

**`transition=1` không đồng nghĩa lỗi**

`transition=1` chỉ nói hệ thống đang hội tụ.

Nó đáng điều tra khi kéo dài bất thường hoặc tooling/kernel bắt đầu signal remaining tasks.

---

## 2. Safe-state và các switching mechanism của kernel livepatch

**Safe state nên hiểu chính xác thế nào?**

Không nên định nghĩa quá cứng:

```text
“safe = không có patched function trên stack”
```

Stack checking là **một cơ chế quan trọng**, nhưng upstream livepatch dùng nhiều cơ chế bổ sung:

1. reliable stack checking cho sleeping task;
2. kernel-exit switching khi task quay về userspace;
3. idle patch point;
4. explicit patch points cho một số kthread patterns.

Safe nghĩa rộng hơn:

> **Điểm mà task có thể đổi patch state mà không vi phạm consistency model của patch.**

**Cờ `TIF_PATCH_PENDING` và cơ chế chuyển đổi**:
Khi kích hoạt transition, Livepatch core bật cờ `TIF_PATCH_PENDING` trong `task_struct->flags` của mọi process/thread. Khi cờ này bật, kernel liên tục tìm cơ hội chuyển đổi trạng thái của task bằng 3 con đường chính:

1. **Reliable Stack Checking (Sleeping tasks)**:
   Nếu kiến trúc hỗ trợ unwind đáng tin cậy (như **ORC unwinder** `CONFIG_UNWINDER_ORC` trên x86_64), Livepatch core gọi `klp_check_stack()` để kiểm tra callstack của task đang ngủ (`TASK_INTERRUPTIBLE` / `TASK_UNINTERRUPTIBLE`). Nếu không có bất kỳ hàm bị vá (cả `old_func` và `new_func`) nằm trên stack, cờ `TIF_PATCH_PENDING` được xóa và patch state của task chuyển sang target.

---

**Kernel-exit switching**

User task có thể được switch khi quay về userspace sau:

- syscall;
- user IRQ;
- signal.

CPU-bound user task cuối cùng thường gặp interrupt và có opportunity switch.

I/O-bound task ngủ trong affected function có thể cần wake/signal để thoát path.

---

**Idle task và kthread**

Idle/swapper không quay userspace, nên livepatch có explicit update point trong idle loop.

Kthread tùy loại có thể khó hơn nếu không có reliable stack hoặc explicit patch point phù hợp.

---

## 3. Stalled transition, observability và case KVM

**Tại sao transition có thể stall?**

```text
Task X cứ nằm hoặc quay lại affected execution path
           ↓
không đạt switching condition
           ↓
patch_state vẫn initial
           ↓
transition = 1 kéo dài
```

---

**Observability**

```bash
cat /sys/kernel/livepatch/<patch>/transition
cat /proc/<pid>/patch_state
cat /proc/<pid>/task/<tid>/patch_state
sudo cat /proc/<pid>/task/<tid>/stack
```

---

**Case KVM workload**

Trong reverse transition của lab, target là `0`. Một số QEMU vCPU thread vẫn:

```text
CPU 0/KVM state=1
CPU 1/KVM state=1
```

trong khi nhiều QEMU thread khác đã `0`.

Đây là bằng chứng trực tiếp của per-task convergence.

---

**Signaling remaining tasks**

Kernel/livepatch có thể signal/poke remaining tasks để tạo opportunity update patch state.

Kpatch CLI có `signal`, nhưng trên kernel hỗ trợ automatic signaling lệnh này có thể no-op vì kernel tự làm.

---

## 4. Reverse/cancel và force: cơ chế cùng rủi ro

**Cancel/reverse transition**

Operator có thể đổi `enabled` về trạng thái ban đầu để reverse transition thay vì force.

Nhưng reverse **cũng là transition**, nên vẫn phải monitor.

---

**Force**

`force` là last resort. Upstream docs cảnh báo force có thể ảnh hưởng future livepatching; sau force nên lên kế hoạch reboot và tránh tiếp tục apply thêm livepatch.

```text
normal transition = chờ task hội tụ an toàn
force             = operator bỏ qua chờ hội tụ
```

---

## 5. Mental model và checklist chẩn đoán

**Mental model cuối cùng**

```text
function redirect = “đường nào có thể chạy”
patch_state       = “task này được phép chạy đường nào”
transition        = “các task đang hội tụ”
safe point        = “điểm task được chuyển state an toàn”
stall             = “ít nhất một task chưa hội tụ”
```

---

**Checklist debug transition**

```text
[ ] patching hay unpatching?
[ ] target state là 1 hay 0?
[ ] transition đã kéo dài bao lâu?
[ ] PID/TID nào khác target?
[ ] stack của nó ở đâu?
[ ] workload có thể quiesce không?
[ ] kernel đã signal remaining tasks chưa?
[ ] có nên reverse thay vì force không?
```

---

## 6. Tài liệu tham khảo

- https://docs.kernel.org/livepatch/livepatch.html
- https://docs.kernel.org/livepatch/reliable-stacktrace.html
