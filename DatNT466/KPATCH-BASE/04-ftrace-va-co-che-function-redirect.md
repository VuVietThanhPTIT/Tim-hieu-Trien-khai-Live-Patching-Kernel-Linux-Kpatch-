# 04 – ftrace và cơ chế function redirect

## Mục lục

1. [1. Nền tảng ftrace và dynamic function instrumentation](#1-nền-tảng-ftrace-và-dynamic-function-instrumentation)
2. [2. Cách Linux livepatch dùng ftrace để redirect function](#2-cách-linux-livepatch-dùng-ftrace-để-redirect-function)
3. [3. So sánh với các cơ chế hook/tracing khác và các giới hạn](#3-so-sánh-với-các-cơ-chế-hooktracing-khác-và-các-giới-hạn)
4. [4. Quan hệ giữa ftrace, transition và luồng livepatch hoàn chỉnh](#4-quan-hệ-giữa-ftrace-transition-và-luồng-livepatch-hoàn-chỉnh)
5. [5. Tài liệu tham khảo](#5-tài-liệu-tham-khảo)

## Function redirect bằng ftrace/livepatch

```text
TRƯỚC PATCH

 caller ---> foo_old()


SAU KHI LIVEPATCH ACTIVE

 caller
   |
   v
 function entry
   |
   v
 ftrace/livepatch handler
   |
   +-------- task dùng old state ----> foo_old()
   |
   +-------- task dùng new state ----> foo_new()

=> redirect xảy ra ở ranh giới function,
   còn consistency được KLP quản lý theo task.
```

## 1. Nền tảng ftrace và dynamic function instrumentation

**Ftrace là gì?**

Ftrace là tracing framework nằm trong kernel Linux. Nó được tạo để quan sát flow, latency và function calls trong kernel.

Dynamic ftrace có khả năng biến các function-entry call site giữa trạng thái gần như NOP và trạng thái gọi tracer/callback, giúp tracing tắt có overhead rất thấp.

---

**Compile-time instrumentation**

Khi kernel được build với function tracing support, compiler đặt instrumentation point gần đầu function, truyền thống là `mcount`, trên x86 hiện đại thường liên quan `__fentry__`/`-fentry`.

Không phải mọi function đều traceable:

- inline không có entry độc lập;
- `notrace` bị loại;
- assembly/special code có hạn chế;
- architecture/config phải hỗ trợ required ftrace behavior.

---

**Dynamic ftrace**

Mental model:

```text
TRACING OFF
function entry: NOP-like patched site

TRACING ON
function entry: call/jump through ftrace machinery
```

Chi tiết instruction phụ thuộc architecture/kernel version, nên không nên cố định thành “luôn đúng 5 byte NOP”.

---

## 2. Cách Linux livepatch dùng ftrace để redirect function

**Livepatch dùng ftrace khác tracing bình thường thế nào?**

Tracing:

```text
foo()
 ↓
ftrace callback
 ↓
record event
 ↓
continue foo()
```

Livepatch:

```text
foo_old entry
 ↓
livepatch ftrace handler
 ↓
select implementation
 ↓
foo_new
```

Handler của Livepatch đăng ký với ftrace bằng cờ đặc biệt `FTRACE_OPS_FL_IPMODIFY` và `FTRACE_OPS_FL_SAVE_REGS`. Khi hàm cũ được gọi, ftrace trampoline nhảy vào `klp_ftrace_handler()`. Handler này sẽ kiểm tra `patch_state` của task hiện tại:
- Nếu task có trạng thái `patched` (state 1): Handler sửa trực tiếp thanh ghi Instruction Pointer (`pt_regs->ip = (unsigned long)new_func`). Khi ftrace trampoline kết thúc và thực hiện `iret` / `ret`, CPU sẽ nhảy thẳng vào mã của `new_func` mà không thực thi bất kỳ lệnh nào của `old_func`.
- Nếu task vẫn ở trạng thái `unpatched` (state 0): Handler không sửa `pt_regs->ip`, CPU quay lại thực thi tiếp `old_func`.

---

**Function entry là điểm vàng**

Livepatch muốn redirect **trước khi function cũ thay đổi stack/parameter state**. Vì vậy upstream docs yêu cầu ftrace location đủ sớm ở function entry.

```text
function có ftrace entry phù hợp → candidate
inline / notrace / special entry → khó hoặc không được
```

---

**Old function có bị xóa không?**

Không nhất thiết. Trong transition, old code vẫn cần cho task còn old state.

```text
memory:
[foo_old] vẫn tồn tại
[foo_new] trong patch module

Task A state=0 → foo_old
Task B state=1 → foo_new
```

---

**Vì sao function granularity?**

Redirect được đăng ký ở function entry, do đó unit tự nhiên là **whole function**.

Kpatch-build xác định function changed trong ELF rồi tạo replacement implementation.

---

**Multiple patches trên cùng function**

Livepatch core có thể quản lý stack replacement cho cùng original function. Cumulative/replace patch giúp giảm complexity khi có nhiều patch nối tiếp.

Patch Author Guide của kpatch khuyến nghị cumulative upgrade khi patch hệ thống đã có patch.

---

## 3. So sánh với các cơ chế hook/tracing khác và các giới hạn

**Ftrace vs kprobe vs livepatch**

| Cơ chế | Mục tiêu chính | Redirect scope |
|---|---|---|
| ftrace | tracing/hooking function | function entry |
| kprobe | dynamic probe | gần arbitrary instruction |
| livepatch | semantic replacement | function-level + consistency |

Livepatch dùng ftrace infrastructure nhưng thêm **consistency model + lifecycle + metadata**.

---

**Ftrace vs eBPF**

EBPF attach vào nhiều hook/tracing point nhưng không phải abstraction tương đương với livepatch function replacement và consistency model.

---

**Pitfall: “ftrace chỉ thay byte đầu hàm”**

Cách nói chính xác hơn:

> Dynamic ftrace dựa vào compiler-generated function-entry instrumentation và runtime text modification/trampolines để gọi callback. Livepatch đăng ký handler dùng cơ chế đó để redirect tới replacement implementation.

---

**Kiểm tra ftrace support**

```bash
cat /boot/config-$(uname -r) | grep -E \
'CONFIG_FUNCTION_TRACER|CONFIG_DYNAMIC_FTRACE|CONFIG_LIVEPATCH'
```

Tracing fs:

```bash
mount | grep tracefs
ls /sys/kernel/tracing
```

---

## 4. Quan hệ giữa ftrace, transition và luồng livepatch hoàn chỉnh

**Liên hệ với transition**

Ftrace trả lời:

```text
“call function sẽ đi đâu?”
```

Consistency model trả lời:

```text
“task này được phép thấy implementation nào?”
```

Hai cơ chế phải đi cùng nhau.

---

**Luồng hoàn chỉnh**

```text
kpatch load
  ↓
KLP đăng ký replacement
  ↓
ftrace handler attach/update
  ↓
transition=1
  ↓
Task state quyết định old/new implementation
  ↓
all tasks converge
  ↓
transition=0
```

---

## 5. Tài liệu tham khảo

- https://docs.kernel.org/trace/ftrace.html
- https://docs.kernel.org/trace/ftrace-uses.html
- https://docs.kernel.org/livepatch/livepatch.html
