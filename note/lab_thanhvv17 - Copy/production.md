production

![Pasted image 20260904172213](img-lab/Pasted%20image%2020260904172213.png)

sau patch
![Pasted image 20260904173039](img-lab/Pasted%20image%2020260904173039.png)
![Pasted image 20260904173237](img-lab/Pasted%20image%2020260904173237.png)

---

Grub ver 2 607

Trước
![Pasted image 20260904224417](img-lab/Pasted%20image%2020260904224417.png)

sau
![Pasted image 20260904224715](img-lab/Pasted%20image%2020260904224715.png)

Grub 3:

trước
![Pasted image 20260904234848](img-lab/Pasted%20image%2020260904234848.png)

sau
![Pasted image 20260904235214](img-lab/Pasted%20image%2020260904235214.png)



  


# QUY TRÌNH BIÊN DỊCH VÀ KIỂM THỬ LINUX KERNEL LIVEPATCH (CVE-2026-53359)

> **Lưu ý cốt lõi:**
> 
>   
> 
> - **Vermagic:** Giá trị `vermagic` trong metadata của file `.ko` sau khi build phải khớp 100% với kernel đang chạy (`uname -r`).
>     
>       
>     
> - **KVM Module Target:** Không thêm cờ `-t vmlinux` vào lệnh `kpatch-build` để hệ thống tự động bóc tách và tạo patch cho module ngoài `kvm.ko`.
>     
>       
>     

## Phần 1: Khởi tạo môi trường & Biên dịch Livepatch (.ko)

Thực hiện toàn bộ phần này tại thư mục `/root/cve-2026-53359` trên máy build/host.

  

### 1. Khởi tạo cấu trúc thư mục

Bash

```
mkdir -p /root/cve-2026-53359/{config,vmlinux,kernel,ko,patches}
cd /root/cve-2026-53359
```

### 2. Tải tài nguyên chuẩn từ S3 (Patch, Config, Vmlinux)

Bash

```
# 1. Tải bản vá chuẩn noble.patch
s3cmd get --force s3://cve-2026-53359/trilogy-cve-2026-64561/git-diff-patch/noble.patch \
  /root/cve-2026-53359/patches/trilogy.noble.patch

# 2. Tải cấu hình kernel (ubuntu-config) cho cả 3 phiên bản
for VER in 6.8.0-106.106 6.8.0-107.107 6.8.0-111.111; do
    s3cmd get --force s3://cve-2026-53359/config/noble/ubuntu-config-${VER} \
      /root/cve-2026-53359/config/ubuntu-config-${VER}
done

# 3. Tải file nhị phân vmlinux debug cho cả 3 phiên bản
for VER in 6.8.0-106.106 6.8.0-107.107 6.8.0-111.111; do
    s3cmd get --force s3://cve-2026-53359/vmlinux/noble/vmlinux-${VER}-generic \
      /root/cve-2026-53359/vmlinux/vmlinux-${VER}-generic
done
```

### 3. Tải mã nguồn Kernel gốc từ Launchpad

Bash

```
cd /root/cve-2026-53359/kernel

# Tải file orig.tar.gz dùng chung cho nhân 6.8.0
wget -nc https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/linux/6.8.0-106.106/linux_6.8.0.orig.tar.gz

# Tải file dsc, diff và giải nén source tương ứng từng bản
for VER in 6.8.0-106.106 6.8.0-107.107 6.8.0-111.111; do
    echo ">>> Đang tải source package Launchpad cho: ${VER}..."
    wget -nc "https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/linux/${VER}/linux_${VER}.dsc"
    wget -nc "https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/linux/${VER}/linux_${VER}.diff.gz"
    
    # Giải nén ra thư mục linux-6.8.0-xxx.xxx
    dpkg-source -x "linux_${VER}.dsc" "linux-${VER}"
done
```

### 4. Chuẩn hóa file cấu hình Kernel

Xóa rỗng `CONFIG_SYSTEM_TRUSTED_KEYS` và `CONFIG_SYSTEM_REVOCATION_KEYS` để loại bỏ cơ chế ký khóa nội bộ, tránh lỗi thiếu private key khi biên dịch:

  

Bash

