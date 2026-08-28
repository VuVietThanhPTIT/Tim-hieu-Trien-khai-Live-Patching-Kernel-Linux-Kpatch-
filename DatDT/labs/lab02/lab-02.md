# Tài liệu quy trình: Build & Live-Patch Kernel KVM Host bằng `kpatch-build`

> Tổng hợp lại từ lịch sử lệnh (`history`) thực hiện trên host `datdt113-kpatch4`, kernel mục tiêu **Ubuntu 24.04 LTS – 6.8.0-134-generic (x86_64)**.
> Mục tiêu bài lab: dùng `kpatch-build` tạo ra một **kernel object (.ko) live patch**, sau đó nạp (`kpatch load`) vào đúng KVM host đã dựng ở Lab 1 mà **không cần reboot**.

---
## 1. Bức tranh tổng quan: `kpatch-build` hoạt động thế nào
`kpatch-build` không "vá" trực tiếp kernel đang chạy. Nó làm việc theo cơ chế **build lại 2 lần rồi diff nhị phân**:

1. Build kernel **gốc** (chưa patch) từ source tree + config đúng như kernel đang chạy trên host.
2. Áp `.patch` (source diff) vào cùng source tree đó, build lại lần 2.
3. So sánh (diff) object code của 2 lần build ở cấp độ hàm (function-level), tìm ra những hàm bị thay đổi.
4. Đóng gói các hàm đã thay đổi thành một **kernel module `.ko`** (dùng cơ chế `livepatch`/ftrace của kernel Linux để redirect hàm cũ → hàm mới khi module này được `insmod`/`kpatch load`).

Vì bước 3 phụ thuộc vào việc **so khớp chính xác** với kernel nhị phân đang chạy, toàn bộ độ khó của bài lab nằm ở việc **tái tạo đúng môi trường build** đã sinh ra kernel `6.8.0-134-generic` đang chạy trên host, chứ không nằm ở nội dung patch.

---

## 2. Trình tự các giai đoạn đã thực hiện

### Giai đoạn 0 — Chuẩn bị kernel mục tiêu trên host (26/08)
```bash
sudo apt install -y linux-image-6.8.0-134-generic linux-headers-6.8.0-134-generic
sudo reboot
```
Cài đúng gói kernel `6.8.0-134-generic` (kernel sẽ được live-patch) và header tương ứng, sau đó reboot để host thực sự chạy trên kernel này. Đây là **kernel mục tiêu (target kernel)** — mọi thứ build sau này phải khớp với chính xác bản này.

### Giai đoạn 1 — Cài công cụ `kpatch` và toolchain build kernel (27/08)
```bash
sudo apt install -y kpatch kpatch-build build-essential dwarves \
    libelf-dev elfutils dpkg-dev git ccache bc flex bison \
    libssl-dev libncurses-dev
```
- `kpatch`, `kpatch-build`: công cụ chính.
- `dwarves` (chứa `pahole`): cần để sinh thông tin BTF/DWARF, phục vụ diff nhị phân.
- `libelf-dev`, `elfutils`: đọc/ghi ELF, cần cho `objtool`, `resolve_btfids`.
- `build-essential`, `flex`, `bison`, `bc`, `libssl-dev`, `libncurses-dev`: toolchain build kernel Linux tiêu chuẩn (biên dịch `.config`, sinh `vmlinux`, sinh header).

Kiểm tra môi trường:
```bash
gcc --version
cat /proc/version
uname -r ; uname -m
grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
dpkg-query -W -f='${Package} ${Version}\n' "linux-image-$KREL" "linux-modules-$KREL" "linux-headers-$KREL"
```

### Giai đoạn 2 — Thử đầu tiên với source "generic" `linux-source-6.8.0` (thất bại)
```bash
sudo apt install linux-source-6.8.0
tar -xf /usr/src/linux-source-6.8.0.tar.bz2 -C ~/kpatch-lab/kernel-build/
```
Đây là **source upstream đóng gói theo package `linux-source`**, chỉ mang version `6.8.0` (không có số revision `.134`). Source này **không đảm bảo khớp 100%** với các patch riêng của Ubuntu đã được áp vào bản `6.8.0-134.134` đang chạy thật trên host.

