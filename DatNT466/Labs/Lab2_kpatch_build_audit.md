# LAB 2 – KPATCH-BUILD VÀ ĐIỀU KIỆN ĐỂ LIVE PATCH VÀO KVM HOST

## 1. Mục tiêu bài lab

Mục tiêu của Lab 2 là dùng `kpatch-build` để chuyển một source patch (`.patch` / `.diff`) thành một **kernel livepatch module** dạng `.ko`, sau đó kiểm tra xem module này có đủ điều kiện kỹ thuật để có thể live patch vào KVM host đã tạo ở Lab 1 hay không.

Yêu cầu audit:

> **“kpatch-build ra 1 kernel object bất kỳ. Cần những điều kiện, material cụ thể nào để 1 bản kernel object có thể live patch vào host KVM tạo ở Lab 1.”**

Điểm quan trọng: không phải cứ có một file `.ko` là có thể live patch. File `.ko` phải được build **đúng cho kernel đang chạy trên host**, dựa trên **đúng source, config, toolchain, symbol/version information và patch context**.

---

## 2. Output của Lab 2

File livepatch module cuối cùng:

```bash
~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

Tên module:

```text
kvm_mmu_livepatch
```

Kích thước:

```text
~1.9 MB
```

Target kernel:

```text
6.8.0-134-generic
```

Kiểm tra `vermagic`:

```bash
modinfo -F vermagic \
  ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

Output:

```text
6.8.0-134-generic SMP preempt mod_unload modversions
```

Kernel đang chạy trên host:

```bash
uname -r
```

Output:

```text
6.8.0-134-generic
```

=> `vermagic` của livepatch module đã khớp với kernel host.

---

## 3. Các function được kpatch-build phát hiện

Trong quá trình build, `kpatch-build` xác định các thay đổi trong:

```text
arch/x86/kvm/mmu/mmu.o
```

Các function:

```text
new function:
- kpatch_child_sp_matches

changed function:
- __link_shadow_page

new function:
- kpatch_zap_present_spte

changed function:
- kvm_mmu_get_child_sp
```

Object/module liên quan:

```text
Patched objects: arch/x86/kvm/kvm.ko
```

Kết quả build:

```text
Building patch module: kvm-mmu-livepatch.ko
SUCCESS
```

---

## 4. Host KVM mục tiêu

Host được chuẩn bị ở Lab 1 có kernel:

```bash
uname -r
```

```text
6.8.0-134-generic
```

Kernel package:

```text
6.8.0-134.134
```

CPU hỗ trợ hardware virtualization:

```text
Intel VT-x
```

KVM device tồn tại:

```text
/dev/kvm
```

Kiểm tra:

```bash
kvm-ok
```

Kết quả:

```text
/dev/kvm exists
KVM acceleration can be used
```

Host có `qemu-kvm`, `libvirt`, `virtinst`, `bridge-utils`; hai VM được chạy trên host bằng KVM/libvirt.

Do patch của Lab 2 tác động vào:

```text
arch/x86/kvm/mmu/mmu.c
```

nên host Lab 1 chính là target phù hợp để thử live patch ở Lab 3.

---

## 5. Material bắt buộc để build livepatch module

### 5.1. Kernel target chính xác

Phải biết chính xác kernel đang chạy:

```bash
uname -r
```

Trong lab:

```text
6.8.0-134-generic
```

Đây là điều kiện quan trọng nhất. Nếu module được build với release khác, ví dụ `6.8.12`, nhưng host chạy `6.8.0-134-generic` thì module chưa đạt điều kiện compatibility cơ bản để load trực tiếp.

### 5.2. Kernel source đúng package/version

Source sử dụng:

```text
linux-source-6.8.0
```

Package version:

```text
6.8.0-134.134
```

Kiểm tra:

```bash
zgrep -m1 '^linux (' \
  /usr/share/doc/linux-source-6.8.0/changelog.Debian.gz
```

Output:

```text
linux (6.8.0-134.134) noble; urgency=medium
```

Source được đặt tại:

```text
~/kpatch-lab/kernel-build/linux-source-6.8.0
```

Lý do cần đúng source: `kpatch-build` phải build source gốc, apply patch, build source đã patch, so sánh ELF/object giữa hai bản, lấy các function thay đổi và đóng gói chúng thành livepatch module. Nếu source không khớp kernel target thì function layout, symbol, instruction hoặc ABI có thể khác.

---

## 6. Kernel headers

Headers của đúng kernel target đã được cài:

```text
linux-headers-6.8.0-134-generic
```

Version package:

```text
6.8.0-134.134
```

Headers cung cấp các interface cần thiết để build kernel/module.

