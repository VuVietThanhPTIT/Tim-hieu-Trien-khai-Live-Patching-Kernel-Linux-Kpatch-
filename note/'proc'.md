
### 2. `/proc` (Procfs - Hệ thống tệp ảo của tiến trình)

- **WHAT (Nó là cái gì?):** **`/proc`** là một **hệ thống tệp ảo (virtual file system / procfs)**. Các tệp và thư mục trong `/proc` không thực sự tồn tại trên ổ cứng vật lý; kernel tạo ra chúng một cách "động" (on the fly) trực tiếp trên bộ nhớ RAM khi tiến trình truy cập vào.
- **WHO (Ai quản lý/sử dụng nó?):** Kernel Linux quản lý và phơi bày các dữ liệu nội bộ của mình thông qua `/proc`. Cả người dùng (qua dòng lệnh như `cat`, `echo`, `ps`) và các tiến trình ứng dụng đều sử dụng nó để giám sát hệ thống.
- **WHERE (Nó nằm ở đâu?):** Nó được gắn kết (mount) trực tiếp tại thư mục `/proc` trên cây thư mục gốc.
- **WHEN (Khi nào nó xuất hiện và thay đổi?):**
    - Nó xuất hiện ngay khi hệ điều hành Linux khởi động và mount hệ thống tệp `procfs`.
    - Các thư mục con dạng `/proc/PID` (như `/proc/1`) mang tính chất tạm thời (volatile): chúng tự động sinh ra khi một tiến trình có ID tương ứng được tạo và bốc hơi hoàn toàn khi tiến trình đó kết thúc.
- **WHY (Tại sao phải cần nó?):** Cung cấp một giao diện chuẩn hóa, an toàn và dễ đọc (dạng văn bản thuần túy) để userspace có thể truy vấn trạng thái hệ thống và cấu hình kernel mà không cần phải thực hiện các lệnh can thiệp thô bạo vào bộ nhớ Ring 0.
- **HOW (Nó hoạt động như thế nào?):** Khi bạn gõ lệnh `cat /proc/meminfo`, kernel sẽ chặn thao tác đọc này, truy xuất cấu trúc dữ liệu quản lý bộ nhớ trong RAM, chuyển thông tin đó thành văn bản thường và trả về cho bạn. Bạn cũng có thể cấu hình kernel (nếu có đặc quyền) bằng cách ghi vào các file trong `/proc/sys` (ví dụ: thay đổi số lượng PID tối đa qua `/proc/sys/kernel/pid_max`).