Các bước chuẩn bị `.config` và `vmlinux` debug (áp dụng lặp lại ở các lần build sau này, xem Giai đoạn 4–5), rồi chạy thử:
```bash
kpatch-build -a 6.8.0-134-generic \
  -s ~/kpatch-lab/kernel-build/linux-source-6.8.0 \
  -c ~/kpatch-lab/config-6.8.0-134-kpatch \
  -v ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic \
  -j 4 -n kvm-mmu-livepatch \
  -o ~/kpatch-lab/output \
  ~/kpatch-lab/patches/kvm-mmu.patch
```
**Kết quả:** thư mục `output/` cuối cùng **rỗng**, không sinh ra `.ko` — nghĩa là lần build này chưa bao giờ hoàn tất thành công (được xác nhận lại ở ngày 28/08 bằng lệnh `modinfo` báo *not found*). Nguyên nhân cốt lõi: source `linux-source-6.8.0` không phải bản source **chính xác theo từng patch/revision** mà Ubuntu dùng để build ra `6.8.0-134.134` — nên không thể tái tạo lại nhị phân gốc để diff đúng.

### Giai đoạn 3 — Lấy debug symbols (`dbgsym`) khớp đúng bản kernel
```bash
wget -c http://ddebs.ubuntu.com/pool/main/l/linux/linux-image-unsigned-6.8.0-134-generic-dbgsym_6.8.0-134.134_amd64.ddeb
dpkg-deb -x linux-image-unsigned-6.8.0-134-generic-dbgsym_6.8.0-134.134_amd64.ddeb \
  ~/kpatch-lab/dbgsym/unsigned-extracted/
strings ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic \
  | grep -m1 '^Linux version'
```
- `.ddeb` là gói **debug symbol** (chứa DWARF debug info) đi kèm chính xác với `linux-image-unsigned-6.8.0-134-generic` phiên bản `6.8.0-134.134`.
- `vmlinux` có debug info này là **bắt buộc** để `kpatch-build` biết cấu trúc symbol/offset thật của kernel đang chạy, dùng làm "khuôn" so sánh.
- Lệnh `strings ... | grep '^Linux version'` dùng để **xác nhận** chuỗi version-string trong `vmlinux` khớp đúng với kernel đang chạy trên host (kiểm tra chéo, tránh lấy nhầm dbgsym của version khác).

### Giai đoạn 4 — Chuẩn bị `.config` khớp kernel đang chạy
```bash
cp /boot/config-6.8.0-134-generic .config
make olddefconfig
grep -E 'CONFIG_SYSTEM_TRUSTED_KEYS|CONFIG_SYSTEM_REVOCATION_KEYS' .config
scripts/config --set-str SYSTEM_TRUSTED_KEYS ""
scripts/config --set-str SYSTEM_REVOCATION_KEYS ""
make olddefconfig
cp .config ~/kpatch-lab/config-6.8.0-134-kpatch
```
- Lấy đúng `.config` mà Ubuntu dùng để build kernel đang chạy (`/boot/config-<uname -r>`).
- `make olddefconfig`: đồng bộ lại config với source tree hiện có (điền giá trị mặc định cho option mới/thiếu) mà **không hỏi tương tác**.
- Xoá `SYSTEM_TRUSTED_KEYS` / `SYSTEM_REVOCATION_KEYS`: bản gốc Ubuntu trỏ tới certificate riêng của Canonical (không có sẵn trong môi trường build của mình) — nếu để nguyên, build sẽ lỗi vì thiếu file cert dùng để ký module. Set rỗng để build không cố ký module bằng key không tồn tại.
- File `.config` cuối cùng được lưu lại làm **config chuẩn dùng chung** (`config-6.8.0-134-kpatch`) cho mọi lần `kpatch-build` sau này.