Một điểm đặc biệt của Ubuntu trong lab:

```bash
make -s -C /usr/src/linux-headers-$(uname -r) kernelrelease
```

trả:

```text
6.8.12
```

trong khi:

```bash
uname -r
```

trả:

```text
6.8.0-134-generic
```

Điều này cho thấy Ubuntu kernel package có ABI/flavor metadata ngoài base upstream kernel version.

---

## 7. Kernel config

Config của kernel host:

```text
/boot/config-6.8.0-134-generic
```

Được copy vào source tree:

```bash
cp /boot/config-6.8.0-134-generic .config
make olddefconfig
```

Các option quan trọng đã kiểm tra:

```text
CONFIG_LIVEPATCH=y
CONFIG_FUNCTION_TRACER=y
CONFIG_DYNAMIC_FTRACE=y
CONFIG_DYNAMIC_FTRACE_WITH_REGS=y
CONFIG_DYNAMIC_FTRACE_WITH_DIRECT_CALLS=y
CONFIG_DYNAMIC_FTRACE_WITH_ARGS=y
CONFIG_MODVERSIONS=y
```

Ý nghĩa ngắn gọn:

- `CONFIG_LIVEPATCH=y`: bật Linux livepatch framework.
- `CONFIG_FUNCTION_TRACER=y` và `CONFIG_DYNAMIC_FTRACE=y`: cần cho cơ chế redirect function runtime.
- `CONFIG_MODVERSIONS=y`: kernel/module dùng symbol CRC/version để kiểm tra ABI module.

---

## 8. Điều chỉnh certificate config khi build source

Lần build source đầu gặp lỗi:

```text
No rule to make target 'debian/canonical-certs.pem', needed by 'certs/x509_certificate_list'
```

Khắc phục trong môi trường lab:

```bash
scripts/config --set-str SYSTEM_TRUSTED_KEYS ""
scripts/config --set-str SYSTEM_REVOCATION_KEYS ""
make olddefconfig
```

Kiểm tra:

```bash
grep -E 'CONFIG_SYSTEM_TRUSTED_KEYS|CONFIG_SYSTEM_REVOCATION_KEYS' .config
```

Output:

```text
CONFIG_SYSTEM_TRUSTED_KEYS=""
CONFIG_SYSTEM_REVOCATION_KEYS=""
```

Config dùng cho kpatch-build được lưu:

```text
~/kpatch-lab/config-6.8.0-134-kpatch
```

**Audit note:** đây là một deviation so với production Ubuntu kernel config, dùng để tránh dependency vào Canonical certificate trong quá trình build lab.

---

## 9. Compiler và binutils

Kernel host cho biết toolchain build:

```text
GCC 13.3.0
GNU Binutils 2.42
```

Compiler cài trên host cũng là GCC 13.3.0.

Điều này quan trọng vì compiler/binutils khác version có thể sinh object khác, dẫn tới chênh lệch không liên quan tới patch khi kpatch so sánh original và patched object.

---

## 10. Exact vmlinux của kernel target

Một material rất quan trọng là exact target `vmlinux`:

```text
vmlinux-6.8.0-134-generic
```

Ban đầu build trực tiếp source tree tạo ra identity base:

```text
Linux version 6.8.12
```

trong khi kernel host là:

```text
6.8.0-134-generic
```

Vì vậy đã lấy exact debug `vmlinux` từ Ubuntu Launchpad.

Package thực sự chứa debug vmlinux:

```text
linux-image-unsigned-6.8.0-134-generic-dbgsym_6.8.0-134.134_amd64.ddeb
```

Dung lượng package:

```text
~1.7 GB
```

Extract:

```bash
dpkg-deb -x \
  linux-image-unsigned-6.8.0-134-generic-dbgsym_6.8.0-134.134_amd64.ddeb \
  unsigned-extracted/
```

File exact target:

```text
~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic
```

Kiểm tra:

```bash
strings \
  ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic \
  | grep -m1 '^Linux version'
```

Output:

```text
Linux version 6.8.0-134-generic (buildd@lcy02-amd64-007) (x86_64-linux-gnu-gcc-13 (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, GNU ld (GNU Binutils for Ubuntu) 2.42) #134-Ubuntu SMP PREEMPT_DYNAMIC (Ubuntu 6.8.0-134.134-generic 6.8.12)
```

=> Đây là exact `vmlinux` phù hợp target host.

---

## 11. Tại sao cần vmlinux?

`vmlinux` cung cấp binary/debug/symbol context của kernel target. Trong workflow kpatch, nó giúp đối chiếu function/symbol, relocation và các special sections với kernel cần patch.

