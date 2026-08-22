

### 3. `/sys` (Sysfs - Hệ thống tệp ảo của thiết bị)

- **WHAT (Nó là cái gì?):** **`/sys`** là một **hệ thống tệp ảo (pseudo-file system / sysfs)** xuất hiện từ nhân Linux 2.6.
- **WHO (Ai quản lý/sử dụng nó?):** Kernel sử dụng `/sys` để xuất cấu trúc thông tin về các **thiết bị phần cứng (devices)** và trình điều khiển (drivers) ra userspace. Các tiến trình quản trị hệ thống như trình quản lý thiết bị `udev` dựa hoàn toàn vào `/sys` để phát hiện và cấu hình thiết bị cắm vào máy.
- **WHERE (Nó nằm ở đâu?):** Được mount tại thư mục `/sys`.
- **WHEN (Khi nào nó hoạt động?):** Được mount tự động khi hệ thống khởi động. Nó cập nhật liên tục thời gian thực mỗi khi có phần cứng mới được kết nối hoặc ngắt kết nối khỏi máy chủ.
- **WHY (Tại sao phải cần nó?):** Trước đây, `/proc` bị quá tải do phải gánh cả thông tin tiến trình lẫn thiết bị phần cứng, dẫn đến sự lộn xộn. `/sys` ra đời để chuyên biệt hóa nhiệm vụ **quản lý cấu trúc cây thiết bị phần cứng**, tách biệt hoàn toàn khỏi nhiệm vụ quản lý tiến trình của `/proc`.
- **HOW (Nó hoạt động như thế nào?):** Nhân Linux tổ chức các thiết bị phần cứng theo mô hình phân cấp (bus, class, power...). Khi một thiết bị được cắm vào, driver tương ứng đăng ký với kernel, kernel lập tức tạo ra các thư mục và tệp tin tương ứng trong `/sys`. Userspace có thể đọc các tệp này để biết trạng thái thiết bị, hoặc ghi thông số cấu hình để thay đổi hành vi phần cứng (như đổi chế độ tiết kiệm pin).