### Giai đoạn 5 — Viết & tinh chỉnh patch nguồn (`kvm-mmu.patch`)
*(Phần copy nội dung patch qua `nano`/`cat << EOF`/`base64` được lược bớt trong tài liệu này vì đã chỉnh sửa lại nhiều lần — chỉ giữ lại bản cuối cùng dùng để build thành công.)*

Patch cuối cùng chỉnh sửa 2 file:
- `arch/x86/kvm/mmu/mmu.c`
- `arch/x86/kvm/mmu/paging_tmpl.h`

Nội dung về mặt logic:
- Thêm hàm `kvm_mmu_zap_child_spte_if_mismatch()` (đánh dấu `noinline` để bảo đảm nó tồn tại như một hàm riêng biệt, dễ được `kpatch-build` nhận diện và đóng gói khi diff).
- Đưa logic kiểm tra "SPTE con có khớp `gfn`/`role` hay không" ra khỏi điều kiện `if` trong `kvm_mmu_get_child_sp()`, gọi qua hàm mới.
- Đổi thứ tự kiểm tra `is_page_fault_stale()` trong `direct_page_fault()` (mmu.c) và `FNAME(page_fault)()` (paging_tmpl.h): kiểm tra **sau** khi gọi `make_mmu_pages_available()` thay vì trước, để đóng cả 2 hàm bị ảnh hưởng vào cùng một "changeset" hợp lệ về mặt kiểm soát khoá (`mmu_lock`).

Kiểm tra patch áp được vào đúng source tree trước khi build:
```bash
patch -p1 --dry-run < ~/kpatch-lab/patches/kvm-mmu.patch
```

### Giai đoạn 6 — Phát hiện vấn đề "source không khớp ABI" → chuyển sang git clone chính xác từ Launchpad
Nhiều lần dry-run patch bị lỗi `can't find file to patch`, phải dùng `-l` (ignore whitespace) để né tạm — dấu hiệu cho thấy **nội dung file gốc trong source tree không khớp 100%** với những gì patch kỳ vọng (vì `linux-source-6.8.0` chỉ là bản upstream chung, không phải bản Ubuntu build thật).

Giải pháp: clone **chính xác source tree Ubuntu dùng để build ra kernel đang chạy**, theo đúng tag:
```bash
git clone --depth 1 --branch "Ubuntu-6.8.0-134.134" \
  https://git.launchpad.net/~ubuntu-kernel/ubuntu/+source/linux/+git/noble
cd noble
git status        # Not currently on any branch. (detached tag)
git log -1 --oneline
# 8210677b0 (grafted, HEAD, tag: Ubuntu-6.8.0-134.134) UBUNTU: Ubuntu-6.8.0-134.134
head -n 5 debian.master/changelog
# linux (6.8.0-134.134) noble; urgency=medium
```
Đây là điểm mấu chốt của cả bài lab: **tag `Ubuntu-6.8.0-134.134` chính là source code y hệt** (từng dòng, từng patch riêng của Ubuntu) đã được Canonical dùng để build ra gói `linux-image-6.8.0-134-generic` phiên bản `6.8.0-134.134` mà host đang chạy. Có source tree đúng thì:
- `patch -p1 --dry-run` mới áp sạch, không lỗi context.
- Object code build ra từ tree này mới **thật sự trùng khớp về mặt logic/byte** với kernel đang chạy → `kpatch-build` mới diff đúng.

