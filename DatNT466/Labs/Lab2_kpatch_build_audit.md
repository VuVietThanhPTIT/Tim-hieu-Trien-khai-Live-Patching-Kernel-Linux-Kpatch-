# LAB 2 – BUILD VÀ KIỂM CHỨNG LIVEPATCH MODULE BẰNG kpatch-build


## 1. Yêu cầu bài lab

Sử dụng công cụ `kpatch-build` để chuyển đổi một bản vá mã nguồn (`.patch` / `.diff`) thành một **Kernel Livepatch Module (`.ko`)**, sau đó thẩm định (audit) xem artifact đó có đạt đầy đủ các điều kiện kỹ thuật để nạp động (Livepatch) vào Host KVM đã dựng ở Lab 1 hay không.

### Câu hỏi audit chính:
> **Một tệp `.ko` do `kpatch-build` tạo ra cần những điều kiện và material cụ thể nào để có thể live patch vào Host KVM của Lab 1?**

### Điểm quan trọng cần ghi nhớ:

```text
 Có file .ko nhả ra  !=  Có Livepatch Module dùng được
```

Artifact chỉ thực sự có khả năng livepatch thành công khi nó được biên dịch trong đúng ngữ cảnh (Context) của Kernel Target:
$$\text{Livepatch Valid} = \text{Release} + \text{Package/ABI} + \text{Source} + \text{Config} + \text{Toolchain} + \text{vmlinux/Debug} + \text{Patch Context} + \text{MODVERSIONS}$$

---

## 2. Kết quả cần đạt

| Thành phần | Giá trị |
|---|---|
| **Host Target** | KVM Host từ Lab 1 (`datnt466-kpatch`) |
| **Hệ điều hành Host** | Ubuntu 24.04 LTS |
| **Kiến trúc CPU** | `x86_64` |
| **Kernel đang chạy** | `6.8.0-134-generic` |
| **Ubuntu Kernel Package** | `6.8.0-134.134` |
| **Patch Target Source** | `arch/x86/kvm/mmu/mmu.c` |
| **Patched Object** | `arch/x86/kvm/kvm.ko` |
| **Livepatch Module Name** | `kvm-mmu-livepatch.ko` |
| **File Artifact cuối cùng** | `~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko` |
| **Vermagic chuẩn cuối cùng** | `6.8.0-134-generic SMP preempt mod_unload modversions` |

### Các hàm được `kpatch-build` trích xuất thành công:
- **New functions:** `kpatch_child_sp_matches`, `kpatch_zap_present_spte`
- **Changed functions:** `__link_shadow_page`, `kvm_mmu_get_child_sp`

### Output build cuối cùng kỳ vọng:
```text
Patched objects: arch/x86/kvm/kvm.ko
Building patch module: kvm-mmu-livepatch.ko
SUCCESS
```

---

## 3. Hiểu đúng các object trong Lab 2

Trong bài lab này xuất hiện nhiều khái niệm tệp nhị phân dễ bị gọi chung là "Kernel Object". Việc phân biệt rõ vai trò của từng tệp là bắt buộc:

```text
                      LUỒNG BIẾN ĐỔI OBJECT TRONG KPATCH-BUILD

  kvm-mmu.patch
        │
        ▼
  mmu.c (Source File bị sửa)
        │
        ▼
  mmu.o original vs mmu.o patched  ───> [kpatch-build so sánh binary ELF]
                                                   │
                                                   ▼
  Target Module = kvm.ko ───────────────> Trích xuất Changed Functions
                                                   │
                                                   ▼
                                     kvm-mmu-livepatch.ko (Livepatch Module)
```

### 3.1. Source Object (`mmu.o`)
- Patch tác động vào mã nguồn: `arch/x86/kvm/mmu/mmu.c`.
- Khi biên dịch, file C này sinh ra object file: `arch/x86/kvm/mmu/mmu.o`.
- Đây là object mà `kpatch-build` phân tích nhị phân để trích xuất hàm mới và hàm thay đổi.

