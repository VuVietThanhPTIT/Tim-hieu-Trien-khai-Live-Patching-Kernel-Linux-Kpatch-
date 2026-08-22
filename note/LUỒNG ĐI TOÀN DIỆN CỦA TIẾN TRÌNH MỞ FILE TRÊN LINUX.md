  
## 1. Mô Hình Kiến Trúc Liên Kết Chuẩn Xác trong VFS

  

Lớp **Virtual File System (VFS)** của Linux quản lý việc mở file thông qua một chuỗi liên kết đối tượng gián tiếp chặt chẽ [130, 315]. Chuỗi này phân tách rõ ràng giữa trạng thái động của phiên làm việc (session state) và trạng thái tĩnh của dữ liệu vật lý (storage state):

  

$$\text{File Descriptor (Số nguyên)} \xrightarrow{\text{Chỉ mục}} \text{File Object (struct file)} \xrightarrow{\text{Trỏ tới}} \text{Dentry Object (struct dentry)} \xrightarrow{\text{Trỏ tới}} \text{Inode Object (struct inode)}$$

  

### Chi tiết các thực thể trong chuỗi liên kết:

  

1. **File Descriptor (FD - Bộ mô tả tệp):**

   - **Bản chất:** Là một số nguyên không âm nhỏ (ví dụ: `0`, `1`, `2`, `3`) [73, 273].

   - **Cấp độ quản lý:** Cục bộ, riêng biệt cho từng tiến trình (per-process FD table) [73, 273].

   - **Vai trò:** Hoạt động như một chỉ số (index) để tra cứu vào bảng quản lý tệp tin của tiến trình [87, 273].

  

2. **File Object (Đối tượng tệp tin đang mở - `struct file`):**  File structure hay chính là cái tấm vé

   - **Bản chất:** Đại diện cho một **phiên mở file** (an open file description) [88, 274].

   - **Cấp độ quản lý:** Toàn cục trong nhân hệ điều hành (system-wide open file table) [88, 274].

   - **Thông tin lưu trữ:** Lưu trữ các trạng thái động tại thời điểm chạy: vị trí con trỏ đọc/ghi hiện tại (`f_pos`), các cờ mở file (`O_RDONLY`, `O_WRONLY`, `O_APPEND`...) và quyền hạn mở [88, 274].

   - **Liên kết:** Trỏ tới cấu trúc `dentry` tương ứng của file đó [42, 275]. *(Lưu ý: Kernel hiện đại sao chép thêm một con trỏ trực tiếp `f_inode` từ dentry sang file object để tối ưu hóa tốc độ truy cập inode mà không cần nhảy qua dentry)*.

  

3. **Dentry Object (Directory Entry - `struct dentry`):**

   - **Bản chất:** Đại diện cho một **thành phần trong đường dẫn** tệp tin (một nút trên cây thư mục ảo) [41, 336].

   - **Cấp độ quản lý:** Toàn cục trong bộ nhớ RAM [41, 336].

   - **Thông tin lưu trữ:** Liên kết giữa tên tệp dạng chuỗi ký tự (`d_name` như "passwd", "app.log") với số hiệu `inode` vật lý của nó [30, 41]. Nó cũng giữ các con trỏ trỏ đến dentry cha (`d_parent`) và các dentry con (`d_subdirs`) [41].

   - **Đặc điểm vật lý:** **Không được lưu trữ trên ổ đĩa**, chỉ tồn tại trong RAM. Kernel duy trì một bộ nhớ đệm gọi là **Dentry Cache (dcache)** để tránh việc phải quét đĩa cứng tìm file một cách chậm chạp [41].

  

4. **Inode Object (Index Node - `struct inode`):**

   - **Bản chất:** Đại diện cho **thể tệp tin vật lý** thực sự [23, 310].

   - **Cấp độ quản lý:** Toàn cục [23, 275].

   - **Thông tin lưu trữ:** Chứa toàn bộ siêu dữ liệu (metadata) tĩnh của file: loại file (file thường, thư mục, socket, device), kích thước file, chủ sở hữu (UID/GID), quyền hạn truy cập (permissions), các mốc thời gian (timestamps) và quan trọng nhất là danh sách các con trỏ trỏ tới các khối dữ liệu (data blocks) thực tế trên ổ đĩa [24, 25, 275, 310, 311].

   - **Đặc điểm vật lý:** Được lưu trữ cố định trên ổ đĩa dưới dạng một bảng inode (inode list) và được nạp vào RAM (in-memory inode) khi có tiến trình truy cập [27, 90, 276, 309]. **Bản thân inode hoàn toàn không chứa tên file** [160, 200, 348, 387].

  

