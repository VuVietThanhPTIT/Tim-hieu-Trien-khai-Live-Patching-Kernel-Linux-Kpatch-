# Nguồn hình ảnh trong bộ tài liệu

Các file ảnh được lưu cục bộ để Markdown vẫn xem được khi không có mạng. Chú thích ngay dưới mỗi hình là nơi cần xem đầu tiên; bảng này là danh mục tập trung để kiểm tra nguồn.

## 1. Hình lấy từ nguồn công khai

| File | Dùng tại | Nguồn | Ghi chú |
|---|---|---|---|
| `redhat-kpatch-ftrace-overview.png` | Chương 01, 03 | [Red Hat User Group Security Update 2022, trang 32](https://people.redhat.com/aludwar/2022-Q2-RHUG-Security-Update.pdf) | Trích một trang slide mô tả kpatch/ftrace; giữ attribution và link nguồn. |
| `linux-kernel-interfaces.svg` | Chương 04 | [Wikimedia Commons — Linux kernel interfaces](https://commons.wikimedia.org/wiki/File:Linux_kernel_interfaces.svg) | CC BY-SA 3.0; xem trang nguồn để biết tác giả và lịch sử đóng góp. |
| `kvm-architecture.png` | Chương 05 | Karen Noel, [KVM: Virtual vs. Physical Machines, trang 4](https://www.linux-kvm.org/images/9/95/KVM_Virtual_vs_Physical.pdf), DevConf.cz 2014 | Trích trang slide kiến trúc KVM. |
| `kvm-run-vmexit-flow.png` | Chương 05 | IIT Bombay CS 695, [Hardware Virtualization — KVM and QEMU, trang 10](https://www.cse.iitb.ac.in/~cs695/slides_pdf/04-hwvirt-kvmqemu.pdf) | Trích trang slide mô tả vòng `KVM_RUN`/VM-exit. |

## 2. Sơ đồ SVG biên soạn riêng

Các sơ đồ dưới đây do bộ tài liệu tự dựng để khớp chính xác với nội dung tiếng Việt. Chúng không sao chép hình của bên thứ ba; kiến thức kỹ thuật được đối chiếu từ [Linux livepatch](https://docs.kernel.org/livepatch/livepatch.html), [Linux ftrace](https://docs.kernel.org/trace/ftrace.html), [KVM API](https://docs.kernel.org/virt/kvm/api.html) và [kpatch](https://github.com/dynup/kpatch).

| File | Nội dung |
|---|---|
| `kpatch-knowledge-map-drawio.svg` | Quan hệ kpatch-build → module → livepatch core → ftrace. |
| `kpatch-build-flow-drawio.svg` | Quy trình từ CVE commit tới transition hoàn tất. |
| `livepatch-transition-state-drawio.svg` | State machine old/new theo từng task. |
| `livepatch-task-routing-drawio.svg` | Ftrace/livepatch handler chọn original hay replacement function. |
| `userspace-kernel-driver-hardware-flow-drawio.svg` | Bốn lớp userspace -> kernel -> driver/subsystem -> hardware. |
| `three-io-paths-drawio.svg` | So sánh cache hit, block I/O qua DMA/interrupt và device `ioctl`. |
| `kvm-fd-ioctl-hierarchy-drawio.svg` | Cây system fd, VM fd, vCPU fd và các ioctl tương ứng. |
| `stalled-transition-decision-tree-drawio.svg` | Cây quyết định xử lý stalled transition. |

## 3. Quy ước khi thêm ảnh

- Ưu tiên tài liệu kernel, dự án upstream, vendor hoặc slide kỹ thuật có tác giả rõ ràng.
- Lưu file trong thư mục này; không hotlink ảnh để tránh link chết hoặc preview phụ thuộc mạng.
- Luôn có alt text, số hình, mô tả ngắn và link tới trang/tài liệu gốc.
- Không dùng hình tìm thấy qua công cụ tìm kiếm nếu không xác định được trang nguồn và quyền sử dụng.
