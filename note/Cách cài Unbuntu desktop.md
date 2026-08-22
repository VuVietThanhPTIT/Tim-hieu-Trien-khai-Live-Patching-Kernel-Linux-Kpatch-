**1. Cài đặt môi trường giao diện đồ họa (GUI) và Display Manager**

  

Bash

```
# Cập nhật danh mục gói
apt update

# Cài đặt giao diện GNOME rút gọn kèm trình quản lý đăng nhập gdm3
apt install -y ubuntu-desktop

# Đặt giao diện đồ họa làm mặc định khi khởi động
systemctl set-default graphical.target

# Khởi chạy dịch vụ gdm3
systemctl start gdm3
```

**2. Cài đặt và kích hoạt dịch vụ Remote Desktop (XRDP)**

  


```
# Cài đặt xrdp
apt install -y xrdp

# Thêm quyền đọc chứng chỉ bảo mật cho xrdp
adduser xrdp ssl-cert

# Bật và kích hoạt dịch vụ xrdp chạy nền
systemctl enable --now xrdp
```

**3. Tạo tài khoản người dùng thường (bắt buộc để đăng nhập GUI)**

  

```
# Tạo user mới (ví dụ: 'thanh')
adduser thanh

# Cấp quyền sudo quản trị cho user
usermod -aG sudo thanh
```

**4. Thiết lập kết nối trên MobaXterm (qua 2 lớp mạng)**

  

- **Tạo Session:** Chọn biểu tượng **`RDP`**.
    
      
    - **Remote host:** Điền **IP của máy Ubuntu đích**.
        
          
        
    - **Username:** Điền **`thanh`** | Port: **`3389`**.
        
          
        
- **Cấu hình Gateway qua máy trung gian:**
    
      
    - Chuyển sang tab **`Network settings`**.
        
          
        
    - Tích chọn **`Connect through SSH gateway (jump host)`**.
        
          
        
    - Nhập **IP**, **User**, và **Port 22** của máy trung gian (lớp 1).
        
          
        
- **Kết nối:** Bấm **OK** và nhập mật khẩu của user `thanh`.