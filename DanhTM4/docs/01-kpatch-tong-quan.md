# 01. Tổng quan về kpatch

## 1. Bài toán kpatch giải quyết

Kernel thông thường được cập nhật bằng cách cài kernel mới và reboot. Với compute host đang chứa nhiều VM, reboot kéo theo migrate VM hoặc downtime. kpatch cho phép thay một số hàm trong **kernel đang chạy** mà không reboot kernel và không restart process.

Live patch phù hợp nhất với bản vá bảo mật hoặc bug fix nhỏ, cục bộ. Nó **không phải** cơ chế nâng cấp kernel tổng quát và không bảo đảm mọi CVE đều live-patch được.

![Cơ chế kpatch dùng ftrace chuyển lời gọi từ hàm gốc sang hàm thay thế](images/redhat-kpatch-ftrace-overview.png)

*Hình 1 — kpatch đăng ký code thay thế và ftrace chuyển hướng lời gọi hàm.*

## 2. Ba thành phần của kpatch

### 2.1. `kpatch-build`

Nhận source patch, build hai phiên bản:

- kernel/object gốc;
- kernel/object sau khi áp source patch.

Sau đó công cụ so sánh binary để tìm hàm thay đổi, kiểm tra một số điều kiện patchability, trích code và relocation cần thiết rồi link thành livepatch module.

### 2.2. Livepatch module `.ko`

Module chứa:

- phiên bản mới của các hàm cần thay;
- metadata ánh xạ object/hàm cũ với hàm mới;
- relocation để code mới tham chiếu symbol của kernel đang chạy;
- callback trước/sau patch nếu bản vá cần chuyển đổi trạng thái dữ liệu.

Đây là module dành cho **đúng kernel mục tiêu**. Không được coi một module build cho kernel A là dùng được cho kernel B chỉ vì cùng major/minor.

### 2.3. Lệnh `kpatch`

CLI dùng để quản lý module:

```bash
kpatch list
kpatch info patch.ko
sudo kpatch load patch.ko
sudo kpatch unload patch.ko
sudo kpatch install patch.ko
sudo kpatch uninstall patch.ko
sudo kpatch signal
```

- `load`: áp vào kernel hiện đang chạy.
- `install`: lưu patch để có thể tự load khi boot lại vào đúng kernel tương ứng.
- `unload`: disable patch, đợi reverse transition hoàn tất rồi gỡ module nếu an toàn.
- `signal`: “poke” các task còn làm transition bị kẹt trên kernel có giao diện hỗ trợ.

Không suy ra production syntax từ tài liệu chung; hãy đọc `kpatch --help`, `man kpatch` và package của distro đích.

## 3. Luồng từ source patch tới code đang chạy

![Luồng build và load live patch bằng kpatch](images/kpatch-build-flow-drawio.svg)

*Hình 2 — từ commit sửa CVE tới livepatch module và trạng thái `transition=0`*

Kpatch hoạt động ở **function granularity**: thay toàn bộ implementation của hàm thay đổi. Nó không đơn giản chép vài byte của source diff vào RAM.

## 4. Vòng đời khi load

1. Kernel module loader nạp `.ko`, resolve symbol và relocation.
2. Module đăng ký `struct klp_patch`, các object và function với livepatch core.
3. Core tạo entry trong `/sys/kernel/livepatch/<patch>/`.
4. Core đăng ký ftrace handler cho hàm cần thay.
5. Patch vào transition: từng task được chuyển sang patched state khi an toàn.
6. Khi tất cả task đã hội tụ, `transition` từ `1` về `0`.

Trong transition, task A có thể dùng code mới còn task B vẫn dùng code cũ. Consistency model phải bảo đảm mỗi task thấy một tập hàm nhất quán; chi tiết nằm ở [02-transition-safe-state.md](02-transition-safe-state.md).

## 5. Điều kpatch làm được và không làm được

### Thường thuận lợi

- Thêm kiểm tra bounds, NULL hoặc quyền truy cập.
- Sửa calculation/race cục bộ mà không đổi interface hay lifetime dữ liệu.
- Thay logic bên trong một hoặc vài hàm có ftrace entry.

