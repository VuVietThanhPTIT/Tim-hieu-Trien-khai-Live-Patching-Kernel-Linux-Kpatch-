# 07 – Cài đặt, build và sử dụng kpatch: runbook kỹ thuật

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [1. Mục tiêu, pre-flight và sizing môi trường build](#1-mục-tiêu-pre-flight-và-sizing-môi-trường-build)
3. [2. Cài đặt công cụ và chuẩn bị đúng kernel material](#2-cài-đặt-công-cụ-và-chuẩn-bị-đúng-kernel-material)
4. [3. Build patch và kiểm tra livepatch module](#3-build-patch-và-kiểm-tra-livepatch-module)
5. [4. Load, monitor, unload và persistent installation](#4-load-monitor-unload-và-persistent-installation)
6. [5. Catalogue lỗi thường gặp và checklist trước khi load](#5-catalogue-lỗi-thường-gặp-và-checklist-trước-khi-load)
7. [6. Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **Runbook** | Technical Operational Guide | Tài liệu quy trình kỹ thuật chuẩn hướng dẫn các bước thực thi từ chuẩn bị đến vận hành. |
| **Pre-flight** | Pre-flight Checks | Bước kiểm tra tiền điều kiện (môi trường, dung lượng, kernel release, config) trước khi thực hiện thao tác chính. |
| **kpatch load / unload** | CLI Lifecycle Commands | Các lệnh CLI của kpatch dùng để đăng ký kích hoạt hoặc hủy đăng ký gỡ livepatch module khỏi kernel đang chạy. |
| **dmesg** | Display Message | Câu lệnh xem buffer nhật ký hệ thống kernel (kernel ring buffer log). |

## Runbook từ chuẩn bị đến load/unload

```text
PRE-FLIGHT
  |
  v
Dependencies + kpatch
  |
  v
Exact kernel source
  |
  +--> matching config
  |
  +--> exact vmlinux/debuginfo
  |
  v
Source patch + dry-run
  |
  v
kpatch-build
  |
  v
Verify .ko
  |
  v
kpatch load
  |
  v
monitor transition / workload
  |
  +--> success: keep/monitor
  |
  +--> problem: unload/recovery/fallback
```

## 1. Mục tiêu, pre-flight và sizing môi trường build

**Mục tiêu runbook**

File này trả lời theo format vận hành:

```text
Prerequisites → Prepare → Build → Verify → Load → Observe → Unload → Troubleshoot
```

> **Lưu ý:** command chính xác phụ thuộc distro/kernel. Luôn đọc `kpatch --help`, `kpatch-build --help` và vendor documentation trên target.

---

**Pre-flight**

```bash
uname -r
uname -m
cat /proc/version
```

Kiểm tra config:

```bash
grep -E 'CONFIG_LIVEPATCH|CONFIG_FUNCTION_TRACER|CONFIG_DYNAMIC_FTRACE|CONFIG_MODVERSIONS' \
  /boot/config-$(uname -r)
```

Tối thiểu cần kernel livepatch/ftrace support phù hợp.

---

**Disk/RAM/toolchain**

Kpatch build có thể tốn nhiều GB disk và compile lâu. Official install guide lưu ý chuẩn bị khoảng 15 GB cache cho nhiều distro; source/debug package riêng có thể làm tổng nhu cầu lớn hơn.

```bash
df -h
free -h
gcc --version
make --version
```

---

## 2. Cài đặt công cụ và chuẩn bị đúng kernel material

**Cài dependencies và kpatch**

Ví dụ source install:

```bash
git clone https://github.com/dynup/kpatch.git
cd kpatch
make
sudo make install
```

Verify:

```bash
kpatch --help
kpatch-build --help
kpatch version
```

---

**Chuẩn bị exact kernel source**

Không chỉ lấy “Linux 6.8 source”. Cần đúng distro package/ABI context.

```text
[ ] package version đúng
[ ] source patch apply được
[ ] config từ host target
[ ] generated files/certs handled
```

---

**Chuẩn bị config**

```bash
cp /boot/config-$(uname -r) .config
make olddefconfig
```

Distro source có thể reference signing cert file không có trong source package. Nếu lab cần neutralize cert path để build, phải ghi rõ đây là **build deviation**, không coi đó là production signing design.

---

**Chuẩn bị exact `vmlinux` / debug symbols**

Target cần unstripped/debug binary tương ứng kernel thực tế.

```bash
strings /path/to/vmlinux-$(uname -r) | grep -m1 '^Linux version'
```

Trên Ubuntu historical build, artifact có thể phải lấy từ ddebs/Launchpad thay vì apt index hiện tại.

---

**Chuẩn bị source patch**

```bash
patch -p1 --dry-run < fix.patch
```

Nếu có reject, dừng. Không ép patch bằng fuzz rồi coi như exact target.

---

## 3. Build patch và kiểm tra livepatch module

**Build command pattern**

Ví dụ kiểu đã dùng trong lab:

```bash
MAKEFLAGS='KERNELRELEASE=6.8.0-134-generic' \
kpatch-build \
  -a 6.8.0-134-generic \
  -s /path/to/kernel-source \
  -c /path/to/config \
  -v /path/to/vmlinux \
  -j 4 \
  -n patch-name \
  -o /path/to/output \
  fix.patch
```

Option có thể thay đổi theo kpatch version. Dùng `--help` của binary đang cài làm source of truth.

---

**Đọc output build**

Tìm:

```text
Building original source
Building patched source
Extracting new and modified ELF sections
changed function: ...
new function: ...
Patched objects: ...
Building patch module: ...
SUCCESS
```

Nếu changed functions khác kỳ vọng, không load ngay.

---

**Verify `.ko`**

```bash
ls -lh output/*.ko
modinfo output/patch.ko
modinfo -F vermagic output/patch.ko
readelf -SW output/patch.ko | grep -E 'kpatch|klp|__versions'
```

So sánh:

```bash
uname -r
```

---

## 4. Load, monitor, unload và persistent installation

**Load**

```bash
sudo kpatch load /path/to/patch.ko
```

Song song:

```bash
sudo dmesg -wT
```

Sau load:

```bash
kpatch list
ls /sys/kernel/livepatch
cat /sys/kernel/livepatch/<patch>/enabled
cat /sys/kernel/livepatch/<patch>/transition
```

Stable state mong đợi:

```text
enabled=1
transition=0
```

---

**Monitor per-task state khi transition lâu**

```bash
for f in /proc/*/task/*/patch_state; do
  [ -r "$f" ] || continue
  echo "$f $(cat "$f")"
done
```

Thread identity:

```bash
ps -T -p <PID>
```

Stack:

```bash
sudo cat /proc/<PID>/task/<TID>/stack
```

---

**Unload / rollback**

```bash
sudo kpatch unload <patch_name>
```

Unloading cũng phải qua reverse transition.

Stable final state:

```text
patch không còn trong kpatch list
/sys/kernel/livepatch/<patch> biến mất
```

---

**Install persistent patch**

`kpatch install` và boot-time behavior phụ thuộc distro/tooling.

```text
load    = runtime hiện tại
install = cấu hình artifact để load theo lifecycle tương ứng
```

---

## 5. Catalogue lỗi thường gặp và checklist trước khi load

**Common errors – catalogue**

**A. Patch reject**

```text
Hunk FAILED
```

→ source mismatch hoặc patch context sai.

**B. Canonical cert missing**

```text
No rule to make target debian/canonical-certs.pem
```

→ distro packaging dependency; xử lý build config có chủ đích.

**C. Kernelrelease mismatch**

```text
source make kernelrelease = 6.8.12
host = 6.8.0-134-generic
```

→ distro ABI/version injection khác raw source.

**D. Vermagic mismatch**

→ không load trước khi hiểu và sửa target build identity.

**E. Unsupported jump labels**

→ patch function có static-key/jump-label issue; redesign patch hoặc dùng supported approach.

**F. Module signing warning**

→ có thể taint kernel nhưng chưa chắc load fail; production cần signing policy.

**G. Transition stall**

→ sang file 09.

---

**Golden checklist trước `kpatch load`**

```text
[ ] uname -r đúng target
[ ] patch dry-run sạch
[ ] exact source/package
[ ] exact config
[ ] exact vmlinux/debug symbols
[ ] compiler/toolchain hợp lý
[ ] changed functions reviewed
[ ] vermagic khớp
[ ] livepatch sections tồn tại
[ ] dmesg monitor đã mở
[ ] workload baseline đã có
[ ] rollback/fallback đã chuẩn bị
```

---

## 6. Tài liệu tham khảo

- https://github.com/dynup/kpatch/blob/master/doc/INSTALL.md
- https://github.com/dynup/kpatch/blob/master/man/kpatch.1
- https://github.com/dynup/kpatch/blob/master/man/kpatch-build.1