Nếu dùng sai `vmlinux`, livepatch có thể build được nhưng không có nghĩa nó phù hợp kernel host.

---

## 12. Patch source

Patch được lưu tại:

```text
~/kpatch-lab/patches/kvm-mmu.patch
```

Target file:

```text
arch/x86/kvm/mmu/mmu.c
```

Dry-run:

```bash
cd ~/kpatch-lab/kernel-build/linux-source-6.8.0
patch -p1 --dry-run < ~/kpatch-lab/patches/kvm-mmu.patch
```

Output:

```text
checking file arch/x86/kvm/mmu/mmu.c
```

Không có error/reject, tức patch apply được vào source tree đang dùng.

---

## 13. kpatch toolchain

Repository dùng:

```text
https://github.com/dynup/kpatch.git
```

Build/install:

```bash
make
sudo make install
```

Tool chính:

```text
/usr/local/bin/kpatch-build
/usr/local/sbin/kpatch
```

`kpatch-build` dùng để tạo livepatch module. `kpatch` dùng để quản lý module runtime như `load`, `unload`, `list`.

---

## 14. Build lần đầu và lỗi KERNELRELEASE

Command ban đầu:

```bash
kpatch-build \
  -a 6.8.0-134-generic \
  -s ~/kpatch-lab/kernel-build/linux-source-6.8.0 \
  -c ~/kpatch-lab/config-6.8.0-134-kpatch \
  -v ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic \
  -j 4 \
  -n kvm-mmu-livepatch \
  -o ~/kpatch-lab/output \
  ~/kpatch-lab/patches/kvm-mmu.patch
```

Build trả:

```text
SUCCESS
```

Nhưng kiểm tra:

```bash
modinfo -F vermagic ~/kpatch-lab/output/kvm-mmu-livepatch.ko
```

Output:

```text
6.8.12 SMP preempt mod_unload modversions
```

Trong khi host:

```text
6.8.0-134-generic
```

=> Module lần đầu chưa đạt điều kiện target compatibility.

---

## 15. Xác định nguyên nhân mismatch 6.8.12

Kiểm tra source/header:

```bash
make -s -C /usr/src/linux-headers-$(uname -r) kernelrelease
```

Output:

```text
6.8.12
```

Nhưng module KVM chính thức:

```bash
modinfo -F vermagic kvm
```

Output:

```text
6.8.0-134-generic SMP preempt mod_unload modversions
```

Ubuntu official build pipeline đưa ABI/flavor `6.8.0-134-generic` vào module release, trong khi raw source tree trả base release `6.8.12`.

---

## 16. Khắc phục KERNELRELEASE

Test override:

```bash
MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic' \
make -s kernelrelease
```

Output:

```text
6.8.0-134-generic
```

Rebuild với output riêng:

```bash
mkdir -p ~/kpatch-lab/output-kr134

MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic' \
kpatch-build \
  -a 6.8.0-134-generic \
  -s ~/kpatch-lab/kernel-build/linux-source-6.8.0 \
  -c ~/kpatch-lab/config-6.8.0-134-kpatch \
  -v ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic \
  -j 4 \
  -n kvm-mmu-livepatch \
  -o ~/kpatch-lab/output-kr134 \
  ~/kpatch-lab/patches/kvm-mmu.patch
```

Build output chính:

```text
Using source directory at /home/ubuntu/kpatch-lab/kernel-build/linux-source-6.8.0
Testing patch file(s)
Reading special section data
Building original source
Building patched source
Extracting new and modified ELF sections
arch/x86/kvm/mmu/mmu.o: new function: kpatch_child_sp_matches
arch/x86/kvm/mmu/mmu.o: changed function: __link_shadow_page
arch/x86/kvm/mmu/mmu.o: new function: kpatch_zap_present_spte
arch/x86/kvm/mmu/mmu.o: changed function: kvm_mmu_get_child_sp
Patched objects: arch/x86/kvm/kvm.ko
Building patch module: kvm-mmu-livepatch.ko
SUCCESS
```

---

## 17. Xác nhận vermagic sau rebuild

```bash
modinfo -F vermagic \
  ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

Output:

```text
6.8.0-134-generic SMP preempt mod_unload modversions
```

Stock KVM:

```bash
modinfo -F vermagic kvm
```

```text
6.8.0-134-generic SMP preempt mod_unload modversions
```

Kernel host:

```bash
uname -r
```

```text
6.8.0-134-generic
```

=> PASS điều kiện `vermagic`.

---

## 18. Livepatch-specific ELF sections

Kiểm tra:

```bash
readelf -S \
  ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko \
  | grep -E '__versions|klp|kpatch'
