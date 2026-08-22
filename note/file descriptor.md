

### 1. FILE DESCRIPTOR (FD - Bộ mô tả tệp tin)

- **WHAT (Nó là cái gì?):** **File descriptor** là một số nguyên không âm (thường là số nhỏ) đại diện cho một tệp tin hoặc tài nguyên I/O đang mở trong hệ thống.
- **WHO (Ai quản lý/sử dụng nó?):** Kernel duy trì một bảng FD riêng cho **từng tiến trình** (per-process FD table). Tiến trình ở userspace sử dụng số FD này làm tham chiếu để thực hiện các thao tác đọc/ghi thông qua các system call mà không cần quan tâm đến cấu trúc dữ liệu phức tạp của tệp tin ở tầng kernel.
- **WHERE (Nó nằm ở đâu?):**
    - Bảng FD của tiến trình nằm hoàn toàn trong **vùng nhớ bảo vệ của Kernel Space**.
    - Khi ứng dụng chạy, 3 FD mặc định luôn được mở sẵn bởi Shell: `0` (**stdin** - nhập liệu tiêu chuẩn), `1` (**stdout** - xuất tiêu chuẩn), và `2` (**stderr** - xuất lỗi tiêu chuẩn).
- **WHEN (Khi nào nó được tạo ra và biến mất?):**
    - **Tạo ra:** Khi tiến trình gọi các system call như `open()`, `pipe()`, `socket()`, hoặc `dup()`.
    - **Biến mất:** Khi tiến trình gọi lệnh `close(fd)` hoặc khi tiến trình kết thúc, kernel sẽ tự động giải phóng FD đó cùng các tài nguyên liên quan.
- **WHY (Tại sao phải cần nó?):** Để hiện thực hóa triết lý UNIX _"Tất cả mọi thứ đều là tệp tin"_ (Everything is a file). Nhờ FD, mọi tài nguyên từ file vật lý trên đĩa, thư mục, thiết bị phần cứng, đường ống Pipe, cho đến kết nối mạng Socket đều được đồng nhất dưới một giao diện I/O duy nhất.
- **HOW (Nó hoạt động như thế nào?):** Khi tiến trình gọi `read(fd, buf, count)`, kernel sử dụng số nguyên `fd` này để tra cứu vào bảng FD của tiến trình đó, tìm kiếm con trỏ tham chiếu đến **Bảng mô tả file đang mở toàn hệ thống** (Open file description table), từ đó xác định vị trí đọc/ghi hiện tại (offset) và thực hiện đọc dữ liệu.
	i