### Cần phân tích đặc biệt hoặc có thể không phù hợp

| Loại thay đổi | Rủi ro |
|---|---|
| Đổi layout/kích thước `struct` đang tồn tại | Object cũ và code mới có thể hiểu memory khác nhau. |
| Đổi ý nghĩa của dữ liệu dùng chung | Task chạy code cũ và mới có thể diễn giải cùng dữ liệu khác nhau. |
| Đổi prototype/exported ABI | Caller hoặc module khác vẫn gọi theo ABI cũ. |
| Sửa `__init`, module/device initialization | Code init có thể đã chạy và không chạy lại. |
| Hàm inline | Code đã được copy vào nhiều caller; phải xác định mọi caller bị ảnh hưởng. |
| Assembly hoặc hàm không có ftrace entry | Không có điểm redirect phù hợp. |
| `notrace`, bản thân ftrace/livepatch | Tránh vòng lặp và xung đột nội bộ nên không patch được theo cách thường. |
| Static key/jump label, alternatives | Code trong patch module có thể không phản ánh trạng thái runtime nếu xử lý sai. |
| Thay đổi lock ordering nhiều hàm | Task trộn semantics cũ/mới có thể deadlock hoặc phá invariant. |
| Thay data table, per-CPU data, hardware init | Function replacement đơn thuần có thể chưa đủ. |

Kpatch có callback và Linux livepatch có shadow variable để xử lý một số thay đổi data, nhưng đây là thiết kế patch chuyên sâu, không phải cơ chế tự động.

## 6. Build thành công chưa đồng nghĩa an toàn

`kpatch-build SUCCESS` chủ yếu chứng minh công cụ tạo được module theo những gì nó phát hiện. Nó không thể tự chứng minh:

- patch giữ nguyên mọi invariant và locking semantics;
- mọi hàm inline liên quan đã được đưa vào module;
- object sống từ trước tương thích với code mới;
- workload KVM thực tế không đi vào đường code chưa test;
- transition chắc chắn hội tụ trên host production.

Do đó phải có ba lớp kiểm tra:

1. **Source review:** hiểu upstream fix và toàn bộ semantic change.
2. **Binary/livepatch review:** xem danh sách hàm thực sự thay, warning của build, symbol/relocation.
3. **Runtime validation:** load/unload, stress, VM lifecycle, live migration, I/O, CPU virtualization và tình huống stalled transition.

## 7. Liên hệ trực tiếp với task cloud/KVM

Khi nhận một CVE KVM, bốn câu hỏi đầu tiên là:

1. Fix sửa hàm nào và hàm đó thuộc `vmlinux`, `kvm`, `kvm_intel` hay `kvm_amd`?
2. Fix có đổi struct, data dùng chung, inline/assembly hoặc init code không?
3. Code cũ và mới có thể cùng tồn tại trong lúc các vCPU thread chuyển state không?
4. Danh sách hàm do `kpatch-build` phát hiện có đúng với source review không?

“Zero downtime” ở đây nên hiểu là **không reboot host và không chủ động restart workload trong đường thành công**. Nó không có nghĩa:

- mọi bản vá đều áp được;
- không bao giờ có latency spike;
- không cần canary, rollback hoặc phương án migrate;
- có thể `force` transition mà không ảnh hưởng VM.

Nếu transition bị kẹt bởi QEMU/vCPU thread, thao tác stop/continue hoặc restart process có thể làm VM pause hoặc chết. Vì vậy zero downtime là ràng buộc phải được đưa vào quyết định xử lý, không phải đặc tính tự động của kpatch.

## 8. Nguồn đọc thêm

- [kpatch README: components, build flow, limitations](https://github.com/dynup/kpatch/blob/master/README.md)
- [kpatch Patch Author Guide](https://github.com/dynup/kpatch/blob/master/doc/patch-author-guide.md)
- [Linux kernel: Livepatch life-cycle](https://docs.kernel.org/livepatch/livepatch.html)
- [Red Hat: limitations and process of kpatch](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/7/html/kernel_administration_guide/applying_patches_with_kernel_live_patching)