### Giai đoạn 7 — Cấu hình lại & chạy `make prepare` trên source tree chuẩn
```bash
cp ~/kpatch-lab/config-6.8.0-134-kpatch .config
make olddefconfig     # lỗi: /bin/sh: flex: not found
apt install -y flex bison bc libelf-dev libssl-dev build-essential dwarves rsync ccache
make olddefconfig
test -f include/config/auto.conf && echo "auto.conf OK"
make prepare
test -f include/config/auto.conf && echo "prepare OK"
make kernelrelease
# 6.8.12+
```
- `make prepare`: sinh toàn bộ header generated (`asm-offsets.h`, `bounds.h`, `utsrelease.h`…) và build các tool phụ trợ nội bộ kernel (`objtool`, `resolve_btfids`, `fixdep`…) — **bắt buộc** trước khi `kpatch-build` có thể build kernel theo source tree đó.
- `make kernelrelease` trả về `6.8.12+`, **khác** với `6.8.0-134-generic` (chuỗi `uname -r` thật). Đây là lý do phải ép `KERNELRELEASE` qua biến môi trường khi gọi `kpatch-build`:
```bash
MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic' kpatch-build \
  -a 6.8.0-134-generic \
  -s ~/kpatch-lab/patches/noble \
  -c ~/kpatch-lab/config-6.8.0-134-kpatch \
  -v ~/kpatch-lab/dbgsym/unsigned-extracted/usr/lib/debug/boot/vmlinux-6.8.0-134-generic \
  -j 4 -n kvm-mmu-livepatch \
  -o ~/kpatch-lab/output-kr134 \
  ~/kpatch-lab/patches/kvm-mmu.patch \
  2>&1 | tee ~/kpatch-lab/kpatch-build-noble.log
```
Nếu không override, `vermagic` của `.ko` sinh ra sẽ mang chuỗi `6.8.12+ ...` thay vì `6.8.0-134-generic ...`, khiến kernel đang chạy **từ chối nạp module** vì không khớp vermagic.

> Lưu ý phát sinh trong lúc `apt install`: hệ thống báo *"Pending kernel upgrade! ... expected kernel version 6.8.0-138-generic"* — tức có bản kernel mới hơn đã sẵn sàng nhưng host **chưa reboot sang** bản đó. Không xử lý (không reboot) để giữ nguyên đúng kernel mục tiêu `134` đang chạy — nếu reboot lúc này, mọi vmlinux/config/source đã chuẩn bị sẽ **không còn khớp** kernel thật đang chạy nữa.

### Giai đoạn 8 — Build thành công, xác minh kết quả
Sau khi build xong (`output-kr134/kvm-mmu-livepatch.ko`), xác minh bằng `modinfo`:
```bash
modinfo -F vermagic ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
# 6.8.0-134-generic SMP preempt mod_unload modversions

modinfo -F vermagic ~/kpatch-lab/output/kvm-mmu-livepatch.ko
# modinfo: ERROR: Module ... not found.   (build ở Giai đoạn 2 chưa từng ra file)
```
`vermagic` của `.ko` (`6.8.0-134-generic SMP preempt mod_unload modversions`) trùng khớp hoàn toàn với chuỗi mà kernel đang chạy mong đợi → module này **đủ điều kiện nhị phân** để nạp vào host.

Bước nạp thực tế (đã thử ở lần build trước đó trong log lịch sử):
```bash
cat /proc/version_signature
kpatch-build     # kiểm tra help/usage
kpatch load ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
dmesg -Tw        # theo dõi log kernel khi patch được nạp
```

---

## 3. Trả lời câu hỏi bài lab

### 3.1. Vật liệu đầu vào cho quá trình build (material)

