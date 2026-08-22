Toàn bộ đoạn mã trên là kỹ thuật **APT Pinning (ghim độ ưu tiên kho)**, dùng để **"mượn" duy nhất gói Kernel 5.15 từ Ubuntu 22.04 (Jammy)** cài sang Ubuntu 24.04 (Noble) mà không làm hỏng các thư viện phần mềm khác của hệ thống.

  

Ý nghĩa chi tiết của từng khối lệnh:

  

### Khối 1: Khai báo thêm kho lưu trữ của Ubuntu 22.04 (Jammy)

Bash

```
echo "deb http://archive.ubuntu.com/ubuntu jammy main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu jammy-updates main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu jammy-security main restricted universe multiverse" \
  | sudo tee /etc/apt/sources.list.d/jammy-kernel-temp.list

sudo apt update
```

- **`echo "..." | sudo tee .../jammy-kernel-temp.list`**: Tạo một tệp nguồn phụ trong thư mục `/etc/apt/sources.list.d/`. Tệp này thông báo cho APT biết địa chỉ máy chủ chứa toàn bộ các gói phần mềm của bản **Ubuntu 22.04 (Jammy)**.
    
      
    
- **`sudo apt update`**: Tải danh mục chỉ mục gói từ kho Jammy về máy để APT "nhìn thấy" các gói phần mềm đang có trên 22.04.
    
      
    

### Khối 2: Cấu hình APT Pinning (Lọc và chặn xung đột — Cực kỳ quan trọng)

Nếu chỉ thêm kho Jammy ở Khối 1 mà không có Khối 2, khi bạn chạy lệnh `apt upgrade` hoặc cài phần mềm, APT sẽ vô tình kéo theo hàng nghìn thư viện cũ của 22.04 về đè lên 24.04, dẫn đến hỏng toàn bộ hệ điều hành (lỗi _Franken-Ubuntu_).

  

Bash

```
sudo tee /etc/apt/preferences.d/jammy-kernel-pin <<'EOF'
Package: *
Pin: release n=jammy
Pin-Priority: -10

Package: linux-image-* linux-headers-* linux-modules-* linux-buildinfo-*
Pin: release n=jammy-updates
Pin-Priority: 990
EOF

sudo apt update
```

- **Quy tắc 1 (`Package: *` / `Pin-Priority: -10`)**:
    
      
    - Đặt mức ưu tiên âm ($-10$) cho **tất cả** các gói đến từ kho Jammy.
        
          
        
    - _Ý nghĩa:_ Cấm tuyệt đối APT tự động tải bất kỳ phần mềm/thư viện nào từ Jammy về máy.
        
          
        
- **Quy tắc 2 (`Package: linux-*` / `Pin-Priority: 990`)**:
    
      
    - Đặt mức ưu tiên rất cao ($990$) chỉ riêng cho các gói liên quan đến **Kernel** (`linux-image`, `linux-headers`, `linux-modules`).
        
          
        
    - _Ý nghĩa:_ Tạo ngoại lệ cho phép APT tải và ưu tiên các gói nhân Kernel từ Jammy.
        
          
        

### Khối 3: Tra cứu chính xác số hiệu bản Kernel có trong kho

Bash

```
apt-cache madison linux-image-5.15.0-185-generic
```

- **`madison`**: Là bảng tra cứu trong bộ nhớ đệm của APT. Lệnh này in ra danh sách tất cả các phiên bản (version number), kiến trúc (amd64) và nguồn repository đang cung cấp gói `linux-image-5.15.0-185-generic`.
    
      
    
- Đầu ra sẽ cho bạn biết chính xác chuỗi phiên bản đầy đủ (ví dụ: `5.15.0-185.195`) để bạn đưa vào lệnh `apt install`.