```
for VER in 6.8.0-106.106 6.8.0-107.107 6.8.0-111.111; do
    CFG="/root/cve-2026-53359/config/ubuntu-config-${VER}"
    sed -i 's/CONFIG_SYSTEM_TRUSTED_KEYS=.*/CONFIG_SYSTEM_TRUSTED_KEYS=""/' "$CFG"
    sed -i 's/CONFIG_SYSTEM_REVOCATION_KEYS=.*/CONFIG_SYSTEM_REVOCATION_KEYS=""/' "$CFG"
done
```

### 5. Biên dịch Livepatch với `kpatch-build`

Bash

```
PATCH_FILE="/root/cve-2026-53359/patches/trilogy.noble.patch"
KO_DIR="/root/cve-2026-53359/ko"

for VER in 6.8.0-106.106 6.8.0-107.107 6.8.0-111.111; do
    CFG="/root/cve-2026-53359/config/ubuntu-config-${VER}"
    VMLINUX="/root/cve-2026-53359/vmlinux/vmlinux-${VER}-generic"
    SRCDIR="/root/cve-2026-53359/kernel/linux-${VER}"
    VER_DASHES="${VER//./-}"
    KPATCH_GEN_KO="${KO_DIR}/trilogy--cve-2026-53359--cve-2026-64561--${VER_DASHES}.ko"
    FINAL_KO="${KO_DIR}/trilogy__cve-2026-64561--cve-2026-64561__${VER}.ko"

    export KREL="${VER%.*}-generic"
    export VER="${VER}"

    echo ">>> Bắt đầu build kpatch cho kernel: ${VER}..."
    kpatch-build \
        -s "$SRCDIR" \
        -v "$VMLINUX" \
        -c "$CFG" \
        -j "$(nproc)" \
        -n "trilogy--cve-2026-53359--cve-2026-64561--${VER}" \
        -o "$KO_DIR" \
        --skip-compiler-check \
        --skip-cleanup \
        "$PATCH_FILE"

    # Đổi tên file về chuẩn đầu ra
    if [ -f "$KPATCH_GEN_KO" ]; then
        mv "$KPATCH_GEN_KO" "$FINAL_KO"
    fi
done
```

### 6. Nghiệm thu Module Livepatch (.ko)

Kiểm tra định dạng file nhị phân, cờ `livepatch: Y` và thông số `vermagic`:

  

Bash

```
# Liệt kê danh sách artifact
ls -lh /root/cve-2026-53359/ko/trilogy__cve-2026-64561--cve-2026-64561__6.8.0-*.ko

# Kiểm tra metadata và vermagic
for f in /root/cve-2026-53359/ko/trilogy__cve-2026-64561--cve-2026-64561__6.8.0-*.ko; do
    echo "=================================================="
    echo "File: $(basename "$f")"
    modinfo "$f" | grep -E "^(name|livepatch|vermagic|retpoline|license):"
done
```

## Phần 2: Cài đặt Kernel & Ghim GRUB trên Host (`vhhl1c2lab2com05`)

### 1. Cài đặt các phiên bản Kernel cần kiểm thử

Bash

```
sudo apt update
sudo apt install -y \
  linux-image-6.8.0-106-generic=6.8.0-106.106 \
  linux-modules-6.8.0-106-generic=6.8.0-106.106 \
  linux-modules-extra-6.8.0-106-generic=6.8.0-106.106 \
  linux-headers-6.8.0-106-generic=6.8.0-106.106 \
  linux-headers-6.8.0-106=6.8.0-106.106 \
  linux-image-6.8.0-107-generic=6.8.0-107.107 \
  linux-modules-6.8.0-107-generic=6.8.0-107.107 \
  linux-modules-extra-6.8.0-107-generic=6.8.0-107.107 \
  linux-headers-6.8.0-107-generic=6.8.0-107.107 \
  linux-headers-6.8.0-107=6.8.0-107.107 \
  linux-image-6.8.0-111-generic=6.8.0-111.111 \
  linux-modules-6.8.0-111-generic=6.8.0-111.111 \
  linux-modules-extra-6.8.0-111-generic=6.8.0-111.111 \
  linux-headers-6.8.0-111-generic=6.8.0-111.111 \
  linux-headers-6.8.0-111=6.8.0-111.111
```

### 2. Các lệnh ghim GRUB tương ứng từng vòng test

Sau mỗi lần thay đổi `GRUB_DEFAULT`, bắt buộc chạy `update-grub` và kiểm tra lại `grub.cfg`:

  