### 3.2. Target Kernel Module (`kvm.ko`)
- File `mmu.o` thuộc về Kernel Module KVM: `arch/x86/kvm/kvm.ko`.
- Do đó build log báo: `Patched objects: arch/x86/kvm/kvm.ko`.

### 3.3. Livepatch Module (`kvm-mmu-livepatch.ko`)
- `kpatch-build` không thay thế trực tiếp file `kvm.ko` hay `mmu.o`.
- Nó tạo ra một Module hoàn toàn mới tên là `kvm-mmu-livepatch.ko` chứa: **Mã hàm mới + Metadata livepatch + Mapping table + Relocations + Version information (`__versions`)**.

---

## 4. Điều kiện và material cần có trước khi build

### 4.1. Điều kiện kiểm tra tại Host Target (Preflight Checklist)

| Điều kiện kiểm tra | Câu lệnh / Vị trí | Yêu cầu chuẩn Lab 2 | Status |
|---|---|---|---|
| Kiến trúc CPU | `uname -m` | `x86_64` | **PASS** |
| Kernel Release | `uname -r` | `6.8.0-134-generic` | **PASS** |
| Package / ABI | `dpkg-query` | `6.8.0-134.134` | **PASS** |
| KVM Acceleration | `kvm-ok`, `/dev/kvm` | KVM acceleration can be used | **PASS** |
| Kernel Modules | `/boot/config-$KREL` | `CONFIG_MODULES=y` | **PASS** |
| Livepatch Framework | `/boot/config-$KREL` | `CONFIG_LIVEPATCH=y` | **PASS** |
| Dynamic Ftrace | `/boot/config-$KREL` | `CONFIG_DYNAMIC_FTRACE=y` | **PASS** |
| Ftrace Save Regs | `/boot/config-$KREL` | `CONFIG_DYNAMIC_FTRACE_WITH_REGS=y` | **PASS** |
| Symbol Versioning | `/boot/config-$KREL` | `CONFIG_MODVERSIONS=y` | **PASS** |
| Host Compiler | `gcc --version` | GCC 13.3.0 | **PASS** |
| Host Binutils | `ld --version` | GNU Binutils 2.42 | **PASS** |

### 4.2. Danh mục Material phục vụ biên dịch

| Material | Vai trò kỹ thuật |
|---|---|
| **Source Patch** | Mô tả chính xác các dòng mã C cần thay đổi (`kvm-mmu.patch`). |
| **Kernel Source đúng Ubuntu Package** | Cung cấp cây mã nguồn gốc `linux-source-6.8.0` (`6.8.0-134.134`). |
| **Kernel Config từ Host** | Đảm bảo các cờ tính năng trùng khớp với Host (`/boot/config-6.8.0-134-generic`). |
| **Kernel Headers đúng Target** | Cung cấp Kbuild interface và generated headers (`linux-headers-6.8.0-134-generic`). |
| **Exact Debug `vmlinux`** | Cung cấp bảng ký hiệu nhị phân (Symbol Table / Relocations) chưa bị unstripped. |
| **Compiler & Binutils phù hợp** | Triệt tiêu sai lệch mã máy do khác biệt công cụ dịch (GCC 13.3.0). |
| **`kpatch-build` Toolchain** | Bộ công cụ phân tích nhị phân ELF và đóng gói Livepatch Module. |

### 4.3. Đánh giá an toàn nội dung Patch
Không phải cứ build thành công là patch an toàn để nạp. Trước khi nạp ở Lab 3, bản vá KVM MMU phải đảm bảo các quy tắc:
- Không thay đổi kích thước `struct` C (Struct Layout) khi chưa dùng Shadow Variables.
- Không thay đổi thứ tự khóa (Lock Ordering) giữa các hàm.
- Không tác động vào các hàm `__init` đã giải phóng khỏi RAM sau khi boot.
- Hàm bị vá bắt buộc phải hỗ trợ ftrace (`notrace` functions là NO-GO).

---

## 5. Chuẩn bị workspace và biến môi trường

Khởi tạo cấu trúc thư mục làm việc tiêu chuẩn:
```bash
mkdir -p ~/kpatch-lab/{kernel-build,patches,dbgsym,output,output-kr134}
```

