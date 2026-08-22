Khi chạy lệnh `apt`, hệ thống sẽ dựa vào các tệp cấu hình nguồn để kết nối tới các máy chủ kho phần mềm (**Package Repositories / Mirrors**), tải tệp chỉ mục về so khớp và tải các gói `.deb` tương ứng.

  

### 1. APT lấy gói từ đâu?

APT xác định máy chủ tải về dựa vào các tệp cấu hình nằm trong `/etc/apt/`:

  

- **Trên Ubuntu 24.04 trở lên:** Cấu hình chính nằm ở tệp định dạng mới `deb822` tại:
    
      
    
    Bash
    
    ```
    /etc/apt/sources.list.d/ubuntu.sources
    ```
    
- **Trên Ubuntu 22.04 trở về trước:** Cấu hình nằm ở tệp truyền thống:
    
      
    
    Bash
    
    ```
    /etc/apt/sources.list
    ```
    
- **Các phần mềm bên thứ 3 (Docker, Google, Nginx...):** Nằm trong các tệp riêng biệt tại thư mục:
    
      
    
    Bash
    
    ```
    /etc/apt/sources.list.d/*.list hoặc *.sources
    ```
    

### 2. Qua từng phiên bản OS có tải từ chỗ khác nhau không?

**Có, đường dẫn phân nhánh bắt buộc phải khác nhau.**

  

Mặc dù tên miền máy chủ (_Domain_) có thể vẫn là `archive.ubuntu.com`, nhưng đường dẫn bên trong sẽ phân tách theo **Mã định danh phiên bản (Codename)**:

  

- **Ubuntu 24.04:** Sử dụng nhánh kho **`noble`** (bao gồm `noble-updates`, `noble-security`, `noble-backports`).
    
      
    
- **Ubuntu 22.04:** Sử dụng nhánh kho **`jammy`**.
    
      
    
- **Ubuntu 20.04:** Sử dụng nhánh kho **`focal`**.
    
      
    

> **Tại sao phải chia khác nhau?**
> 
> Mỗi phiên bản Ubuntu sử dụng một bộ thư viện nền tảng khác nhau (như phiên bản `glibc`, `systemd`, `gcc`). Một gói phần mềm `.deb` biên dịch riêng cho Ubuntu 24.04 (`noble`) nếu cố cài trên 20.04 (`focal`) sẽ gây xung đột và gãy toàn bộ hệ thống thư viện phụ thuộc (_dependency hell_).
> 
>   

### 3. Cách điều chỉnh nơi tải về (Đổi Mirror & Thêm Kho)

**Cách 1: Đổi sang Mirror Việt Nam để tăng tốc độ tải**

  

Mặc định máy chủ có thể tải từ mirror quốc tế (`archive.ubuntu.com`), tốc độ tải chậm hơn so với máy chủ nội địa.

  

- **Trên Ubuntu 24.04:** Sửa tệp `/etc/apt/sources.list.d/ubuntu.sources`:
    
      
    
    Bash
    
    ```
    nano /etc/apt/sources.list.d/ubuntu.sources
    ```
    
    Tìm dòng `URIs: [http://archive.ubuntu.com/ubuntu/](http://archive.ubuntu.com/ubuntu/)` và đổi thành:
    
      
    
    Plaintext
    
    ```
    URIs: http://vn.archive.ubuntu.com/ubuntu/
    ```
    
- **Cập nhật lại danh mục sau khi đổi:**
    
      
    
    Bash
    
    ```
    apt update
    ```
    

**Cách 2: Thêm kho phần mềm của bên thứ ba (Third-party Repositories)**

  

Khi muốn cài các phần mềm bản mới nhất không có sẵn trong kho mặc định của Ubuntu (như Docker, VS Code, Nginx):

  

1. **Tải khóa GPG xác thực:** Đảm bảo gói tải về không bị giả mạo hay tấn công trung gian.
    
      
    
2. **Khai báo Repository mới:** Tạo thêm 1 tệp cấu hình trong thư mục `/etc/apt/sources.list.d/`.
    
      
    

_Ví dụ cấu hình mẫu kho Docker trên Ubuntu 24.04:_

  

Plaintext

```
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Signed-By: /etc/apt/keyrings/docker.gpg
```

**Cách 3: Thêm kho PPA cá nhân (Personal Package Archive)**

  

Dùng cho các bản phát hành phần mềm do cộng đồng đóng gói:

Bash

```
# Thêm PPA
add-apt-repository ppa:tên-tác-giả/tên-gói

# Cập nhật danh mục
apt update
```
