# 03 – `kpatch-build` và giải phẫu livepatch module

## Mục lục

1. [1. Đầu vào và pipeline build hai phiên bản](#1-đầu-vào-và-pipeline-build-hai-phiên-bản)
2. [2. Binary diff và mô hình function-level replacement](#2-binary-diff-và-mô-hình-function-level-replacement)
3. [3. Giải phẫu ELF và tính tương thích với kernel đích](#3-giải-phẫu-elf-và-tính-tương-thích-với-kernel-đích)
4. [4. Các bẫy patchability và thay đổi state/data](#4-các-bẫy-patchability-và-thay-đổi-statedata)
5. [5. Ý nghĩa build success, kiểm tra artifact và lệnh tối thiểu](#5-ý-nghĩa-build-success-kiểm-tra-artifact-và-lệnh-tối-thiểu)
6. [6. Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

## Pipeline kpatch-build

```text
                INPUT
 patch + source + config + exact vmlinux
                  |
                  v
        +-------------------+
        | Build baseline    |
        +-------------------+
                  |
                  v
             apply patch
                  |
                  v
        +-------------------+
        | Build patched     |
        +-------------------+
                  |
                  v
        compare ELF objects
                  |
                  v
       create-diff-object
                  |
                  v
 changed functions + relocations + metadata
                  |
                  v
         LIVEPATCH MODULE .ko
```

## 1. Đầu vào và pipeline build hai phiên bản

**Input contract của `kpatch-build`**

Để tạo một livepatch module đáng tin cậy, phải xem build như một **reproducibility problem**.

| Material | Vì sao cần |
|---|---|
| Source patch | Mô tả semantic fix cần đưa vào kernel. |
| Exact kernel source/package | Baseline binary phải tương ứng target. |
| Kernel config | Config quyết định code path, struct, feature, tracing. |
| Exact `vmlinux`/debug info | Symbol/binary context của target. |
| Headers | Build interfaces tương ứng kernel. |
| Compiler/binutils | Compiler khác có thể tạo binary diff giả. |
| Symbol/version info | Phục vụ ABI/module compatibility. |

---

**Vì sao build hai lần?**

Nếu chỉ compile file đã sửa, kpatch không biết thay đổi binary nào do patch và thay đổi nào do environment.

```text
source original ──compile──> original.o
       │
       └── apply diff
               ↓
source patched  ──compile──> patched.o

original.o  vs  patched.o
        ↓ binary/ELF analysis
changed functions
```

---

**Build baseline**

Kpatch-build chuẩn bị/build kernel hoặc target object để có baseline unpatched. Đây thường là bước tốn thời gian và disk nhất.

Baseline phải nhất quán về:

- config;
- compiler flags;
- generated headers;
- version string;
- toolchain.

---

**Apply source patch**

Pre-check:

```bash
patch -p1 --dry-run < fix.patch
```

“Apply được” chỉ chứng minh context source khớp, không chứng minh livepatch-safe.

---

**Build patched source**

Kpatch-build theo dõi objects bị rebuild. Đây là first approximation của phạm vi thay đổi.

Ví dụ:

```text
arch/x86/kvm/mmu/mmu.o
virt/kvm/kvm_main.o
```

---

## 2. Binary diff và mô hình function-level replacement

**Function/data sections**

Changed objects được compile với cờ GCC/Clang đặc biệt: `-ffunction-sections` và `-fdata-sections`. Cờ này ép compiler đưa mỗi function và data symbol vào một ELF section riêng biệt (ví dụ: `.text.foo`, `.text.bar`). Nhờ đó `create-diff-object` có thể so sánh nhị phân chi tiết ở mức độ từng hàm (function granularity) thay vì coi cả file object `.o` là một khối blob duy nhất.

---

**`create-diff-object`**

```text
original object
      +
patched object
      ↓
create-diff-object
      ↓
• detect changed/new functions
• analyze patchability
• preserve needed sections
• generate kpatch metadata
• generate dynamic relocation metadata
```

---

**Changed function ≠ changed line**

Một diff chỉ sửa 1 dòng có thể tạo:

- một changed function;
- nhiều changed functions nếu header/inline thay đổi;
- unexpected changes do compiler;
- changes trong caller vì inlining.

Do đó output:

```text
changed function: ...
new function: ...
```

phải được đối chiếu source review.

---

**Function granularity**

Kpatch thay implementation của whole function.

```text
old foo()
   ↓ redirect
new foo()
```

Không phải:

```text
old foo() + “thay đúng 3 instruction ở giữa”
```

---

**New functions**

Patch có thể thêm helper mới. Helper đó được đóng gói trong livepatch module và new patched function có thể gọi nó qua relocation phù hợp.

Case KVM MMU trong lab có helper:

```text
kpatch_child_sp_matches
kpatch_zap_present_spte
```

---

## 3. Giải phẫu ELF và tính tương thích với kernel đích

**ELF sections cần biết**

Tên section phụ thuộc kpatch/kernel version nhưng thường gặp:

```text
.kpatch.funcs
.kpatch.strings
.kpatch.*rela*
.klp.rela.*
__versions
```

Kiểm tra:

```bash
readelf -SW patch.ko | grep -E 'kpatch|klp|__versions'
```

---

**`vmlinux`: source version đúng chưa đủ**

Distro kernel có package/ABI flavor khác base upstream version.

Case trong lab Ubuntu:

```text
raw source kernelrelease → 6.8.12
running distro kernel    → 6.8.0-134-generic
```

Exact debug `vmlinux-6.8.0-134-generic` mới phản ánh target identity.

> **Đừng đồng nhất “source tree cùng nhánh” với “binary target giống hệt host”.**

---

**Vermagic mismatch**

Artifact build có thể `SUCCESS` nhưng:

```text
module vermagic = 6.8.12
host uname -r   = 6.8.0-134-generic
```

Module đó chưa đạt checkpoint target compatibility.

---

## 4. Các bẫy patchability và thay đổi state/data

**Jump labels / static keys**

Trong lab, patch `kvm_arch_vcpu_ioctl_run()` build fail với thông báo dạng:

```text
Found unsupported jump labels ...
Use static_key_enabled() instead.
```

Lý do: compiler/runtime static-key mechanism tạo code đặc biệt mà kpatch-build không thể đơn giản chuyển sang patch module trong context đó.

Bài học:

> Build system không chỉ “compile”; nó còn là **patchability gate**.

---

**Inline function problem**

Inline function không có function entry độc lập. Code của nó đã được copy vào caller.

```text
helper inline changed
  ↓
caller A changed
caller B changed
caller C changed
```

Human reviewer phải chắc danh sách changed functions bao phủ semantics của fix.

---

**Data structure và semantic changes**

Kpatch patches functions, không tự migrate arbitrary live data.

```c
struct foo {
    int a;
+   long new_field;
};
```

Objects tồn tại trong RAM vẫn theo layout cũ. Đây là class thay đổi nguy hiểm.

Linux livepatch có shadow variables và callbacks cho một số case chuyên sâu, nhưng không tự động.

---

**Callback lifecycle**

Kpatch macros hỗ trợ callback:

```text
pre-patch
post-patch
pre-unpatch
post-unpatch
```

Dùng khi function replacement đơn thuần không đủ và cần chuẩn bị/cleanup state.

---

## 5. Ý nghĩa build success, kiểm tra artifact và lệnh tối thiểu

**`SUCCESS` nghĩa gì?**

```text
SUCCESS = tool tạo được module từ binary differences mà nó chấp nhận
```

Không được hiểu:

```text
SUCCESS = patch chắc chắn correct + safe + production-ready
```

Human review vẫn phải xác nhận:

- semantic invariant;
- locking;
- shared data;
- inline callers;
- runtime workload;
- transition convergence.

---

**Audit checklist cho `.ko`**

```text
[ ] file tồn tại
[ ] modinfo name đúng
[ ] vermagic khớp host
[ ] section livepatch tồn tại
[ ] changed functions đúng dự kiến
[ ] no unexplained jump-label/static-call warning
[ ] signing policy rõ ràng
[ ] symbol/modversion compatibility được đánh giá
[ ] source patch đã human-reviewed
```

---

**Minimal command set**

```bash
patch -p1 --dry-run < fix.patch
kpatch-build ... fix.patch
modinfo patch.ko
readelf -SW patch.ko | grep -E 'kpatch|klp|__versions'
uname -r
modinfo -F vermagic patch.ko
```

---

## 6. Tài liệu tham khảo

- https://github.com/dynup/kpatch
- https://github.com/dynup/kpatch/blob/master/doc/patch-author-guide.md
- https://github.com/dynup/kpatch/blob/master/kpatch-build/kpatch-build