Thiết lập biến môi trường Kernel Release:
```bash
export KREL="$(uname -r)"
printf 'KREL=%s\n' "$KREL"
```
* **Output:** `KREL=6.8.0-134-generic`

---

## 6. Kiểm tra KVM host trước khi build

### 6.1. Kiểm tra Hệ điều hành, Kiến trúc và Kernel Release
```bash
uname -r
uname -m
grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
```
* **Output:** `6.8.0-134-generic`, `x86_64`, `Ubuntu 24.04 LTS`.

### 6.2. Kiểm tra KVM Acceleration
```bash
kvm-ok
```
* **Output:**
  ```text
  INFO: /dev/kvm exists
  KVM acceleration can be used
  ```

### 6.3. Kiểm tra các gói Kernel Package tương ứng
```bash
dpkg-query -W -f='${Package} ${Version}\n' \
  "linux-image-$KREL" \
  "linux-modules-$KREL" \
  "linux-headers-$KREL"
```
* **Output:** Cho ra cùng phiên bản package: `6.8.0-134.134`.

---

## 7. Chuẩn bị toolchain và dependencies

Tải mã nguồn công cụ `kpatch` từ repository chính thức và tiến hành biên dịch:
```bash
cd ~
git clone https://github.com/dynup/kpatch.git
cd kpatch
make && sudo make install
```

Kiểm tra vị trí các công cụ sau khi cài đặt:
```bash
which kpatch-build
which kpatch
```
* `/usr/local/bin/kpatch-build` $\rightarrow$ Công cụ biên dịch livepatch `.ko`.
* `/usr/local/sbin/kpatch` $\rightarrow$ Công cụ CLI nạp/gỡ livepatch ở runtime.

---

## 8. Chuẩn bị kernel source và headers

### 8.1. Kernel source

Tải gói `linux-source-6.8.0` và giải nén vào `~/kpatch-lab/kernel-build/linux-source-6.8.0`.

Kiểm tra file changelog để đảm bảo đúng version `6.8.0-134.134`:
```bash
zgrep -m1 '^linux (' /usr/share/doc/linux-source-6.8.0/changelog.Debian.gz
```
* **Output:** `linux (6.8.0-134.134) noble; urgency=medium`

### 8.2. Kernel headers

Kiểm tra tên phiên bản phát hành từ Kernel Headers:
```bash
make -s -C /usr/src/linux-headers-$(uname -r) kernelrelease
```
* **Output:** `6.8.12`
* **Ghi nhận:** Mã nguồn gốc trả về base release `6.8.12`, trong khi `uname -r` là `6.8.0-134-generic`. Sự lệch nhau này sẽ được xử lý bằng cờ ghi đè `KERNELRELEASE` ở Bước 11.

---

## 9. Chuẩn bị kernel config

Di chuyển vào thư mục mã nguồn Kernel và sao chép cấu hình từ Host:
```bash
cd ~/kpatch-lab/kernel-build/linux-source-6.8.0
cp /boot/config-6.8.0-134-generic .config
make olddefconfig
```

Xác nhận các cờ tính năng quan trọng đã được bật:
- `CONFIG_LIVEPATCH=y` $\rightarrow$ Khung Livepatch của Kernel.
- `CONFIG_FUNCTION_TRACER=y` & `CONFIG_DYNAMIC_FTRACE=y` $\rightarrow$ Bộ chuyển hướng hàm ftrace.
- `CONFIG_MODVERSIONS=y` $\rightarrow$ Kiểm tra mã băm CRC của biểu tượng hàm.

---

## 10. Xử lý lỗi certificate của Ubuntu source tree

### Lỗi gặp phải khi build mã nguồn Ubuntu gốc:
```text
No rule to make target 'debian/canonical-certs.pem', needed by 'certs/x509_certificate_list'
```

### Cách xử lý:
Làm rỗng chuỗi khai báo đường dẫn chứng chỉ ký số trong `.config`:
```bash
scripts/config --set-str SYSTEM_TRUSTED_KEYS ""
scripts/config --set-str SYSTEM_REVOCATION_KEYS ""
make olddefconfig
```