```

Các section thấy được gồm:

```text
.text.kpatch...
.kpatch.strings
.kpatch.funcs
.rela.kpatch...
__versions
.kpatch.call...
.kpatch.force
.klp.rela...
```

=> Module chứa metadata phục vụ kpatch/livepatch, không chỉ là một kernel module `.ko` thông thường.

---

## 19. CONFIG_MODVERSIONS và __versions

Kernel host:

```bash
grep '^CONFIG_MODVERSIONS' /boot/config-$(uname -r)
```

Output:

```text
CONFIG_MODVERSIONS=y
```

Livepatch module có section:

```text
__versions
```

Kiểm tra:

```bash
readelf -SW \
  ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko \
  | grep __versions
```

Output:

```text
[70] __versions PROGBITS 0000000000000000 002b00 0001c9 00 A 0 0 32
```

Stock KVM sau khi giải nén cũng có `__versions`.

---

## 20. Cảnh báo `modprobe --show-modversions`

Trong quá trình build xuất hiện:

```text
modprobe: FATAL: could not get modversions of ... kvm-mmu-livepatch.ko: Invalid argument
```

Kiểm tra livepatch bằng:

```bash
modprobe --show-modversions \
  ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

cũng trả `Invalid argument`.

Để đối chiếu, stock Ubuntu KVM module:

```text
/lib/modules/6.8.0-134-generic/kernel/arch/x86/kvm/kvm.ko.zst
```

được giải nén:

```bash
zstd -dc "$KVMKO" > /tmp/kvm-stock.ko
```

Stock module có `__versions`:

```bash
readelf -SW /tmp/kvm-stock.ko | grep __versions
```

nhưng:

```bash
modprobe --show-modversions /tmp/kvm-stock.ko
```

vẫn trả:

```text
Invalid argument
```

**Kết luận audit:** trong môi trường này không thể dùng riêng `modprobe --show-modversions` làm tiêu chí kết luận livepatch module bị hỏng, vì stock Ubuntu KVM module cũng gặp cùng hành vi. Tuy nhiên `CONFIG_MODVERSIONS=y` vẫn là điều kiện quan trọng và kernel sẽ thực hiện kiểm tra symbol/version compatibility khi module được load thật ở Lab 3.

---

## 21. Checklist material/điều kiện bắt buộc

| Material / điều kiện | Yêu cầu | Lab hiện tại |
|---|---|---|
| Target kernel | Biết chính xác kernel host | `6.8.0-134-generic` |
| Kernel package | Khớp ABI/package target | `6.8.0-134.134` |
| Kernel source | Đúng package/source context | PASS |
| Kernel headers | Đúng kernel target | PASS |
| Kernel config | Lấy từ host target | PASS |
| `CONFIG_LIVEPATCH` | `y` | PASS |
| `CONFIG_FUNCTION_TRACER` | `y` | PASS |
| `CONFIG_DYNAMIC_FTRACE` | `y` | PASS |
| `CONFIG_MODVERSIONS` | Phải xử lý đúng nếu bật | `y` |
| Compiler | Nên khớp kernel build | GCC 13.3.0 |
| Binutils | Nên khớp | 2.42 |
| Exact `vmlinux` | Phải đúng target | PASS |
| Debug symbols | Cần cho build/symbol context | PASS |
| Patch | Apply sạch vào source | PASS |
| `kpatch-build` | Build tool | PASS |
| `KERNELRELEASE` | Phải khớp host | FIXED |
| `vermagic` | Phải khớp host | PASS |
| Livepatch ELF metadata | `.kpatch.*`, `.klp.*` | PASS |
| Output `.ko` | Livepatch module | PASS |

---

## 22. Điều kiện để một kernel object có thể live patch vào host

### Điều kiện 1 – Đúng kernel release

```text
module vermagic == running kernel release
```

Trong lab:

```text
6.8.0-134-generic == 6.8.0-134-generic
```

PASS.

### Điều kiện 2 – Đúng kernel source/ABI context

Source phải tương ứng kernel package target `6.8.0-134.134`. Không nên dùng source khác ABI chỉ vì patch compile được.

### Điều kiện 3 – Đúng kernel config

Config ảnh hưởng tới function compilation, struct layout, enabled code paths, tracing, livepatch và module versioning. Do đó config phải bám sát host target.

### Điều kiện 4 – Toolchain tương thích

Compiler/binutils khác có thể làm thay đổi binary output. Trong lab toolchain được đối chiếu với kernel build information.

### Điều kiện 5 – Exact vmlinux/debug symbols

