# LAB 1 — DỰNG KVM HOST, 2 VM VÀ BASELINE NETWORK

## Mục tiêu

- Dựng 01 KVM host trên FPT Cloud.
- Host chạy Ubuntu 24.04 và kernel đúng yêu cầu mentor: `6.8.0-134-generic`.
- Xác nhận nested virtualization hoạt động và KVM acceleration khả dụng.
- Cài đặt QEMU/KVM/libvirt.
- Tạo 02 VM bằng libvirt.
- Hai VM giao tiếp được qua mạng ảo `virbr0`.
- Kiểm tra kết nối bằng `ping` hai chiều.
- Kiểm tra TCP throughput bằng `iperf3`.
- Tạo baseline log để tái sử dụng cho Lab 3 khi thực hiện `kpatch load`.

---

## 1. Chuẩn bị

### 1.1. Kiến trúc lab

```text
FPT Cloud physical infrastructure
        |
        v
FPT Cloud instance: datnt466-kpatch
Ubuntu 24.04 + KVM/libvirt
Kernel: 6.8.0-134-generic
        |
        +-- virbr0 / 192.168.122.0/24
              |
              +-- vm1: 192.168.122.204
              |
              +-- vm2: 192.168.122.122
```

Host `datnt466-kpatch` là một VM trên FPT Cloud, vì vậy để chạy thêm VM bên trong cần nested virtualization.

### 1.2. Cấu hình tài nguyên host

- Flavor: `8C16G`
- RAM host: khoảng 15 GiB
- Disk host: khoảng 148 GiB
- Management IP: `192.168.100.99`

Kiểm tra tài nguyên:

```bash
df -h /
free -h
```

Output thực tế:

```text
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda2       148G  3.5G  138G   3% /

               total        used        free      shared  buff/cache   available
Mem:            15Gi       582Mi        14Gi       4.1Mi       1.3Gi        15Gi
Swap:             0B          0B          0B
```

---

## 2. Triển khai

### Bước 1 — Kiểm tra nested virtualization

Kiểm tra CPU và khả năng ảo hóa:

```bash
lscpu | grep -E 'Model name|Virtualization'
```

Output:

```text
Model name:                           Intel Xeon Processor (Icelake)
Virtualization:                       VT-x
Virtualization type:                  full
```

Kiểm tra cờ `vmx/svm`:

```bash
egrep -c '(vmx|svm)' /proc/cpuinfo
```

Output:

```text
16
```

Kiểm tra thiết bị KVM:

```bash
ls -l /dev/kvm
```

Output:

```text
crw-rw---- 1 root kvm 10, 232 Aug 24 16:08 /dev/kvm
```

Kết luận: nested virtualization đã được expose cho instance và host có thể dùng KVM.

> Ảnh minh họa: chèn screenshot output của 3 lệnh trên nếu cần nghiệm thu bằng hình ảnh.

---

### Bước 2 — Kiểm tra và cập nhật kernel host

Kernel ban đầu:

```bash
uname -r
```

Output ban đầu:

```text
6.8.0-60-generic
```

Mentor yêu cầu package version `6.8.0-134.134`, tương ứng `uname -r` là:

```text
6.8.0-134-generic
```

Cập nhật cache APT:

```bash
sudo apt update
```

Kiểm tra package kernel:

```bash
apt-cache policy linux-image-6.8.0-134-generic
```

Output:

```text
linux-image-6.8.0-134-generic:
  Installed: (none)
  Candidate: 6.8.0-134.134
  Version table:
     6.8.0-134.134 500
        500 http://nova.clouds.archive.ubuntu.com/ubuntu noble-updates/main amd64 Packages
        500 http://security.ubuntu.com/ubuntu noble-security/main amd64 Packages
```

Cài kernel và headers:

```bash
sudo apt install -y \
  linux-image-6.8.0-134-generic \
  linux-headers-6.8.0-134-generic
```

Reboot:

```bash
sudo reboot
```

Kiểm tra sau reboot:

```bash
uname -r
```

Output:

```text
6.8.0-134-generic
```

Kết luận: host đã chạy đúng kernel version phục vụ các lab kpatch tiếp theo.

---

### Bước 3 — Cài KVM/QEMU/libvirt

Cài package:

```bash
sudo apt install -y \
  qemu-kvm \
  libvirt-daemon-system \
  libvirt-clients \
  bridge-utils \
  virtinst \
  cpu-checker
```

Kiểm tra KVM acceleration:

```bash
kvm-ok
```

Output:

```text
INFO: /dev/kvm exists
KVM acceleration can be used
```

Kiểm tra libvirt:

```bash
sudo systemctl status libvirtd --no-pager
```

Output chính:

```text
Active: active (running)
```

Libvirt tự tạo default network với bridge `virbr0`, DHCP range `192.168.122.2 -- 192.168.122.254`.

---