---

  

## 2. Hành Trình Từng Bước: Tiến Trình Mở File `/var/log/app.log`

  

Khi tiến trình của bạn thực hiện lời gọi mở tệp tin ở chế độ chỉ đọc (`O_RDONLY`), hệ điều hành sẽ kích hoạt một chuỗi các bước chuyển dịch trạng thái an toàn:

  

### Bước 1: Khởi động tại Userspace (Ring 3)

Ứng dụng ở Userspace gọi hàm thư viện chuẩn:

```c

int fd = open("/var/log/app.log", O_RDONLY);

```

Tại thời điểm này, chương trình chưa có quyền hạn thao tác với ổ đĩa cứng.

  

### Bước 2: glibc biên dịch và kích hoạt Trực di chuyển (Syscall Wrapper)

Thư viện chuẩn C (`glibc`) đóng gói lời gọi:

1. Nhận chuỗi đường dẫn và cờ chế độ [74, 259].

2. Nạp số hiệu system call `openat` (số **`257`** trên x86-64) vào thanh ghi `%rax` [68, 254].

3. Sao chép các tham số đường dẫn và cờ vào các thanh ghi truyền trạng thái (`%rdi`, `%rsi`) [68, 254].

4. Gọi lệnh máy **`syscall`** để kích hoạt bẫy phần cứng (Trap) [68, 70, 254, 256].

  

### Bước 3: Kernel Entry & Phân phối cuộc gọi (Ring 0)

Bộ vi xử lý chuyển mức đặc quyền từ **Ring 3 lên Ring 0** [255]. CPU nhảy tới điểm nhập assembly **`entry_SYSCALL_64`** đã được đăng ký trước [68]:

1. Thực hiện lệnh `swapgs` và `push` toàn bộ các thanh ghi của tiến trình lên **Kernel Stack** của tiến trình đó để đóng băng trạng thái của ứng dụng [68, 254].

2. Sử dụng số hiệu `257` trong `%rax` để tra bảng **`sys_call_table`**, xác định hàm dịch vụ ngôn ngữ C cần gọi là **`sys_openat()`** [68, 69, 254].

  

### Bước 4: VFS Phân giải đường dẫn (Pathname Resolution)

Bên trong `sys_openat()`, kernel bắt đầu duyệt tìm file trên cấu trúc cây của VFS [62, 131, 247, 316]:

1. Sao chép an toàn chuỗi đường dẫn từ bộ nhớ người dùng sang bộ nhớ của nhân (`getname()`) [68, 254].

2. VFS thực hiện duyệt cây thư mục ảo bắt đầu từ thư mục gốc `/` (có inode mặc định là inode số 2 trên hệ thống tệp UNIX) [159, 347]:

   - Tra cứu trong **Dentry Cache (dcache)** để tìm dentry `/` $\rightarrow$ tìm dentry `var` nằm trong `/`.

   - Tiếp tục tìm dentry `log` nằm trong `var`.

   - Cuối cùng tìm dentry `app.log` nằm trong `log` [41].

3. Nếu xảy ra hiện tượng Cache Miss (không tìm thấy dentry trong RAM), kernel buộc phải gọi driver hệ thống tệp (ví dụ: ext4) đọc cấu trúc danh sách tệp tin lưu trên đĩa cứng để nạp thông tin, tạo dentry mới và đưa vào dcache [33, 41, 333].

4. VFS truy cập con trỏ `d_inode` của dentry `app.log` vừa tìm được để lấy cấu trúc **`inode`** vật lý của file [41].

  

### Bước 5: Cấp phát cấu trúc File Object toàn cục

Nhân kernel tạo mới một mục nhập trong **Bảng mô tả file đang mở toàn cục** (Open File Description Table) [88, 274]:

1. Gán con trỏ `f_path.dentry` trỏ tới dentry của `app.log` và `f_path.mnt` trỏ tới thông tin gắn kết (mount point) [42, 275].

2. Đặt con trỏ vị trí tệp tin hiện tại `f_pos = 0` (bắt đầu đọc từ byte đầu tiên của file) [42, 85, 271, 274].

3. Lưu trữ trạng thái mở file là chỉ đọc (`O_RDONLY`) [88, 274].

