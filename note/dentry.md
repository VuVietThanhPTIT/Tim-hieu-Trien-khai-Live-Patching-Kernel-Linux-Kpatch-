[[Virtual file system]]
**dentry khác giống với concept của dns** 
## 5W1H VỀ DENTRY (DIRECTORY ENTRY)

### 1. WHAT (Nó là cái gì?)

**Dentry (Directory Entry)** là một cấu trúc dữ liệu ảo (được định nghĩa là `struct dentry` trong mã nguồn kernel Linux) thuộc lớp Virtual File System (VFS).

- Nó đại diện cho một **thành phần cấu thành nên đường dẫn** (pathname component) của tệp tin. Thành phần này có thể là thư mục gốc (`/`), thư mục con (như `etc`, `var`), một file thường (như `passwd`), hay một liên kết (symlink/hardlink).
- Nói một cách đơn giản: **Dentry chính là sự kết dính giữa "Tên gọi" (String) và "Số hiệu định danh" (Inode) của file.**

### 2. WHO (Ai quản lý và sử dụng nó?)

- **Kernel (VFS):** Là thực thể duy nhất tạo ra, quản lý, duy trì và giải phóng các đối tượng dentry trong bộ nhớ.
- **Userspace (Ứng dụng/Tiến trình):** **Không** thể nhìn thấy hay can thiệp trực tiếp vào cấu trúc dentry. Khi bạn viết code và gọi các hàm như `open("/etc/passwd")`, bạn chỉ cung cấp một chuỗi ký tự đường dẫn. VFS của kernel sẽ tự động đứng ra phân giải chuỗi này thành các dentry tương ứng ở bên dưới.

### 3. WHERE (Nó nằm ở đâu?)

- Dentry nằm hoàn toàn trong **Kernel Space (RAM)** dưới dạng các cấu trúc dữ liệu động.
- Để tránh việc phải tìm kiếm trên đĩa cứng chậm chạp, kernel lưu trữ các dentry được truy cập gần đây trong một bộ đệm RAM cực nhanh gọi là **Dentry Cache (dcache)**.
- _Lưu ý quan trọng:_ Dentry **không được lưu trữ vật lý trên ổ đĩa** (không giống như Inode hay Data Blocks vốn được ghi xuống đĩa). Dentry chỉ được sinh ra trong RAM khi hệ thống hoạt động để phục vụ cho việc duyệt thư mục.

### 4. WHEN (Khi nào nó được tạo ra, sử dụng và biến mất?)
$$\text{File Descriptor (Số nguyên)} \xrightarrow{\text{chỉ mục}} \text{File Object (Open File Description)} \xrightarrow{\text{trỏ tới}} \text{Dentry Object} \xrightarrow{\text{trỏ tới}} \text{Inode Object}$$
- **Được tạo ra/Sử dụng:** Khi một tiến trình thực hiện thao tác liên quan đến đường dẫn (ví dụ: mở file, tạo thư mục, kiểm tra thuộc tính file). Lúc này, kernel sẽ thực hiện quá trình **Phân giải đường dẫn (Pathname Resolution)**: Duyệt qua từng thành phần từ gốc `/` đi xuống, tìm kiếm dentry tương ứng trong dcache. Nếu không có (Cache Miss), kernel sẽ đọc từ đĩa, tạo ra dentry mới và nạp vào dcache.
- **Biến mất:** Khi bộ nhớ RAM của hệ thống bị cạn kiệt, một cơ chế dọn dẹp của kernel (shrink_dcache) sẽ tự động giải phóng các dentry không còn tiến trình nào sử dụng (độ đếm tham chiếu `d_count` bằng 0) để thu hồi RAM.

### 5. WHY (Tại sao phải cần đến nó?)

Sự ra đời của dentry giải quyết hai bài toán chí mạng của hệ thống tệp UNIX/Linux:

- **Tách biệt Tên file khỏi Inode:** Trong hệ thống tệp UNIX, cấu trúc `inode` (lưu siêu dữ liệu của file) hoàn toàn **không lưu tên file**. Inode chỉ quan tâm đến các thuộc tính vật lý và vị trí lưu trữ. Do đó, cần có một đối tượng trung gian (Dentry) để ánh xạ tên file (userspace dễ đọc) sang số hiệu inode (kernel dễ quản lý). Nhờ có dentry, một inode mới có thể có nhiều tên gọi khác nhau (Hard Link).
- **Tối ưu hóa hiệu năng vượt trội:** Việc đọc cấu trúc thư mục từ ổ cứng vật lý để tìm file cực kỳ tốn kém thời gian I/O. Nhờ dcache lưu sẵn các dentry trong RAM, kernel có thể tìm ra file gần như ngay lập tức mà không cần chạm vào ổ đĩa.

### 6. HOW (Nó hoạt động như thế nào?)

Mỗi đối tượng dentry (`struct dentry`) được tổ chức liên kết với nhau để tạo thành một **"Bản đồ cây thư mục ảo"** trong bộ nhớ RAM thông qua các con trỏ:

- `d_name`: Lưu tên của thành phần (ví dụ: chuỗi "passwd").
- `d_inode`: Con trỏ trỏ tới cấu trúc **Inode** chứa dữ liệu thực tế.
- `d_parent`: Con trỏ trỏ ngược về dentry của thư mục cha (giúp dịch chuyển ngược dòng, ví dụ từ file `passwd` tìm về thư mục cha `etc`).
- `d_subdirs`: Danh sách liên kết chứa các dentry con (nếu dentry hiện tại là một thư mục).
- `d_op`: Bảng các con trỏ hàm (dentry operations) để thực hiện các thao tác đặc thù (như so sánh tên file, kiểm tra tính hợp lệ của dentry).

---

## CÂU HỎI CHUYÊN SÂU: "DENTRY ÂM" (NEGATIVE DENTRY) LÀ GÌ VÀ SỨC MẠNH CỦA NÓ?

Có một kịch bản rất thú vị: **Điều gì xảy ra khi bạn cố tình mở một file không hề tồn tại trên hệ thống (ví dụ: `/etc/file_ao.txt`)?**

1. Hệ thống sẽ thực hiện phân giải đường dẫn và dĩ nhiên là không tìm thấy file này trên đĩa. Nó trả về lỗi `ENOENT` (No such file or directory).
2. Tuy nhiên, thay vì không làm gì cả, kernel sẽ tạo ra một dentry đặc biệt gọi là **Negative Dentry (Dentry âm)** cho tên file `file_ao.txt`.
3. Cấu trúc của Negative Dentry này là: Trường `d_name` vẫn lưu `"file_ao.txt"`, nhưng trường con trỏ `d_inode` được đặt bằng **`NULL`**.
4. **Tác dụng:** Nếu ứng dụng của bạn (hoặc một kẻ tấn công) liên tục gọi lệnh mở file không tồn tại này (tấn công DDoS hoặc lỗi vòng lặp code), kernel chỉ cần tra cứu dcache, thấy ngay dentry này trỏ tới `NULL` và lập tức trả về lỗi lập tức. Kernel không cần phải tốn bất kỳ một vòng quay ổ đĩa nào để kiểm tra sự tồn tại của file nữa.

---