`vmlinux` phải đại diện đúng kernel đang chạy. Lab sử dụng `vmlinux-6.8.0-134-generic` từ Ubuntu dbgsym package.

### Điều kiện 6 – Patch phải apply sạch

Dry-run không được có reject/error.

### Điều kiện 7 – kpatch-build phải xác định đúng changed functions

Lab hiện tại phát hiện 2 function mới và 2 function thay đổi trong KVM MMU code.

### Điều kiện 8 – Module phải có livepatch metadata

Phải có các section kiểu `.kpatch.funcs`, `.kpatch.strings`, `.klp.rela.*`.

### Điều kiện 9 – Symbol/version compatibility

Nếu `CONFIG_MODVERSIONS=y`, symbol CRC/version compatibility là một phần cần kiểm tra khi load. Vì vậy chỉ nhìn thấy chữ `SUCCESS` từ `kpatch-build` chưa đủ để khẳng định module chắc chắn load được.

---

## 23. Material tree của Lab 2

```text
~/kpatch-lab/
│
├── kernel-build/
│   └── linux-source-6.8.0/
│       ├── arch/
│       ├── include/
│       ├── .config
│       └── ...
│
├── patches/
│   └── kvm-mmu.patch
│
├── dbgsym/
│   └── unsigned-extracted/
│       └── usr/lib/debug/boot/
│           └── vmlinux-6.8.0-134-generic
│
├── config-6.8.0-134-kpatch
│
├── output/
│   └── kvm-mmu-livepatch.ko
│       # bản build đầu, vermagic = 6.8.12
│
└── output-kr134/
    └── kvm-mmu-livepatch.ko
        # bản đúng, vermagic = 6.8.0-134-generic
```

Bản giữ lại để sang Lab 3:

```text
~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

---

## 24. Audit trail – lỗi và cách xử lý

### Issue 1 – Thiếu Canonical certificate

Error:

```text
No rule to make target 'debian/canonical-certs.pem'
```

Fix:

```bash
scripts/config --set-str SYSTEM_TRUSTED_KEYS ""
scripts/config --set-str SYSTEM_REVOCATION_KEYS ""
```

### Issue 2 – Source tree báo kernelrelease `6.8.12`

Raw source/header trả `6.8.12`, trong khi host là `6.8.0-134-generic`.

### Issue 3 – Livepatch build đầu có vermagic sai

```text
6.8.12 SMP preempt mod_unload modversions
```

=> không phù hợp host.

### Issue 4 – Override KERNELRELEASE

Fix:

```bash
MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic'
```

Rebuild cho ra:

```text
6.8.0-134-generic SMP preempt mod_unload modversions
```

PASS.

### Issue 5 – `modprobe --show-modversions` báo `Invalid argument`

Livepatch gặp lỗi; stock Ubuntu KVM module sau decompress cũng gặp lỗi giống hệt. Vì vậy ghi nhận warning nhưng không dùng riêng test này để tuyên bố livepatch module hỏng. Runtime load ở Lab 3 mới là bước kiểm tra thực tế tiếp theo.

---

## 25. Kết luận Lab 2

Lab 2 đã tạo thành công livepatch kernel module:

```text
kvm-mmu-livepatch.ko
```

Bản cuối cùng:

```text
~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

Các checkpoint quan trọng:

```text
Patch apply sạch                        PASS
Exact target source/package             PASS
Exact target vmlinux                    PASS
Compiler/toolchain phù hợp              PASS
CONFIG_LIVEPATCH                        PASS
ftrace requirements                     PASS
kpatch-build                            PASS
Changed functions detected              PASS
Livepatch ELF sections                  PASS
KERNELRELEASE                           PASS
vermagic = 6.8.0-134-generic            PASS
```

Điểm cần tiếp tục xác nhận ở Lab 3:

```text
Runtime module load
Kernel-side symbol/modversion check
Livepatch transition
Safe-state behavior
Ảnh hưởng tới VM workload
Rollback/unload behavior
```

### Kết luận kỹ thuật ngắn gọn

Để một `.ko` do `kpatch-build` tạo ra có khả năng live patch vào KVM host, không chỉ cần patch compile thành công mà phải có **đúng kernel target, exact source/package, config, compiler, exact vmlinux/debug symbols, compatible KERNELRELEASE/vermagic, livepatch/ftrace support và symbol/version compatibility**.

Trong Lab 2, lỗi đáng chú ý nhất là source Ubuntu trả base release `6.8.12`, dẫn tới module đầu tiên có vermagic sai. Sau khi ép:

```text
KERNELRELEASE=6.8.0-134-generic
```

module được rebuild với đúng vermagic của host.