Kiểm tra lại:
```bash
grep -E 'CONFIG_SYSTEM_TRUSTED_KEYS|CONFIG_SYSTEM_REVOCATION_KEYS' .config
```
* **Output:** `CONFIG_SYSTEM_TRUSTED_KEYS=""` và `CONFIG_SYSTEM_REVOCATION_KEYS=""`.

Lưu file cấu hình đã làm sạch ra: `~/kpatch-lab/config-6.8.0-134-kpatch`.

---

## 11. Chuẩn bị exact debug vmlinux

**Mục tiêu:** Sở hữu file `vmlinux` gốc chưa bị unstripped của bản build `6.8.0-134-generic`.

Tải gói Debug Symbols `linux-image-unsigned-6.8.0-134-generic-dbgsym_6.8.0-134.134_amd64.ddeb` (~1.7 GB) từ Ubuntu Launchpad và giải nén:
```bash
dpkg-deb -x \
  linux-image-unsigned-6.8.0-134-generic-dbgsym_6.8.0-134.134_amd64.ddeb \
  ~/kpatch-lab/dbgsym/unsigned-extracted/
```

File `vmlinux` thu được tại:
`~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic`

Kiểm tra chuỗi định danh bên trong `vmlinux`:
```bash
strings ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic | grep -m1 '^Linux version'
```
* **Output:** `Linux version 6.8.0-134-generic ... (Ubuntu 6.8.0-134.134-generic 6.8.12)` $\rightarrow$ **PASS**.

---

## 12. Chuẩn bị source patch và kiểm tra patch

Lưu file bản vá vào: `~/kpatch-lab/patches/kvm-mmu.patch` (sửa đổi KVM MMU trong `arch/x86/kvm/mmu/mmu.c`).

Chạy thử áp dụng patch ở chế độ dùng thử (Dry-Run):
```bash
cd ~/kpatch-lab/kernel-build/linux-source-6.8.0
patch -p1 --dry-run < ~/kpatch-lab/patches/kvm-mmu.patch
```
* **Output:** `checking file arch/x86/kvm/mmu/mmu.c` (Không xảy ra lỗi xung đột dòng hay bị reject $\rightarrow$ **PASS**).

---

## 13. Build livepatch lần đầu

Thực thi lệnh `kpatch-build` lần thứ nhất:
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
* **Kết quả Build:** Báo `SUCCESS`.

Kiểm tra ngay `vermagic` của tệp `.ko` thu được:
```bash
modinfo -F vermagic ~/kpatch-lab/output/kvm-mmu-livepatch.ko
```
* **Output:** `6.8.12 SMP preempt mod_unload modversions`

> [!CAUTION]
> **THẤT BẠI (FAIL):** Chuỗi `vermagic` mang giá trị `6.8.12`, bị **LỆCH** so với Kernel Host (`6.8.0-134-generic`). Tệp `.ko` này chưa thể sử dụng.

---

## 14. Phát hiện lỗi vermagic = 6.8.12 và xác định nguyên nhân KERNELRELEASE mismatch

### Phân tích nguyên nhân kỹ thuật:
- Mã nguồn gốc (Raw Source Tree) trả về tên phiên bản base release là `6.8.12`.
- Quy trình build chính thức của Ubuntu chèn thêm ABI/Flavor `6.8.0-134-generic` vào tên module.
- Vì vậy, ta phải ép biến môi trường `KERNELRELEASE` trong cờ `MAKEFLAGS` khi gọi `kpatch-build`.

---

## 15. Rebuild với KERNELRELEASE đúng

Thử nghiệm ép biến `KERNELRELEASE`:
```bash
MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic' make -s kernelrelease
```
* **Output:** `6.8.0-134-generic`

Tiến hành Rebuild tạo artifact chuẩn tại thư mục `output-kr134`:
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

* **Output quá trình trích xuất nhị phân ELF:**
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

## 16. Gate kiểm tra artifact trước khi sang Lab 3