### Bước 4 — Chuẩn bị Ubuntu cloud image

Tạo thư mục lab:

```bash
mkdir -p ~/kpatch-lab/images
cd ~/kpatch-lab/images
```

Tải Ubuntu Noble cloud image:

```bash
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
```

Cài công cụ cloud-init image:

```bash
sudo apt install -y cloud-image-utils
```

Tạo disk riêng cho VM1 và VM2:

```bash
sudo cp ~/kpatch-lab/images/noble-server-cloudimg-amd64.img /var/lib/libvirt/images/vm1.qcow2
sudo cp ~/kpatch-lab/images/noble-server-cloudimg-amd64.img /var/lib/libvirt/images/vm2.qcow2

sudo qemu-img resize /var/lib/libvirt/images/vm1.qcow2 15G
sudo qemu-img resize /var/lib/libvirt/images/vm2.qcow2 15G
```

Kiểm tra VM1 disk:

```bash
sudo qemu-img info /var/lib/libvirt/images/vm1.qcow2
```

Output:

```text
image: /var/lib/libvirt/images/vm1.qcow2
file format: qcow2
virtual size: 15 GiB (16106127360 bytes)
disk size: 596 MiB
```

---

### Bước 5 — Tạo cloud-init cho VM1 và VM2

Tạo thư mục:

```bash
mkdir -p ~/kpatch-lab/cloud-init
cd ~/kpatch-lab/cloud-init
```

Tạo `vm1-user-data`:

```yaml
#cloud-config
hostname: vm1
manage_etc_hosts: true

users:
  - name: ubuntu
    groups: sudo
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: false

chpasswd:
  list: |
    ubuntu:Ubuntu@123
  expire: false

ssh_pwauth: true

package_update: true
packages:
  - iperf3
  - qemu-guest-agent
  - stress-ng

runcmd:
  - systemctl enable --now qemu-guest-agent
```

Tạo VM2 từ template VM1:

```bash
sed 's/hostname: vm1/hostname: vm2/' vm1-user-data > vm2-user-data
```

Tạo metadata:

```text
# vm1-meta-data
instance-id: vm1
local-hostname: vm1

# vm2-meta-data
instance-id: vm2
local-hostname: vm2
```

Tạo seed ISO:

```bash
cloud-localds vm1-seed.iso vm1-user-data vm1-meta-data
cloud-localds vm2-seed.iso vm2-user-data vm2-meta-data
```

Do libvirt system không đọc trực tiếp file dưới `/home/ubuntu`, copy seed ISO sang thư mục libvirt:

```bash
sudo cp ~/kpatch-lab/cloud-init/vm1-seed.iso /var/lib/libvirt/images/
sudo cp ~/kpatch-lab/cloud-init/vm2-seed.iso /var/lib/libvirt/images/
```

Kiểm tra:

```bash
sudo ls -lh /var/lib/libvirt/images/ | grep seed
```

Output:

```text
-rw-r--r-- 1 root root 366K Aug 24 17:29 vm1-seed.iso
-rw-r--r-- 1 root root 366K Aug 24 17:29 vm2-seed.iso
```

---

### Bước 6 — Tạo VM1 và VM2 bằng libvirt

Tạo VM1:

```bash
sudo virt-install \
  --name vm1 \
  --vcpus 2 \
  --memory 3072 \
  --disk path=/var/lib/libvirt/images/vm1.qcow2,format=qcow2,bus=virtio \
  --disk path=/var/lib/libvirt/images/vm1-seed.iso,device=cdrom \
  --os-variant ubuntu24.04 \
  --network network=default,model=virtio \
  --graphics none \
  --import \
  --noautoconsole
```

Output:

```text
Starting install...
Creating domain...
Domain creation completed.
```

Tạo VM2:

```bash
sudo virt-install \
  --name vm2 \
  --vcpus 2 \
  --memory 3072 \
  --disk path=/var/lib/libvirt/images/vm2.qcow2,format=qcow2,bus=virtio \
  --disk path=/var/lib/libvirt/images/vm2-seed.iso,device=cdrom \
  --os-variant ubuntu24.04 \
  --network network=default,model=virtio \
  --graphics none \
  --import \
  --noautoconsole
```

Kiểm tra domain:

```bash
sudo virsh list --all
```

Kỳ vọng:

```text
vm1    running
vm2    running
```

---

### Bước 7 — Kiểm tra IP của hai VM

```bash
sudo virsh domifaddr vm1
sudo virsh domifaddr vm2
```

Output:

```text
vm1
vnet1  52:54:00:27:64:9c  ipv4  192.168.122.204/24

vm2
vnet2  52:54:00:6d:82:d9  ipv4  192.168.122.122/24
```

Kiểm tra DHCP lease:

```bash
sudo virsh net-dhcp-leases default
```

Output chính:

```text
192.168.122.204/24   vm1
192.168.122.122/24   vm2
```

