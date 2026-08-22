[[Virtual file system]]
# Vấn đề : 
- Trên window : hệ điều hành quản lý các ổ cứng theo cơ chế phan vùng độc lập , mỗi phân vùng hay thiết bị cắm vào sẽ được gắn 1 ký tự ổ đĩa riêng biệt 
- Trên linux: Triết lý là 1 cây thư mục duy nhất , tất cả phải nằm dưới 1 thư mục /root 
	- **Làm thế nào để đưa toàn bộ tệp tin bên trong ổ đĩa mới vào trong cái thư mục duy nhất , đó chính là hành động mount** 
## Khái niệm cốt lõi  của mount 
- Thiết bị lưu trũ vật lý hoặc ảo chứa dữ liệu được định dạng bằng 1 hệ thống tệp ( như ext4 , NTFS , FAT32)
- Điểm gắn kết ( Mount point ) là 1 thư mục thông thường 
	- Ví dụ /mnt/usb 
- Hành động mount : là việc đính kèm toàn bộ hệ thống tệp của thiết bị nguồn vào thư mục mount point trên cây thư mục gốc 


## Luồng thực tế của mount  
- Mount tạo ra 1 đối tượng **superblock** cho phân vùng mới cấp phát 1 cấu trúc gắn kết vfsmount và bật cờ đánh dấu **DCACHE_MOUNTED** trên **dentry** của thư mục đích để bẻ luồng truy cập của các tiến trình sang ổ đĩa mới.
## ex
```
mount("/dev/sda12", "/testfs", "ext4", MS_RDONLY, NULL);
```

- Bước 1 : Khởi đầu tại userspace 
	- app gọi mount , sau đó hàm bao của glibc tiếp quản ( ... thực thi lệnh syscal chuyển cpu lên ring 0 ,...)
- Bước 2 : Kernel entry và tiếp nhận tham số 
	- Trình xử lý trap của kernel đóng băng ngữ cảnh userspace bằng cách đấy tất cả thanh ghi vào kernel stack của tiến trình 
     - Kernel sử dụng hàm `getname()` để sao chép an toàn các chuỗi ký tự `"/dev/sda12"` và `"/testfs"` từ không gian nhớ ảo của Userspace vào vùng nhớ an toàn của Kernel Space
- Bước 3: Phân giải điểm gắn kết (Target Path Resolution)
	- vfs thực hiện phân giải đường dẫn pathname resolution cho bién target ỏ đây là '/testfs' duyệt qua bộ đệm dcache để tìm ra đối tượng dentry object 
	- Từ dentry -> đi tìm cấu trúc inode object tươn ứng 
	- kiểm tra tính hợp lệ : liệu đường dẫn đó có phải là thư mục k 
- Bước 4 : Tạo superblock cho hệ thống tệp mới
	- Nếu k phải là bind mount : vfs tra cứu drive thích hợp để tìm đúng loại ( drive cung cáp operation với loại file đấy)
	- nó gọi hàm mount chuyên biệt cảu ext4 , driver này đi xuống phân vùng ỏ đĩa vật lý /dev/sda12 , tìm kiếm superblock vật lý nằm ở những sector đầu tiên 
	- đọc thông số của cái hệ thống ổ đĩa vật lý hoặc logic đó ( **block size , tổng số inode**) nạp lên RAM và khởi tạo cấu trúc của hệ thóng ext4 này 
	- nếu là bind mouint : bước này bỏ qua hoàn toàn , kernel k đọc đĩa mà láy luôn cấu trúc cảu superblock và dentry có sẵn của thư mục nguồn để tải sủ dụng 
- Bước 5 : cấp phát cấu trúc gắn kết 
	- Để theo dõi mối quan hệ gắn kết này trong bộ nhớ , kernel sử dụng 1 cấu trúc dữ liệu gọi là struct vfsmount 
- Bước 6 : Đánh dấu 
	- kernel đưa cá trúc struct mount vừa tạo vào danh sách quản lý mount tree 
	- đánh dấu đối tượng dentry /testfs bằng 1 cờ hiệu đặc biệt trong RAM 
- Bước 7 : kêrnel exit 
	- kernel đặt gái trị về thành công là 0 vào thanh ghi .
	- trap lại vểing 3 
	- glibc nhận kết quả 0 báo lại cho app 
	- 
