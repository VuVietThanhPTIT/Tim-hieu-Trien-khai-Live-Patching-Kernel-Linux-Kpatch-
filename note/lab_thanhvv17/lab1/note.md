

**Requirement** : 
1. Tạo 1 kvm host ubuntu 24.04 live server - kernel 5.15.0-185.195-generic, run 2 vm bằng libvirt với bridge network, hold ping thông và iperf3 (tcp có return) được tới nhau

**Bước 1** : Khởi tạo VM từ image  ubuntu 24.04 live server trong cụm lab  , xem bản kernel hiện tại 
```
uname -r
```
![Pasted image 20260822125131](img/Pasted%20image%2020260822125131.png)

- [How to change linux kernel versions.md](https://gist.github.com/zrruziev/b6ecb011953cf2d93f923bc0f6a06261)
Gõ lệnh để xem các kernel version có thể tải về  , không tìm thấy bản như requirement 
```
apt-cache search linux-image- | grep generic
```
![Pasted image 20260822175825](img/Pasted%20image%2020260822175825.png)


- Trong phiên bản noble 24.04 kernel version là 6.x do vậy ta cần apt pinning ( tránh sau bị tải bị đè thư viện ) để tải về bản  5.15.0 của jammy 

```
echo "deb http://archive.ubuntu.com/ubuntu jammy main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu jammy-updates main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu jammy-security main restricted universe multiverse" \
  | sudo tee /etc/apt/sources.list.d/jammy-kernel-temp.list

```
- Lệnh này dùng để khai báo cho APT biết địa chỉ máy chủ chứa toàn bộ các gói phần mềm của bản **Ubuntu 22.04 (Jammy)**.
```
sudo apt update
```
- Tải danh mục chỉ mục gói từ kho Jammy về máy để APT "nhìn thấy" các gói phần mềm đang có trên 22.04.

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

- Set độ ưu tiên chỉ riêng cho các gói liên quan đến **Kernel** (`linux-image`, `linux-headers`, `linux-modules`).
![Pasted image 20260822183412](img/Pasted%20image%2020260822183412.png)

- Đã tìm được đúng version cần chỉ định sau đó cài đặt
```
sudo apt install \
  linux-image-5.15.0-185-generic=5.15.0-185.195 \
  linux-headers-5.15.0-185-generic=5.15.0-185.195 \
  linux-headers-5.15.0-185=5.15.0-185.195 \
  linux-modules-extra-5.15.0-185-generic=5.15.0-185.195
```

Sửa trực tiếp tệp cấu hình bộ nạp khởi động (`/etc/default/grub`) bằng công cụ xử lý văn bản `sed`. do mặc định grub lấy kernel mới hơn  , sau đó reboot lại 
```
sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 5.15.0-185-generic"/' /etc/default/grub
sudo update-grub
sudo reboot
```

- Kiểm tra xem đã đúng version chưa 
![Pasted image 20260822184353](img/Pasted%20image%2020260822184353.png)

**Bước 2 :** Tạo bridge network ( mạng của 2 con VM cô lập với  host )
Cài trước cái gói cần thiết
```
sudo apt install -y  libvirt-daemon-system libvirt-clients virtinst bridge-utils cloud-image-utils cpu-checker
```

```

sudo tee /tmp/isolated-net.xml <<'EOF'
<network>
  <name>labbr0</name>
  <bridge name="virbr-lab" stp="on" delay="0"/>
  <ip address="192.168.100.1" netmask="255.255.255.0">
    <dhcp>
      <range start="192.168.100.10" end="192.168.100.100"/>
    </dhcp>
  </ip>
</network>
EOF

sudo virsh net-define /tmp/isolated-net.xml
sudo virsh net-start labbr0
sudo virsh net-autostart labbr0

virsh net-list --all
```

- Tạo file và tải images
```
sudo mkdir -p /var/lib/libvirt/images
cd /var/lib/libvirt/images

sudo wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img -O vm1.qcow2
sudo cp vm1.qcow2 vm2.qcow2
sudo qemu-img resize vm1.qcow2 +10G
sudo qemu-img resize vm2.qcow2 +10G
```

- Cloud init seed
	``
```
cat > /tmp/vm1-user-data.yaml <<'EOF'
#cloud-config
hostname: vm1
password: 123456
chpasswd: { expire: false }
ssh_pwauth: true
EOF
sudo cloud-localds /var/lib/libvirt/images/vm1-seed.img /tmp/vm1-user-data.yaml

cat > /tmp/vm2-user-data.yaml <<'EOF'
#cloud-config
hostname: vm2
password: 123456
chpasswd: { expire: false }
ssh_pwauth: true
EOF
sudo cloud-localds /var/lib/libvirt/images/vm2-seed.img /tmp/vm2-user-data.yaml
```

- Kiểm tra địa chỉ IP của 2 VM 
![Pasted image 20260822210540](img/Pasted%20image%2020260822210540.png)

- SSH vào 2 vm và và cài đặt gói iperf3 , trước đó thì bật ip forward trên host , và add default route thêm dns trên 2 VM 

```

sudo apt install -y iperf3

```
- trên VM 2 chạy 
```
iperf3 -s
```

![Pasted image 20260822213752](img/Pasted%20image%2020260822213752.png)

- Đo luồng từ VM1 -> VM2 
```
iperf3 -c 192.168.100.52 -t 30 -i 2
```
![Pasted image 20260822214340](img/Pasted%20image%2020260822214340.png)
- Đo ngược từ VM2 -> VM1 bằng thêm -R 
```
iperf3 -c 192.168.100.12 -t 30 -R
```
![Pasted image 20260822214428](img/Pasted%20image%2020260822214428.png)

- test ping từ vm2 sang vm1 
![Pasted image 20260822220646](img/Pasted%20image%2020260822220646.png)