- **Ghim Kernel `6.8.0-106-generic`:**
    
      
    
    Bash
    
    ```
    sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.8.0-106-generic"/' /etc/default/grub
    sudo update-grub
    ```
    
- **Ghim Kernel `6.8.0-107-generic`:**
    
      
    
    Bash
    
    ```
    sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.8.0-107-generic"/' /etc/default/grub
    sudo update-grub
    ```
    
- **Ghim Kernel `6.8.0-111-generic`:**
    
      
    
    Bash
    
    ```
    sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.8.0-111-generic"/' /etc/default/grub
    sudo update-grub
    ```
    
- **Lệnh xác nhận tên menuentry trước khi reboot:**
    
      
    
    Bash
    
    ```
    grep -E "menuentry 'Ubuntu, with Linux 6.8.0-(106|107|111)-generic'" /boot/grub/grub.cfg
    ```
    

## Phần 3: Phục hồi môi trường OpenStack sau Reboot Host

Sau khi máy Compute khởi động lại, dịch vụ Libvirt và máy ảo OpenStack cần được đồng bộ lại theo thứ tự sau:

  

### 1. Dọn dẹp thư mục socket rác và bật container `nova_libvirt`

Chạy trên máy Compute **`vhhl1c2lab2com05`**:

  

Bash

```
# 1. Xóa thư mục/socket kẹt gây crash 'Address already in use'
rm -rf /run/libvirt/libvirt-sock* /run/libvirt/virtqemud-sock*

# 2. Khởi động lại container ảo hóa
docker start nova_libvirt

# 3. Chờ 3s và xác nhận container ở trạng thái Up
sleep 3
docker ps | grep nova_libvirt
```

### 2. Khởi động 2 máy ảo qua OpenStack CLI

Chạy trên máy Controller **`vhhl1lab2mkolla00`** _(không dùng virsh start trực tiếp để tránh bị Nova gửi tín hiệu ACPI tắt máy)_:

  

Bash

```
# 1. Khởi động máy ảo qua OpenStack
openstack server start thanhvv17-test-vm-01
openstack server start thanhvv17-test-vm-02

# 2. Theo dõi cho đến khi cả 2 VM chuyển sang trạng thái ACTIVE
openstack server list | grep thanhvv17
```

## Phần 4: Thiết lập kịch bản Benchmark mạng trên 2 VM

### 1. Truy cập console của 2 máy ảo từ node Compute (`vhhl1c2lab2com05`)

- **Console VM 01 (`192.168.100.181`):**
    
      
    
    Bash
    
    ```
    docker exec -it nova_libvirt virsh console instance-000002e0
    ```
    
- **Console VM 02 (`192.168.100.159`):**
    
      
    
    Bash
    
    ```
    docker exec -it nova_libvirt virsh console instance-000002e3
    ```
    

_(Ấn phím `Enter` để hiện màn hình login `ubuntu` / `123456`. Thoát console dùng tổ hợp phím `Ctrl + ]`)._

  

### 2. Cấu hình Server trên VM 01 (`192.168.100.181`)

Tạo file `server.py` và chạy thường trực:

  

Bash

```
cat << 'EOF' > server.py
import socket, time

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('0.0.0.0', 5201))
s.listen(5)
print(">>> iperf-py Server listening on 0.0.0.0:5201...")

while True:
    conn, addr = s.accept()
    print(f">>> Connected by {addr}")
    total_bytes = 0
    start = time.time()
    while True:
        data = conn.recv(131072)
        if not data:
            break
        total_bytes += len(data)
    duration = time.time() - start
    speed_gbps = (total_bytes * 8) / (duration * 1e9) if duration > 0 else 0
    print(f">>> Done: {total_bytes / 1e6:.2f} MB in {duration:.2f}s -> Throughput: {speed_gbps:.2f} Gbps\n")
    conn.close()
EOF

python3 server.py
```

### 3. Cấu hình Client trên VM 02 (`192.168.100.159`)

Tạo file `client.py` để chuẩn bị bắn tải:

  

Bash