File Artifact chuẩn được giữ lại cho Lab 3:
`~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko`

Kiểm tra lại `vermagic`:
```bash
modinfo -F vermagic ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```
* **Output:** `6.8.0-134-generic SMP preempt mod_unload modversions`

### Phép đối chiếu 3 bên (Mental Check):
$$\text{Livepatch Vermagic} \equiv \text{Stock KVM Vermagic} \equiv \text{Host Kernel Release} = \mathbf{6.8.0-134-generic} \quad (\text{PASS})$$

---

## 17. Kiểm tra livepatch ELF metadata và MODVERSIONS

### 17.1. Kiểm tra các ELF Sections đặc thù
```bash
readelf -S ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko | grep -E '__versions|klp|kpatch'
```
* **Output:** Xuất hiện các phân đoạn `.kpatch.funcs`, `.kpatch.strings`, `.klp.rela...`, `__versions` $\rightarrow$ Xác nhận đây là một Livepatch Module hoàn chỉnh.

### 17.2. Kiểm tra cờ MODVERSIONS và cảnh báo `modprobe`
```bash
grep '^CONFIG_MODVERSIONS' /boot/config-$(uname -r)
```
* **Output:** `CONFIG_MODVERSIONS=y`

```bash
readelf -SW ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko | grep __versions
```
* **Output:** `[70] __versions PROGBITS ...`

> [!NOTE]
> Lệnh `modprobe --show-modversions` báo `Invalid argument` trên cả Livepatch Module lẫn Module KVM gốc của Ubuntu. Đây là hạn chế của lệnh `modprobe` đối với tệp đĩa rời, không phản ánh tệp Livepatch bị hỏng. Runtime load ở Lab 3 sẽ là bước kiểm tra thực tế tiếp theo.

---

## 18. Material tree cuối cùng

```text
~/kpatch-lab/
│
├── kernel-build/
│   └── linux-source-6.8.0/         # Cây mã nguồn Kernel 6.8.0-134.134
│
├── patches/
│   └── kvm-mmu.patch               # File bản vá mã nguồn KVM MMU
│
├── dbgsym/
│   └── unsigned-extracted/         # Thư mục giải nén vmlinux debug
│       └── usr/lib/debug/boot/
│           └── vmlinux-6.8.0-134-generic
│
├── config-6.8.0-134-kpatch         # File config chuẩn của Host
│
├── output/
│   └── kvm-mmu-livepatch.ko        # [BẢN ĐẦU - BỎ] vermagic = 6.8.12
│
└── output-kr134/
    └── kvm-mmu-livepatch.ko        # [BẢN CHUẨN - DÙNG CHO LAB 3] vermagic = 6.8.0-134-generic
```

---

## 19. Audit trail – lỗi và cách xử lý

| Issue | Hiện tượng lỗi | Nguyên nhân kỹ thuật | Cách xử lý (Fix) |
|---|---|---|---|
| **Issue 1** | `No rule to make target 'debian/canonical-certs.pem'` | Thiếu file chứng chỉ ký số nội bộ của Canonical trong standalone source. | `scripts/config --set-str SYSTEM_TRUSTED_KEYS ""` & `SYSTEM_REVOCATION_KEYS ""` rồi `make olddefconfig`. |
| **Issue 2** | Raw Source / Header trả `6.8.12` | Mã nguồn gốc chưa chèn ABI/Flavor `6.8.0-134-generic` của Ubuntu. | Ghi nhận sự chênh lệch và xử lý bằng `KERNELRELEASE`. |
| **Issue 3** | Build `SUCCESS` nhưng `vermagic = 6.8.12` | `kpatch-build` lấy tên release từ Kbuild mặc định của source tree. | Thêm cờ `MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic'` khi gọi `kpatch-build`. |
| **Issue 4** | `modprobe --show-modversions` báo `Invalid argument` | Hạn chế của tiện ích `modprobe` trên Ubuntu khi đọc file `.ko` rời ngoài hệ thống. | Bỏ qua cảnh báo CLI này; chờ nghiệm thu nạp thật ở Lab 3. |