Topology sau triển khai:

```text
virbr0 / 192.168.122.0/24
   |
   +-- vm1: 192.168.122.204
   |
   +-- vm2: 192.168.122.122
```

---

### Bước 8 — Kiểm tra VM1 ↔ VM2 bằng ping

SSH vào VM1:

```bash
ssh ubuntu@192.168.122.204
```

Từ VM1 ping VM2:

```bash
ping -c 5 192.168.122.122
```

Output:

```text
5 packets transmitted, 5 received, 0% packet loss, time 4104ms
rtt min/avg/max/mdev = 0.326/0.368/0.401/0.025 ms
```

Kết luận: VM1 và VM2 thông nhau ổn định, không có packet loss.

---

### Bước 9 — Kiểm tra TCP bằng iperf3

Trên VM2 chạy server:

```bash
iperf3 -s
```

Trên VM1 chạy client:

```bash
iperf3 -c 192.168.122.122 -t 30 -i 1
```

Trong quá trình test, throughput ghi nhận khoảng 30–45 Gbit/s và `Retr = 0` ở các interval đầu.

> Lưu ý: đây là traffic giữa hai VM trên cùng host/virtual network, không phải tốc độ NIC vật lý của FPT Cloud.

---

### Bước 10 — Tạo baseline log cho Lab 3

Tạo ping log có timestamp trên VM1:

```bash
ping 192.168.122.122 | while read line; do
  echo "$(date '+%Y-%m-%d %H:%M:%S.%3N') $line"
done > ~/ping_baseline.log &
```

Chạy iperf3 trong 300 giây, interval 1 giây:

```bash
iperf3 -c 192.168.122.122 -t 300 -i 1 --logfile ~/iperf_baseline.log
```

Kiểm tra ping log:

```bash
tail -n 10 ~/ping_baseline.log
```

Output mẫu:

```text
2026-08-24 10:42:48.837 64 bytes from 192.168.122.122: icmp_seq=345 ttl=64 time=0.323 ms
2026-08-24 10:42:49.861 64 bytes from 192.168.122.122: icmp_seq=346 ttl=64 time=0.323 ms
2026-08-24 10:42:50.886 64 bytes from 192.168.122.122: icmp_seq=347 ttl=64 time=0.330 ms
2026-08-24 10:42:57.029 64 bytes from 192.168.122.122: icmp_seq=353 ttl=64 time=0.254 ms
2026-08-24 10:42:58.053 64 bytes from 192.168.122.122: icmp_seq=354 ttl=64 time=0.285 ms
```

Kiểm tra iperf log:

```bash
tail -n 20 ~/iperf_baseline.log
```

Output cuối bài test:

```text
[  6] 299.00-300.00 sec  5.04 GBytes  43.3 Gbits/sec    0   5.25 MBytes
- - - - - - - - - - - - - - - - - - - - - - - - -
[ ID] Interval           Transfer     Bitrate         Retr
[  6]   0.00-300.00 sec  1.43 TBytes  41.8 Gbits/sec    0             sender
[  6]   0.00-299.99 sec  1.43 TBytes  41.8 Gbits/sec                  receiver

iperf Done.
```

Dừng ping nền:

```bash
kill 2340
```

hoặc:

```bash
pkill -f "ping 192.168.122.122"
```

---

## 3. Kết quả nghiệm thu Lab 1

| Hạng mục | Kết quả |
|---|---|
| Ubuntu host 24.04 | PASS |
| Kernel `6.8.0-134-generic` | PASS |
| Nested virtualization | PASS |
| `/dev/kvm` tồn tại | PASS |
| KVM acceleration | PASS |
| libvirt chạy ổn định | PASS |
| VM1 chạy bằng libvirt | PASS |
| VM2 chạy bằng libvirt | PASS |
| VM1 ↔ VM2 ping | PASS |
| Packet loss baseline | `0%` |
| RTT baseline | khoảng `0.25–0.40 ms` |
| iperf3 TCP | PASS |
| iperf3 average throughput | `41.8 Gbit/s` |
| TCP retransmission | `0` |
| Baseline log phục vụ Lab 3 | PASS |

---

## 4. File/log cần lưu lại

Trên VM1:

```text
~/ping_baseline.log
~/iperf_baseline.log
```

Trên host:

```text
~/kpatch-lab/images/
~/kpatch-lab/cloud-init/
/var/lib/libvirt/images/vm1.qcow2
/var/lib/libvirt/images/vm2.qcow2
/var/lib/libvirt/images/vm1-seed.iso
/var/lib/libvirt/images/vm2-seed.iso
```



---

## 5. Kết luận

Lab 1 đã dựng thành công môi trường KVM nested trên FPT Cloud với host Ubuntu 24.04, kernel `6.8.0-134-generic`, hai VM chạy bằng libvirt và giao tiếp qua default virtual bridge `virbr0`.