| # | Vật liệu | Vai trò | Cách lấy đúng |
|---|----------|---------|----------------|
| 1 | **Source tree khớp chính xác ABI** của kernel đang chạy (không phải bản upstream chung chung) | Để `kpatch-build` build lại được nhị phân gốc giống hệt kernel thật, làm cơ sở diff | `git clone --branch Ubuntu-<version>.<abi> ...` từ Launchpad, hoặc `apt-get source` đúng version, khớp `dpkg -l linux-image-$(uname -r)` |
| 2 | **File `.config`** đúng của kernel đang chạy | Quyết định các option biên dịch (SMP, PREEMPT, module versioning…) — phải giống hệt để offset/struct layout khớp | `cp /boot/config-$(uname -r) .config` rồi `make olddefconfig` |
| 3 | **`vmlinux` có debug info (dbgsym/ddeb)** đúng version | `kpatch-build` cần thông tin DWARF để đối chiếu symbol, sinh diff chính xác cấp hàm | Cài `*-dbgsym` package hoặc tải `.ddeb` từ `ddebs.ubuntu.com`, khớp đúng version `-134.134` |
| 4 | **Patch nguồn (`.patch`)** áp sạch (`patch --dry-run` không lỗi) vào đúng source tree ở mục (1) | Nội dung thay đổi thực sự sẽ được đóng gói thành `.ko` | Viết diff `-p1` chuẩn `git diff` format, test dry-run trước khi build |
| 5 | **Toolchain build kernel** (gcc, `flex`, `bison`, `bc`, `libelf-dev`, `libssl-dev`, `dwarves`/`pahole`, `build-essential`) | Biên dịch được cả 2 lần (gốc + đã patch) và sinh BTF | `apt install` các gói tương ứng |
| 6 | **`kpatch`, `kpatch-build`** đã cài trên máy build | Công cụ thực thi toàn bộ quy trình diff + đóng gói `.ko` | `apt install kpatch kpatch-build` |
| 7 | **Kiến trúc & tên kernel mục tiêu (`-a <kernelrelease>`)** | Đảm bảo build đúng arch (x86_64) và gắn đúng `vermagic` mong muốn | Truyền qua flag `-a`, hoặc ép bằng `MAKEFLAGS='KERNELRELEASE=...'` nếu `make kernelrelease` trả về chuỗi khác `uname -r` (ví dụ có hậu tố `+`) |

### 3.2. Điều kiện để `.ko` **nạp được** vào KVM host Lab 1 (runtime)

1. **`vermagic` của `.ko` phải khớp tuyệt đối** với kernel đang chạy trên host — kiểm bằng:
   ```bash
   modinfo -F vermagic module.ko
   cat /proc/version
   ```
   Nếu lệch (kể cả chỉ khác hậu tố như `6.8.12+` so với `6.8.0-134-generic`), kernel sẽ từ chối nạp module (`disagrees about version of symbol` / `no symbol version for ...` / `Invalid module format`).

2. **Kernel đang chạy phải bật hỗ trợ livepatch**: `CONFIG_LIVEPATCH=y` trong `.config` của kernel đang chạy (không phải config dùng để build patch, mà chính kernel `6.8.0-134-generic` trên host phải có tính năng này biên dịch sẵn). Có thể kiểm tra:
   ```bash
   zgrep CONFIG_LIVEPATCH /boot/config-$(uname -r)
   ```

3. **Chính sách ký module (module signing) trên host phải cho phép nạp module chưa ký (hoặc đã ký hợp lệ)**. Vì trong lúc build đã set `SYSTEM_TRUSTED_KEYS=""` (không ký), host thực tế cần:
   - `CONFIG_MODULE_SIG_FORCE` **không** bật cứng trên kernel đang chạy, **hoặc**
   - Secure Boot / kernel lockdown **không** ở chế độ ép buộc chỉ nạp module đã ký bởi khoá tin cậy của hệ thống.
   Nếu host bật `MODULE_SIG_FORCE`/Secure Boot nghiêm ngặt, `.ko` build theo cách trên (không ký) sẽ bị từ chối — khi đó cần ký `.ko` bằng key đã được host tin cậy (enroll qua MOK) trước khi `kpatch load`.

4. **Quyền `root`** trên host để chạy `kpatch load` / `insmod`.

5. **Module phải qua được kiểm tra "consistency" của `kpatch`/`livepatch`**: các hàm bị patch không được đang nằm trong call-stack tại thời điểm nạp (kernel dùng cơ chế kiểm tra stack qua `klp_try_switch_task`) — với patch nhỏ, hàm ngắn như trong bài lab (KVM MMU), rủi ro này thấp nhưng vẫn cần theo dõi `dmesg -Tw` khi `kpatch load` để chắc chắn transition thành công (không bị "stuck"/pending).

6. **Máy build và host chạy đúng phải cùng kiến trúc CPU** (ở đây x86_64) — vì `.ko` là mã máy đã biên dịch sẵn, không phải mã nguồn.

