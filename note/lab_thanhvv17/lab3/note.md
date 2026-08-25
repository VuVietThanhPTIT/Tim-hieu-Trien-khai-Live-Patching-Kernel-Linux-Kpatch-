# Lab 3

**Host:** Ubuntu 24.04 live server — kernel `6.8.0-134.134-generic` **Patch:** `livepatch-noble.ko` (build từ `noble.patch` bằng `kpatch-build`, sửa 2 hàm trong `kvm.ko`: `__link_shadow_page`, `kvm_mmu_get_child_sp`) **Topology:** 2 VM (`vm1`, `vm2`) chạy qua libvirt, bridge network. `vm2 = 192.168.100.51`

---

## 1. Mục tiêu Lab 3

Nạp `kpatch load` vào host trong khi `vm1` và `vm2` đang trao đổi traffic liên tục (ping + iperf3 TCP + UDP), để trả lời:

1. Đường ping giữa 2 VM có bị gián đoạn khi host load kpatch không?
2. Nếu gián đoạn, mức độ (số gói mất, độ trễ tăng) là bao nhiêu?
3. TCP/UDP throughput và retransmit/jitter có bị ảnh hưởng không?

So sánh 2 giai đoạn: **BASELINE** (host chưa làm gì) vs **DURING** (host đang `kpatch load`).

---

## 2. Chuẩn bị

### 2.1. VM2 — Receiver / Server

Mở sẵn 2 iperf3 server (TCP port 5201, UDP port 5202), chạy nền, log ra file:

```bash
# Dọn tiến trình iperf3 cũ đang chiếm port
sudo killall -9 iperf3 2>/dev/null

# Server TCP — cổng mặc định 5201
iperf3 -s -D --logfile ~/iperf3-tcp-server.log

# Server UDP — cổng 5202
iperf3 -s -p 5202 -D --logfile ~/iperf3-udp-server.log

# Xác nhận cả 2 process đang chạy
pgrep -a iperf3
```

Kỳ vọng thấy 2 PID: 1 cho TCP (5201), 1 cho UDP (5202).

### 2.2. VM1 — Sender / Client

```bash
IP_VM2="192.168.100.51"
```

---

## 3. Giai đoạn 1 — BASELINE (60s, host chưa động gì)

Chạy đồng thời 3 tiến trình đo trên VM1:

```bash
IP_VM2="192.168.100.51"

# 1. Ping micro-latency: 1 gói mỗi 50ms, kèm timestamp hệ thống ở đầu mỗi dòng
ping -i 0.05 "$IP_VM2" | while read -r line; do echo "$(date '+%H:%M:%S.%N') $line"; done > ~/ping-baseline.log &

# 2. TCP: đo băng thông + retransmit, 60s, báo cáo mỗi 1s
iperf3 -c "$IP_VM2" -t 60 -i 1 --logfile ~/tcp-baseline.log &

# 3. UDP: đo jitter + tỷ lệ rớt gói, ép băng thông 700Mbps, 60s
iperf3 -c "$IP_VM2" -p 5202 -u -b 700M -t 60 -i 1 --logfile ~/udp-baseline.log &
```

Chờ đủ 60s cho baseline chạy xong hoàn toàn trước khi sang giai đoạn 2 — đây là mốc đối chứng "hệ thống bình thường" để so sánh độ lệch ở giai đoạn DURING.

---

## 4. Giai đoạn 2 — DURING (120s, nạp kpatch giữa chừng)

### 4.1. Trên VM1 — bắn traffic kéo dài 120s

```bash
IP_VM2="192.168.100.51"

ping -i 0.05 "$IP_VM2" | while read -r line; do echo "$(date '+%H:%M:%S.%N') $line"; done > ~/ping-during.log &
iperf3 -c "$IP_VM2" -t 120 -i 1 --logfile ~/tcp-during.log &
iperf3 -c "$IP_VM2" -p 5202 -u -b 700M -t 120 -i 1 --logfile ~/udp-during.log &
```

### 4.2. Trên Host — script nạp patch + theo dõi transition song song

```bash
#!/bin/bash
KPATCH_FILE=~/kpatch-lab/livepatch-noble.ko

sudo -v

# Ghi toàn bộ dmesg trong lúc patch chạy
sudo dmesg -T -w > ~/host-dmesg.log 2>&1 &
DMESG_PID=$!

# Theo dõi trạng thái transition mỗi 50ms
(
  while true; do
    TRANS=$(cat /sys/kernel/livepatch/*/transition 2>/dev/null || echo "0")
    STATE=$(cat /sys/kernel/livepatch/*/enabled 2>/dev/null || echo "0")
    echo "$(date '+%H:%M:%S.%N') trans=$TRANS enabled=$STATE"
    sleep 0.05
  done
) > ~/host-transition.log 2>&1 &
TRACKER_PID=$!

# Đợi 10s cho traffic VM1↔VM2 ổn định trước khi patch
sleep 10

echo "LOAD_START: $(date '+%H:%M:%S.%N')" >> ~/host-kpatch.log
sudo kpatch load "$KPATCH_FILE" >> ~/host-kpatch.log 2>&1
echo "LOAD_END:   $(date '+%H:%M:%S.%N')" >> ~/host-kpatch.log

# Đợi thêm 10s sau load rồi dọn các tiến trình theo dõi
sleep 10
kill "$TRACKER_PID" 2>/dev/null
sudo kill "$DMESG_PID" 2>/dev/null
```



---

## 6. Đối chiếu với `host-transition.log` và `host-dmesg.log`

- `host-transition.log`: xem cột `trans=` chuyển từ `1` (đang transition) về mất hẳn dòng hoặc không còn file (patch đã `enabled=1` ổn định) — đo được đúng khoảng thời gian transition kéo dài bao lâu trong điều kiện traffic bình thường (không cố tình gây stall như Lab 4).
- `host-dmesg.log`: tìm dòng liên quan `livepatch`/tên patch để xác nhận thời điểm transition complete, đối chiếu với `LOAD_START`/`LOAD_END` trong `host-kpatch.log`.

---


![](img/Pasted%20image%2020260824223837.png)![](img/Pasted%20image%2020260824223934.png)

![](../lab4/img/Pasted%20image%2020260824224233.png)