```
cat << 'EOF' > client.py
import socket, time

target_ip = '192.168.100.181'
target_port = 5201
duration = 10
chunk = b'x' * 131072

print(f">>> Connecting to {target_ip}:{target_port}...")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((target_ip, target_port))
print(f">>> Benchmarking for {duration} seconds...")

total_sent = 0
start_time = time.time()

while time.time() - start_time < duration:
    s.sendall(chunk)
    total_sent += len(chunk)

actual_duration = time.time() - start_time
s.close()

speed_gbps = (total_sent * 8) / (actual_duration * 1e9)
print("---------------------------------------------")
print(f"Sent: {total_sent / 1e6:.2f} MB")
print(f"Time: {actual_duration:.2f} s")
print(f"Throughput: {speed_gbps:.2f} Gbps")
print("---------------------------------------------")
EOF
```

## Phần 5: Ma trận Thực thi & Đánh giá (Test Loop 106 ➔ 107 ➔ 111)

Quy trình lặp chuẩn cho từng kernel:

  

```
[Ghim GRUB] ➔ [Reboot Host] ➔ [Fix Socket & Start VM] ➔ [Benchmark Baseline] ➔ [Nạp kpatch] ➔ [Benchmark After-Patch]
```

### Chu kỳ 1: Kiểm thử trên Kernel 6.8.0-106

1. **Ghim GRUB & Reboot:**
    
      
    
    Bash
    
    ```
    sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.8.0-106-generic"/' /etc/default/grub
    sudo update-grub
    sudo reboot
    ```
    
2. **Khởi tạo lại môi trường (sau khi máy lên):**
    
      
    - Trên Compute: `rm -rf /run/libvirt/libvirt-sock* && docker start nova_libvirt`
        
          
        
    - Trên Controller: `openstack server start thanhvv17-test-vm-01 && openstack server start thanhvv17-test-vm-02`
        
          
        
3. **Chạy Baseline (Chưa nạp Patch):**
    
      
    - VM 01 bật: `python3 server.py`
        
          
        
    - VM 02 bắn tải: `python3 client.py`
        
          
        
    - _Ghi nhận kết quả thông lượng Baseline._
        
          
        
4. **Nạp Livepatch trên host Compute:**
    
      
    
    Bash
    
    ```
    cd /root/cve-2026-53359/ko
    kpatch load ./trilogy__cve-2026-64561--cve-2026-64561__6.8.0-106.106.ko
    kpatch list
    ```
    
5. **Chạy Benchmark sau khi nạp Patch:**
    
      
    - VM 02 chạy lại: `python3 client.py`
        
          
        
    - _So sánh Throughput trước và sau patch, đảm bảo hệ thống không suy giảm hiệu năng._
        
          
        

### Chu kỳ 2: Chuyển sang Kernel 6.8.0-107

1. **Ghim GRUB & Reboot:**
    
      
    
    Bash
    
    ```
    sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.8.0-107-generic"/' /etc/default/grub
    sudo update-grub
    sudo reboot
    ```
    
2. **Khởi tạo lại môi trường:**
    
      
    - Fix socket `nova_libvirt`, bật lại 2 VM lên `ACTIVE`.
        
          
        
3. **Chạy Baseline (Chưa patch):**
    
      
    - VM 02: `python3 client.py`
        
          
        
4. **Nạp Livepatch 107 trên host Compute:**
    
      
    
    Bash
    
    ```
    cd /root/cve-2026-53359/ko
    kpatch load ./trilogy__cve-2026-64561--cve-2026-64561__6.8.0-107.107.ko
    kpatch list
    ```
    
5. **Chạy Benchmark sau khi nạp Patch:**
    
      
    - VM 02: `python3 client.py`
        
          
        

### Chu kỳ 3: Chuyển sang Kernel 6.8.0-111

1. **Ghim GRUB & Reboot:**
    
      
    
    Bash
    
    ```
    sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.8.0-111-generic"/' /etc/default/grub
    sudo update-grub
    sudo reboot
    ```
    
2. **Khởi tạo lại môi trường:**
    
      
    - Fix socket `nova_libvirt`, bật lại 2 VM lên `ACTIVE`.
        
          
        
3. **Chạy Baseline (Chưa patch):**
    
      
    - VM 02: `python3 client.py`
        
          
        
4. **Nạp Livepatch 111 trên host Compute:**
    
      
    
    Bash
    
    ```
    cd /root/cve-2026-53359/ko
    kpatch load ./trilogy__cve-2026-64561--cve-2026-64561__6.8.0-111.111.ko
    kpatch list
    ```
    
5. **Chạy Benchmark sau khi nạp Patch:**
    
      
    - VM 02: `python3 client.py`