4. Ánh xạ các con trỏ hàm thao tác tệp tin (`f_op`) trỏ về bảng thao tác chuyên biệt của hệ thống tệp đích (ví dụ: các hàm `ext4_file_read`...) [43].

  

### Bước 6: Đăng ký File Descriptor cục bộ cho tiến trình

1. Nhân kernel truy cập bảng File Descriptor cục bộ của tiến trình hiện tại [87, 273].

2. Quét từ vị trí chỉ số 0 trở lên để tìm kiếm chỉ số **trống nhỏ nhất chưa sử dụng** (theo đặc tả tiêu chuẩn POSIX) [76, 263]. Do `0`, `1`, `2` đã bị chiếm bởi các luồng I/O tiêu chuẩn, chỉ số được cấp thường bắt đầu từ **`3`** [73, 76, 263].

3. Ghi nhận chỉ mục `3` này trỏ tới địa chỉ của cấu trúc File Object vừa tạo ra ở Bước 5 [87, 273].

  

### Bước 7: Kernel Exit & Trở lại thế giới thực (Ring 0 -> Ring 3)

1. Đặt giá trị FD vừa được cấp (số `3`) vào thanh ghi kết quả `%rax` [68, 255].

2. Chạy mã assembly khôi phục lại trạng thái cũ của các thanh ghi người dùng từ Kernel Stack [255].

3. Thực thi lệnh **`sysretq`** để hạ quyền lực CPU về **Ring 3** và trả con trỏ lệnh về tiếp tục chạy trong thư viện `glibc` [255].

  

### Bước 8: glibc bàn giao quyền kiểm soát

Hàm bao của `glibc` nhận kết quả trả về từ thanh ghi `%rax` (là số `3`) và bàn giao số nguyên `3` này cho ứng dụng [255].

Kể từ lúc này, ứng dụng đã có trong tay chiếc "vé thông hành" mang tên **FD 3** để thực hiện các thao tác đọc/ghi tiếp theo [73, 252].

  

---

  

## 3. Bản Chất của Ảo Ảnh "File System Cô Lập" Trong Docker

  

Hiểu rõ chuỗi liên kết **File Descriptor $\rightarrow$ File Object $\rightarrow$ Dentry $\rightarrow$ Inode** của VFS giúp ta thấy được chính xác cách Docker đánh lừa tiến trình để tạo ra sự cô lập container:

  

1. **Mount Namespace (`CLONE_NEWNS`):**

   Khi Docker khởi chạy container, nó gọi lệnh `clone()` với cờ `CLONE_NEWNS` [215, 402]. Lúc này, kernel sẽ nhân bản bảng gắn kết (mount table) của máy chủ vật lý và cấp riêng cho container. Mọi lệnh `mount` hay `umount` bên trong container từ nay chỉ làm thay đổi danh sách mount riêng này của VFS, hoàn toàn vô hình đối với máy chủ vật lý bên ngoài [215, 402].

  

2. **Xếp chồng Layer bằng OverlayFS:**

   Docker gộp các layer Image (Read-only) và một lớp ghi dữ liệu của container (Read-write) lại thành một thư mục hợp nhất (`MergedDir`). Lớp VFS của Linux đứng ra xử lý việc gộp này bằng cách **xếp chồng các dentry** của các layer lên nhau trong bộ nhớ dcache. Tiến trình bên trong container khi duyệt thư mục sẽ chỉ nhìn thấy các dentry hợp nhất này.

  

3. **Bịt lối thoát bằng `pivot_root`:**

   Để tiến trình không thể lần mò ngược về hệ thống tệp gốc của máy host, Docker sử dụng lệnh `pivot_root` trong Mount Namespace mới [134, 319]. Lệnh này hoán đổi mount point gốc thực sự của hệ thống thành thư mục `MergedDir` của OverlayFS, sau đó thực hiện gỡ bỏ hoàn toàn (umount) hệ thống tệp của máy host ra khỏi container [134, 319].

  

4. **Remount `/proc` và `/sys`:**

   Sau khi đã khóa chặt thư mục gốc, Docker ra lệnh cho VFS mount hệ thống tệp ảo **`procfs`** mới đè lên `/proc` và **`sysfs`** đè lên `/sys` [114, 299]. Do được liên kết trực tiếp với PID Namespace cô lập của container, hệ thống `/proc` mới này chỉ hiển thị danh sách các tiến trình nội bộ của container (bắt đầu từ PID 1), hoàn tất ảo ảnh hoàn hảo về một hệ điều hành riêng biệt [221, 407].