---

## 20. Checklist PASS/FAIL

| Hạng mục kiểm tra | Tiêu chuẩn đánh giá | Kết quả |
|---|---|---|
| **Host Kernel Target** | Đã xác định chính xác `6.8.0-134-generic` | **PASS** |
| **Package Version** | Khớp phiên bản Ubuntu Package `6.8.0-134.134` | **PASS** |
| **Kernel Source** | Cây mã nguồn `linux-source-6.8.0` khớp context | **PASS** |
| **Kernel Headers** | Đã cài đặt `linux-headers-6.8.0-134-generic` | **PASS** |
| **Kernel Config** | Đã bật `CONFIG_LIVEPATCH`, `ftrace`, `MODVERSIONS` | **PASS** |
| **Host Toolchain** | GCC 13.3.0 và GNU Binutils 2.42 đồng nhất | **PASS** |
| **Exact `vmlinux`** | Bản unstripped lấy từ `dbgsym` ddeb package | **PASS** |
| **Patch Dry-Run** | Apply sạch vào `arch/x86/kvm/mmu/mmu.c` | **PASS** |
| **`kpatch-build` Tool** | Cài đặt và vận hành thành công | **PASS** |
| **Changed Functions** | Trích xuất đúng 4 hàm trong `kvm.ko` | **PASS** |
| **`KERNELRELEASE` Override** | Ép thành công về `6.8.0-134-generic` | **PASS** |
| **Final `vermagic`** | Khớp 100% với `uname -r` của Host Target | **PASS** |
| **Livepatch ELF Metadata** | Tồn tại đầy đủ `.kpatch.*` và `.klp.*` sections | **PASS** |
| **Artifact Output** | Tệp `output-kr134/kvm-mmu-livepatch.ko` tạo thành công | **PASS** |

---

## 21. Kết luận Lab 2

Lab 2 đã tạo thành công file Livepatch Kernel Module:
`~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko`

**Bài học cốt lõi từ Lab 2:**
1. Một file `.ko` báo `kpatch-build SUCCESS` chưa chắc đã có thể nạp vào Kernel nếu lệch `vermagic` hoặc sai ngữ cảnh `vmlinux`.
2. Lỗi phổ biến nhất khi build livepatch trên Ubuntu là mã nguồn trả về base release (`6.8.12`), cần phải dùng cờ ghi đè `MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic'` để ép chuỗi `vermagic` khớp 100% với Host target.

File artifact `output-kr134/kvm-mmu-livepatch.ko` hiện tại đã đạt đầy đủ điều kiện kỹ thuật để chuyển sang **LAB 3 (Nạp và Thử nghiệm Runtime Livepatch trên Host KVM)**.

---

## 22. Command flow rút gọn để làm lại lab

Trường hợp đã chuẩn bị sẵn các tệp nguyên liệu, chuỗi lệnh thực thi ngắn gọn từ đầu đến cuối là:

```bash
# 1. Xác định Kernel Target
uname -r

# 2. Vào thư mục mã nguồn và chuẩn bị Config
cd ~/kpatch-lab/kernel-build/linux-source-6.8.0
cp /boot/config-6.8.0-134-generic .config
scripts/config --set-str SYSTEM_TRUSTED_KEYS ""
scripts/config --set-str SYSTEM_REVOCATION_KEYS ""
make olddefconfig

# 3. Chạy thử áp dụng Patch (Dry-Run)
patch -p1 --dry-run < ~/kpatch-lab/patches/kvm-mmu.patch

# 4. Kiểm tra thông tin exact vmlinux
strings ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic | grep -m1 '^Linux version'

# 5. Kiểm tra khả năng ghi đè KERNELRELEASE
MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic' make -s kernelrelease

# 6. Biên dịch Livepatch Module chuẩn
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

# 7. Thẩm định vermagic khớp với Host
modinfo -F vermagic ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
uname -r
modinfo -F vermagic kvm

# 8. Thẩm định Livepatch ELF Metadata
readelf -S ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko | grep -E '__versions|klp|kpatch'
```
