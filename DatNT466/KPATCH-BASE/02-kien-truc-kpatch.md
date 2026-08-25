# 02 – Giải phẫu kiến trúc kpatch

## Mục lục

1. [1. Bức tranh tổng thể và hai mặt phẳng build/runtime](#1-bức-tranh-tổng-thể-và-hai-mặt-phẳng-buildruntime)
2. [2. Các thành phần phía build: kpatch-build và livepatch module](#2-các-thành-phần-phía-build-kpatch-build-và-livepatch-module)
3. [3. Các thành phần phía runtime: module loader, KLP, ftrace và consistency](#3-các-thành-phần-phía-runtime-module-loader-klp-ftrace-và-consistency)
4. [4. Kernel object, symbol, relocation và compatibility](#4-kernel-object-symbol-relocation-và-compatibility)
5. [5. Vòng đời load hoàn chỉnh và điểm kiểm toán](#5-vòng-đời-load-hoàn-chỉnh-và-điểm-kiểm-toán)
6. [6. Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

## Kiến trúc từ build-time đến runtime

```text
BUILD-TIME (userspace)

 source patch + kernel source + config + vmlinux
                    |
                    v
              kpatch-build
                    |
                    v
          livepatch module .ko
                    |
====================|===================== kernel boundary
                    v
RUNTIME (kernel)

              Module loader
                    |
                    v
            Livepatch Core (KLP)
              |             |
              v             v
         ftrace redirect   per-task transition
              |             |
              +------+------+
                     v
             patched function
```

## 1. Bức tranh tổng thể và hai mặt phẳng build/runtime

**Bức tranh lớn**

Kpatch không phải một daemon đơn lẻ. Nó là chuỗi component từ build-time tới runtime:

```text
SOURCE / BUILD TIME

patch.diff
 + exact kernel source
 + config
 + vmlinux/debug info
 + compiler/binutils
        ↓
   kpatch-build
        ↓
 livepatch module .ko
        ↓
────────────────────────────────────
RUNTIME / KERNEL
        ↓
 kernel module loader
        ↓
 Linux Livepatch Core (KLP)
        ↓
 ftrace redirect
        ↓
 old/new kernel functions
```

---

**Build plane và runtime plane**

**Build plane**

Quan tâm:

- exact source;
- compiler;
- debug info;
- changed functions;
- static keys/jump labels;
- ELF/relocation.

**Runtime plane**

Quan tâm:

- module load;
- symbol resolution;
- transition;
- patch state;
- ftrace;
- workload impact;
- rollback.

Một module có thể **build thành công nhưng runtime fail**. Ngược lại, build fail thường có giá trị vì tool phát hiện patchability problem sớm.

---

## 2. Các thành phần phía build: kpatch-build và livepatch module

**Layer 1 – `kpatch-build`**

`kpatch-build` là compiler/orchestrator cho livepatch artifact. Nó không chỉ chạy `make` một lần. Nhiệm vụ chính:

- chuẩn bị kernel source;
- build baseline;
- apply source patch;
- build patched version;
- xác định changed objects/functions;
- kiểm tra một số patchability issue;
- tạo metadata/relocation;
- link ra `.ko`.

Helper quan trọng là `create-diff-object`.

---

**Layer 2 – livepatch module `.ko`**

Một `.ko` livepatch vẫn là ELF kernel module, nhưng có thêm metadata để Linux livepatch hiểu:

- function nào thuộc object nào cần thay;
- implementation mới nằm đâu;
- relocation nào phải resolve;
- callback nào chạy trước/sau patch;
- patch có replace patch cũ hay không.

Trong kpatch-generated artifact có thể gặp các section như:

```text
.kpatch.funcs
.kpatch.strings
.kpatch.force
.klp.rela.*
__versions
```

Section cụ thể phụ thuộc version/toolchain.

---

## 3. Các thành phần phía runtime: module loader, KLP, ftrace và consistency

**Layer 3 – kernel module loader**

Trước khi livepatch core có thể làm gì, kernel module loader phải chấp nhận ELF module:

```text
load .ko
  ↓
validate ELF
  ↓
resolve exported symbols / relocations
  ↓
check module compatibility / version data
  ↓
module_init()
```

Đây là nơi các vấn đề như vermagic, symbol version hoặc module signing có thể xuất hiện.

---

**Layer 4 – Linux Livepatch Core**

Linux livepatch infrastructure nằm trong kernel khi có `CONFIG_LIVEPATCH`.

Nó quản lý:

- `struct klp_patch`;
- patch objects (`vmlinux`, `kvm`, module khác);
- function replacement;
- transition state;
- per-task patch state;
- sysfs;
- enable/disable/replace;
- callbacks/shadow variables.

Runtime surface quan trọng:

```text
/sys/kernel/livepatch/<patch>/
```

Các file thường cần nhìn:

```text
enabled
transition
force
```

---

**Layer 5 – ftrace**

Linux livepatch sử dụng dynamic ftrace để redirect execution ở function entry.

Ftrace ban đầu là tracing framework, nhưng infrastructure cho phép callback can thiệp instruction pointer trên architecture/config phù hợp.

Mental model:

```text
caller
  ↓
function entry
  ↓
ftrace/livepatch handler
  ↓
chọn implementation phù hợp với patch state của task
  ↓
old_func hoặc new_func
```

Điều này giải thích vì sao livepatch là function-level replacement, không phải source-line patching.

---

**Layer 6 – consistency engine theo task**

Function redirect chưa đủ. Nếu task A đang chạy old function trong khi patch được enable, không thể ép nó nhảy giữa function.

KLP theo dõi patch state theo từng task:

```text
0 = unpatched
1 = patched
```

Trong transition, task khác nhau có thể tạm thời ở state khác nhau.

---

## 4. Kernel object, symbol, relocation và compatibility

**Object model: `vmlinux` vs module**

Kernel code có thể nằm trong:

```text
vmlinux      → built-in kernel code
kvm.ko       → KVM module
kvm_intel.ko → Intel-specific KVM module
...
```

Livepatch metadata phải xác định đúng **object owner** của function. Đây là lý do output `kpatch-build` kiểu:

```text
Patched objects: arch/x86/kvm/kvm.ko
```

rất quan trọng.

---

**Symbol, relocation và vì sao exact `vmlinux` quan trọng**

Code mới trong livepatch module vẫn gọi vào function/variable của kernel hiện tại. Địa chỉ thực tế chỉ biết khi link/load.

Relocation giúp chỉ định:

```text
“tại offset X của new_func, reference symbol Y (có thể là local/static symbol)”
```

**Cơ chế KLP Dynamic Relocations (`.klp.rela`)**:
Các hàm/biến nội bộ trong kernel (static/non-exported symbols) không thể resolve qua bảng ký hiệu chuẩn (`/proc/kallsyms`) khi nạp module thông thường. Vì vậy, Linux Livepatch định nghĩa các section chuyên dụng có định dạng `.klp.rela.<object>.<section_name>` (ví dụ: `.klp.rela.vmlinux.text.foo_new`). 

Khi `klp_enable_patch()` chạy, Livepatch core sẽ duyệt qua các section `.klp.rela` này, tra cứu địa chỉ của local symbol dựa trên metadata từ `vmlinux` (qua symbol table và `kallsyms_lookup_name()`), rồi tiến hành ghi đè địa chỉ tĩnh (apply relocation) vào mã máy của hàm mới trong memory trước khi kích hoạt ftrace redirect.

Exact `vmlinux`/debug data chứa đúng DWARF và symbol offsets của target kernel là yếu tố bắt buộc để `create-diff-object` xây dựng chính xác các section `.klp.rela` này.

---

**Vermagic và modversions**

**`vermagic`**

Chuỗi compatibility metadata của module, ví dụ:

```text
6.8.0-134-generic SMP preempt mod_unload modversions
```

Nếu target host là `6.8.0-134-generic` nhưng module mang `6.8.12`, đó là red flag.

**`CONFIG_MODVERSIONS`**

Khi bật, module/kernel sử dụng version/CRC information của exported symbols để tăng khả năng phát hiện ABI mismatch.

---

**Module signing và kernel taint**

Livepatch module tự build thường không được ký bằng distro production key. Kernel có thể log:

```text
module verification failed ... tainting kernel
```

Taint không đồng nghĩa load fail. Nhưng production cần policy signing/trust riêng.

---

## 5. Vòng đời load hoàn chỉnh và điểm kiểm toán

**Architecture walkthrough của một lần load**

```text
1. kpatch load patch.ko
2. userspace yêu cầu nạp module
3. module loader resolve ELF/symbol
4. module init đăng ký patch với KLP
5. KLP tạo sysfs entry
6. KLP đăng ký/stack function replacement qua ftrace
7. transition=1
8. task dần chuyển patch state
9. tất cả hội tụ
10. transition=0
```

---

**Audit checkpoints**

Một reviewer kiến trúc phải kiểm tra được:

```text
[ ] artifact target đúng kernel
[ ] object/function list đúng dự kiến
[ ] patch có KLP metadata
[ ] sysfs entry xuất hiện sau load
[ ] transition về 0
[ ] dmesg không có panic/oops
[ ] workload vẫn đáp ứng SLO
```

---

## 6. Tài liệu tham khảo

- https://github.com/dynup/kpatch
- https://docs.kernel.org/livepatch/api.html
- https://docs.kernel.org/livepatch/livepatch.html
