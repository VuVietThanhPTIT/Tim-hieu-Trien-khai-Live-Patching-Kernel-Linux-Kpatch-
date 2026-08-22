## 1. Process 
## 1.1. Process (Tiến trình) 
- **Process (Tiến trình):** chương trình đang trong quá trình thực thi , là đơn vị cấp phát tài nguyên và bảo vệ hệ thống , mỗi tiến trình **Sở hữu một không gian địa chỉ ảo** ( Virutal adress space chính là cái phân đoạn mã lệnh , phân đoạn dữ liệu đã khởi tạo , phân doạn dữ liệu chưa khởi tạo  , vùng nhớ heap , vùng nhớ stack , danh sách các tập tin đang mở ( **Open file**) , quyền hạn người dùng (**User ID**)  và cơ chế **IPC** 
	-
	- Sự cô lập bộ nhớ được thực thi bằng bảng trang **(page table)** 
	- Trang : khối nhỏ trong không gian địa chỉ của tiến trình 
	- khung trang : khối nhỏ trong RAM vật lý thật 
	- bảng trang : ánh xạ giữa trang và khung trang 
		
	- 