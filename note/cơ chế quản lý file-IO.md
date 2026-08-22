		 ## 3 tầng cấu trúc dữ liệu mà kernel dùng để quản lý khi 1 tiến trình mở và thao tác đọc ghi với file 
### 1 FD : số vé riêng của từng tiến trình 
## 2 Bảng File đang mở toàn cục (Open File Description)
## 3  inode  - lý lịch gốc thật của file trên đĩa 


# Vấn đề cần giải quyết :
- Khi 1 chương trình muốn đọc file  ,nó không thể chạm trực tiếp vào để mở file , cần thông qua kernel để thao tác 
	-  Chương trình gọi tên file đơn giản không cần gõ đường dẫn dài mỗi lần đọc 
	- Kernel biết chương trình đang đọc đến đâu rồi 
	- Kernel biết file đó nằm thực tế ở đâu 
## Tầng 1 : 
```

int fd = open("data.txt", O_RDONLY);
// giả sử fd = 3
```
-> thay vì gọi data lần sau ta có thể gọi vé 3 
	**# Note** 
-  Mỗi tiến trình có **1 quyển vé riêng**, đánh số từ 0 trở lên
- Vé `0` = stdin (bàn phím / input)
- Vé `1` = stdout (màn hình / output)
- Vé `2` = stderr (báo lỗi)
- Vé `3, 4, 5...` = các file bạn tự mở thêm
## Tầng 2 :  Gọi là File structure  
[[Virtual file system]]
	- Mỗi lần bạn mở file , kernel tạo ra 1 hồ sơ mở file , ghi lại 
		- Đang mở với quyền gì 
		- Con trỏ vị trí offset 
## Tầng 3: 
  - i-node :thực tế là metadata của file , quyền truy cập , chủ sở hữu , kích thước file 
  

	