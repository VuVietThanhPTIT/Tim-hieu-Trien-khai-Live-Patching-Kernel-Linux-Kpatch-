# LAB 3 – LIVE PATCH KVM HOST KHI 2 VM ĐANG CHẠY WORKLOAD

## 1. Mục tiêu bài lab

Mục tiêu của Lab 3 là kiểm tra khả năng **live patch kernel trên KVM host đang chạy VM**, sử dụng livepatch module đã tạo ở Lab 2:

```text
~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

Yêu cầu chính cần kiểm chứng:

- Host **không reboot**.
- Không live migrate VM.
- Hai VM vẫn chạy trong lúc patch.
- Có workload mạng liên tục giữa VM1 và VM2.
- Load livepatch vào kernel host.
- Theo dõi:
  - trạng thái transition,
  - trạng thái patch,
  - kernel log,
  - packet loss,
  - latency,
  - TCP throughput,
  - tình trạng VM trước và sau patch.

---

# 2. Mô hình bài lab

```text
                    KVM HOST
          datnt466-kpatch
          Kernel: 6.8.0-134-generic
                    |
          -----------------------
          |                     |
         VM1                   VM2
192.168.122.204         192.168.122.122
          |                     |
          |------ ping -------->|
          |------ iperf3 ------>|
```

Livepatch được load vào **kernel của KVM host**, không phải kernel bên trong VM.

Kernel của guest trong thời điểm test:

```text
VM1: 6.8.0-137-generic
VM2: 6.8.0-137-generic
```

Việc guest chạy kernel khác host không ảnh hưởng đến mục tiêu Lab 3 vì patch được áp vào host KVM:

```text
Host: 6.8.0-134-generic
```

---

# 3. Livepatch module sử dụng

Module được build từ Lab 2:

```text
~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

Tên module:

```text
kvm_mmu_livepatch
```

Target:

```text
6.8.0-134-generic
```

Vermagic đã được kiểm tra ở Lab 2:

```bash
modinfo -F vermagic \
  ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

Output:

```text
6.8.0-134-generic SMP preempt mod_unload modversions
```

---

# 4. Chuẩn bị host trước khi patch

## 4.1. Kiểm tra kernel host

```bash
uname -r
```

Output:

```text
6.8.0-134-generic
```

=> Khớp target của livepatch module.

---

## 4.2. Kiểm tra VM

```bash
virsh list --all
```

Output:

```text
 Id   Name   State
----------------------
 2    vm1    running
 3    vm2    running
```

=> Hai VM đều đang hoạt động trước khi live patch.

---

## 4.3. Kiểm tra livepatch trước khi load

```bash
kpatch list
```

Output:

```text
Loaded patch modules:

Installed patch modules:
```

=> Trước Lab 3 chưa có livepatch nào active.

---

## 4.4. Kiểm tra KVM modules

```bash
lsmod | grep -E '^kvm'
```

Output:

```text
kvm_intel             487424  8
kvm                  1404928  5 kvm_intel
```

=> KVM đang được load và có workload sử dụng.

---

## 4.5. Xác nhận IP của VM

VM1:

```bash
virsh domifaddr vm1
```

Output:

```text
vnet1  52:54:00:27:64:9c  ipv4  192.168.122.204/24
```

VM2:

```bash
virsh domifaddr vm2
```

Output:

```text
vnet2  52:54:00:6d:82:d9  ipv4  192.168.122.122/24
```

---

# 5. Bố trí 5 terminal khi thực hiện Lab 3

Để tránh bỏ sót dữ liệu trong lúc live patch, bài lab sử dụng 5 terminal.

## Terminal 1 – VM2

Vai trò:

```text
iperf3 server
```

Command:

```bash
iperf3 -s
```

Output:

```text
Server listening on 5201
```

---

## Terminal 2 – VM1

Vai trò:

```text
ping liên tục VM1 -> VM2
```

Command:

```bash
mkdir -p ~/lab3-logs

ping -D 192.168.122.122 | tee ~/lab3-logs/ping.log
```

`-D` được dùng để ghi Unix timestamp vào từng ping reply.

Ví dụ baseline trước patch:

```text
[1787628407.869727] ... icmp_seq=1 ... time=0.252 ms
[1787628408.900255] ... icmp_seq=2 ... time=0.297 ms
[1787628409.924235] ... icmp_seq=3 ... time=0.301 ms
...
```

Latency baseline quan sát được chủ yếu khoảng:

```text
0.2 – 0.4 ms
```

---

## Terminal 3 – VM1

Vai trò:

```text
iperf3 TCP client
```

Command:

```bash
iperf3 -c 192.168.122.122 \
  -t 600 \
  -i 1 \
  --logfile ~/lab3-logs/iperf.log
```

Mục tiêu:

- duy trì TCP traffic liên tục,
- đo throughput mỗi giây,
- quan sát retransmission.

---

## Terminal 4 – Host

Vai trò:

```text
theo dõi kernel log
```

Command:

```bash
sudo dmesg -wT
```

---

## Terminal 5 – Host

Vai trò:

```text
load livepatch + kiểm tra transition
```

Đây là terminal thực hiện thao tác chính của Lab 3.

---

# 6. Xác nhận workload KVM trước khi patch

Trên host:

```bash
date '+%F %T.%N'
```

Output:

```text
2026-08-25 10:42:18.625637844
```

Kiểm tra VM:

```bash
virsh list
```

Output:

```text
 Id   Name   State
----------------------
 2    vm1    running
 3    vm2    running
```

Kiểm tra QEMU processes:

```bash
ps -ef | grep qemu-system | grep -v grep
```

Quan sát:

- có process `qemu-system-x86_64` của `vm1`,
- có process `qemu-system-x86_64` của `vm2`,
- cả hai chạy với:

```text
-accel kvm
```

=> Hai guest đang thực sự chạy trên KVM.

---

# 7. Load livepatch

Command:

```bash
sudo kpatch load \
  ~/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko
```

Output:

```text
loading patch module:
/home/ubuntu/kpatch-lab/output-kr134/kvm-mmu-livepatch.ko

waiting (up to 15 seconds) for patch transition to complete...

transition complete (2 seconds)
```

Đây là kết quả quan trọng nhất của bước load.

`kpatch` báo:

```text
transition complete (2 seconds)
```

=> Livepatch đã chuyển xong trạng thái trong thời gian CLI đo khoảng 2 giây.

Lưu ý:

**2 giây transition không có nghĩa là VM downtime 2 giây.**

Transition time là thời gian livepatch framework cần để hoàn tất việc chuyển các task sang trạng thái patch phù hợp.

Downtime phải được đánh giá độc lập bằng ping/workload.

---

# 8. Kiểm tra trạng thái patch sau load

Timestamp sau khi load:

```bash
date '+%F %T.%N'
```

Output:

```text
2026-08-25 10:43:14.223138310
```

Kiểm tra:

```bash
kpatch list
```

Output:

```text
Loaded patch modules:
kvm_mmu_livepatch [enabled]

Installed patch modules:
```

=> Module đã active.

---

# 9. Kiểm tra kernel livepatch sysfs

```bash
ls -l /sys/kernel/livepatch/
```

Output:

```text
kvm_mmu_livepatch
```

Kiểm tra trạng thái:

```bash
grep -R . \
  /sys/kernel/livepatch/*/{enabled,transition} \
  2>/dev/null
```

Output:

```text
/sys/kernel/livepatch/kvm_mmu_livepatch/enabled:1
/sys/kernel/livepatch/kvm_mmu_livepatch/transition:0
```

Giải thích:

```text
enabled = 1
```

=> patch đang enabled.

```text
transition = 0
```

=> hiện tại không còn patch transition đang pending.

Có thể mô tả flow:

```text
kpatch load
    |
    v
transition bắt đầu
    |
    v
các task được chuyển sang patch state phù hợp
    |
    v
transition hoàn tất
    |
    v
enabled = 1
transition = 0
```

---

# 10. Kernel log của livepatch

Command:

```bash
sudo dmesg -T \
  | grep -Ei 'livepatch|kpatch|kvm_mmu|kvm-mmu' \
  | tail -n 50
```

Output:

```text
[Tue Aug 25 10:42:52 2026]
kvm_mmu_livepatch: loading out-of-tree module taints kernel.

[Tue Aug 25 10:42:52 2026]
kvm_mmu_livepatch: tainting kernel with TAINT_LIVEPATCH

[Tue Aug 25 10:42:52 2026]
kvm_mmu_livepatch: module verification failed:
signature and/or required key missing - tainting kernel

[Tue Aug 25 10:42:52 2026]
livepatch: enabling patch 'kvm_mmu_livepatch'

[Tue Aug 25 10:42:52 2026]
livepatch: 'kvm_mmu_livepatch': starting patching transition

[Tue Aug 25 10:42:53 2026]
livepatch: 'kvm_mmu_livepatch': patching complete
```

Timeline từ kernel log:

```text
10:42:52  load module
10:42:52  enable patch
10:42:52  start transition
10:42:53  patching complete
```

Theo độ phân giải timestamp của `dmesg -T`, transition hoàn tất giữa hai timestamp cách nhau khoảng 1 giây.

Theo `kpatch` CLI:

```text
transition complete (2 seconds)
```

Hai số này không mâu thuẫn vì cách đo/timestamp khác nhau.

---

# 11. Module signature warning

Kernel log có:

```text
module verification failed:
signature and/or required key missing - tainting kernel
```

Và:

```text
loading out-of-tree module taints kernel
```

Điều này có nghĩa:

- module lab là out-of-tree module,
- module không được ký bằng key mà kernel hiện tại trust,
- kernel đánh dấu trạng thái `tainted`.

Tuy nhiên đây **không phải lỗi load livepatch**.

Bằng chứng:

```text
livepatch: enabling patch
livepatch: starting patching transition
livepatch: patching complete
```

và:

```text
kvm_mmu_livepatch [enabled]
```

=> patch vẫn load và enable thành công.

Trong production cần xem xét module signing/trusted key policy riêng.

---

# 12. Phân tích ping đúng quanh thời điểm patch

Kernel bắt đầu transition khoảng:

```text
2026-08-25 10:42:52
```

Unix timestamp gần tương ứng:

```text
1787629372
```

Lấy ping quanh cửa sổ này:

```bash
awk '{
  t=$1
  gsub(/\[|\]/,"",t)
  if (t >= 1787629365 && t <= 1787629380) print
}' ~/lab3-logs/ping.log
```

Output:

```text
[1787629365.124143] icmp_seq=123 time=0.215 ms
[1787629366.148119] icmp_seq=124 time=0.212 ms
[1787629367.172201] icmp_seq=125 time=0.228 ms
[1787629368.196076] icmp_seq=126 time=0.169 ms
[1787629369.220116] icmp_seq=127 time=0.181 ms
[1787629370.244205] icmp_seq=128 time=0.242 ms
[1787629371.268094] icmp_seq=129 time=0.155 ms
[1787629372.292121] icmp_seq=130 time=0.195 ms
[1787629373.316229] icmp_seq=131 time=0.240 ms
[1787629374.340297] icmp_seq=132 time=0.351 ms
[1787629375.364181] icmp_seq=133 time=0.220 ms
[1787629376.388081] icmp_seq=134 time=0.161 ms
[1787629377.412191] icmp_seq=135 time=0.256 ms
[1787629378.436269] icmp_seq=136 time=0.347 ms
[1787629379.460251] icmp_seq=137 time=0.282 ms
```

---

# 13. Phân tích packet continuity

Sequence quan sát được:

```text
123
124
125
126
127
128
129
130
131
132
133
134
135
136
137
```

Không có sequence gap.

Đặc biệt quanh đúng transition:

```text
icmp_seq=129  0.155 ms
icmp_seq=130  0.195 ms   <- khoảng thời điểm patch start
icmp_seq=131  0.240 ms   <- sau đó
icmp_seq=132  0.351 ms
```

Kết luận:

```text
Observed packet loss quanh transition: 0 packet
```

Trong cửa sổ đo được, không quan sát thấy packet loss.

---

# 14. Phân tích latency quanh transition

RTT trong cửa sổ trên:

```text
min khoảng 0.155 ms
max khoảng 0.351 ms
```

Latency vẫn nằm cùng order với baseline trước patch.

Không thấy spike kiểu:

```text
10 ms
100 ms
1000 ms
timeout
```

Kết luận:

```text
Không quan sát thấy latency spike đáng kể trong cửa sổ transition.
```

Điều này là bằng chứng mạnh cho việc VM traffic không bị pause rõ rệt ở tầng ICMP.

---

# 15. TCP workload trong quá trình test

Log iperf3 ghi throughput theo từng giây.

Ví dụ:

```text
0.00-1.00 sec   50.7 Gbits/sec  Retr 0
1.00-2.00 sec   53.0 Gbits/sec  Retr 0
2.00-3.00 sec   45.7 Gbits/sec  Retr 0
3.00-4.00 sec   41.8 Gbits/sec  Retr 0
...
20.00-21.00 sec 42.2 Gbits/sec  Retr 0
21.00-22.00 sec 41.0 Gbits/sec  Retr 0
...
60.00-61.00 sec 42.5 Gbits/sec  Retr 0
...
74.00-75.00 sec 41.2 Gbits/sec  Retr 0
75.00-76.00 sec 41.6 Gbits/sec  Retr 0
76.00-76.95 sec 39.9 Gbits/sec  Retr 0
```

Quan sát chung:

```text
throughput chủ yếu ~40–43+ Gbit/s
Retr = 0
```

---

# 16. Giới hạn của log iperf trong lần đo này

File:

```text
~/lab3-logs/iperf.log
```

ghi thời gian tương đối:

```text
0.00-1.00
1.00-2.00
2.00-3.00
...
```

nhưng không có wall-clock timestamp cho từng interval.

Vì vậy không thể map tuyệt đối từng dòng iperf vào chính xác:

```text
10:42:52
```

chỉ từ logfile này.

Do đó khi audit không nên viết:

> “iperf tại chính xác giây livepatch chắc chắn là X Gbit/s”

mà nên viết:

> TCP workload được duy trì trong quá trình test; các interval ghi nhận trong logfile chủ yếu khoảng 40–43 Gbit/s và không có retransmission. Bằng chứng có timestamp trực tiếp quanh transition được lấy từ ping log.

Đây là giới hạn đo đạc cần ghi rõ.

---

# 17. Kiểm tra hậu-patch – trạng thái VM

Sau patch:

```bash
virsh list
```

Output:

```text
 Id   Name   State
----------------------
 2    vm1    running
 3    vm2    running
```

=> Hai VM vẫn hoạt động.

Không có:

```text
shutdown
paused
crashed
migrated
```

---

# 18. Kiểm tra hậu-patch – trạng thái livepatch

```bash
kpatch list
```

Output:

```text
Loaded patch modules:
kvm_mmu_livepatch [enabled]
```

=> livepatch vẫn active.

---

# 19. Kiểm tra hậu-patch – kernel log

```bash
sudo dmesg -T | tail -n 30
```

Phần cuối liên quan patch:

```text
kvm_mmu_livepatch: loading out-of-tree module taints kernel.
kvm_mmu_livepatch: tainting kernel with TAINT_LIVEPATCH
kvm_mmu_livepatch: module verification failed:
signature and/or required key missing - tainting kernel

livepatch: enabling patch 'kvm_mmu_livepatch'
livepatch: 'kvm_mmu_livepatch': starting patching transition
livepatch: 'kvm_mmu_livepatch': patching complete
```

Không quan sát thấy các lỗi nghiêm trọng như:

```text
kernel panic
Oops
BUG
general protection fault
KVM crash
QEMU crash
```

trong output kiểm tra hậu-patch.

---

# 20. Ping hậu-patch

Command:

```bash
ping -c 10 192.168.122.122
```

Output:

```text
10 packets transmitted
10 received
0% packet loss
```

RTT:

```text
min/avg/max/mdev
=
0.194/0.343/0.412/0.060 ms
```

=> Sau livepatch, connectivity giữa VM1 và VM2 vẫn bình thường.

---

# 21. iperf3 hậu-patch

Command:

```bash
iperf3 -c 192.168.122.122 -t 10 -i 1
```

Output theo giây:

```text
0.00-1.00   51.6 Gbits/sec   Retr 0
1.00-2.00   45.3 Gbits/sec   Retr 0
2.00-3.00   40.9 Gbits/sec   Retr 0
3.00-4.00   40.4 Gbits/sec   Retr 0
4.00-5.00   41.4 Gbits/sec   Retr 0
5.00-6.00   40.5 Gbits/sec   Retr 0
6.00-7.00   40.1 Gbits/sec   Retr 0
7.00-8.00   41.3 Gbits/sec   Retr 0
8.00-9.00   41.4 Gbits/sec   Retr 0
9.00-10.00  41.3 Gbits/sec   Retr 0
```

Summary:

```text
49.4 GBytes
42.4 Gbits/sec
Retr = 0
```

=> TCP throughput sau patch vẫn ở mức tương đương baseline của lab và không có retransmission trong test 10 giây.

---

# 22. Bảng tổng hợp kết quả

| Hạng mục | Trước patch | Trong / quanh transition | Sau patch |
|---|---|---|---|
| VM1 | running | không thấy dừng | running |
| VM2 | running | không thấy dừng | running |
| Host reboot | không | không | không |
| VM migration | không | không | không |
| Livepatch | chưa load | transition | enabled |
| Transition | 0 | start -> complete | 0 |
| Ping | ~0.2–0.4 ms | ~0.155–0.351 ms | avg 0.343 ms |
| Packet loss | không thấy | không thấy sequence gap | 0% / 10 packets |
| TCP | ~40+ Gbit/s | workload duy trì | 42.4 Gbit/s |
| Retransmission | 0 trong log | không quan sát lỗi connection | 0 |
| Kernel panic/Oops | không | không quan sát | không quan sát |

---

# 23. Timeline Lab 3

```text
Trước 10:42:52
|
| VM1 running
| VM2 running
| ping running
| iperf3 running
|
10:42:52
|
| livepatch module được load
| enabling patch
| starting patching transition
|
10:42:53
|
| patching complete
|
| ping seq vẫn liên tục
| không quan sát packet loss
| không thấy latency spike đáng kể
|
Sau patch
|
| kvm_mmu_livepatch [enabled]
| enabled = 1
| transition = 0
| VM1 running
| VM2 running
| ping 0% loss
| iperf3 42.4 Gbit/s, Retr 0
```

---

# 24. Liên hệ transition state

Trong Linux livepatch/kpatch, việc load module không nhất thiết đồng nghĩa mọi task chuyển sang code mới ngay tại cùng một CPU instruction.

Có một giai đoạn:

```text
transition state
```

Trong lab, bằng chứng của transition:

```text
livepatch:
'kvm_mmu_livepatch':
starting patching transition
```

Sau đó:

```text
livepatch:
'kvm_mmu_livepatch':
patching complete
```

Và cuối cùng:

```text
transition = 0
```

=> Không còn transition pending.

---

# 25. Liên hệ safe state

Trong quá trình transition, livepatch framework phải đảm bảo task được chuyển trạng thái một cách nhất quán.

Khái niệm quan trọng:

```text
per-task consistency
```

Mục tiêu là tránh một task rơi vào tình trạng không nhất quán giữa implementation cũ và implementation mới.

Có thể mô tả đơn giản:

```text
task đang ở trạng thái cũ
        |
        v
đạt điểm phù hợp để chuyển
        |
        v
task chuyển patch state
        |
        v
sử dụng implementation mới
```

Không nên hiểu “safe state” quá đơn giản thành:

> “toàn bộ hệ thống phải dừng”

Lab cho thấy điều ngược lại:

- transition vẫn diễn ra,
- VM workload vẫn tiếp tục,
- ping không thấy mất gói,
- host không reboot.

---

# 26. Vì sao transition 2 giây nhưng không thấy downtime?

Hai khái niệm khác nhau:

## Transition duration

Thời gian kernel livepatch framework cần để hoàn thành quá trình chuyển trạng thái.

Trong lab:

```text
~2 giây theo kpatch CLI
```

## Service downtime

Khoảng thời gian workload bên ngoài không được phục vụ.

Đo bằng:

- packet loss,
- timeout,
- latency spike,
- TCP disruption,
- application failure.

Trong lab:

```text
không quan sát packet loss quanh transition
không thấy RTT spike đáng kể
VM vẫn running
```

Do đó:

```text
transition time != downtime
```

---

# 27. Kết quả zero / near-zero downtime

Kết quả của bài lab hỗ trợ kết luận:

> Trong điều kiện workload của Lab 3, livepatch được áp dụng vào KVM host mà không quan sát thấy downtime ở tầng ping giữa hai VM.

Bằng chứng:

```text
icmp_seq=123 -> 137 liên tục
```

đúng quanh transition.

Không có:

```text
Request timeout
Destination unreachable
sequence gap
```

RTT vẫn ở mức sub-millisecond.

Do độ phân giải phép đo ping khoảng 1 packet/giây, kết luận chính xác nên dùng:

```text
No observable downtime at the measurement granularity used in this lab.
```

Không nên khẳng định tuyệt đối:

```text
downtime vật lý = 0 nanosecond
```

vì phép đo hiện tại không có độ phân giải đủ để chứng minh điều đó.

---

# 28. Điểm cần cải thiện nếu audit sâu hơn

Nếu cần đo chính xác hơn trong lần test sau, có thể:

1. Ping với interval ngắn hơn, nếu môi trường/lab cho phép.
2. Gắn wall-clock timestamp cho iperf interval.
3. Thu CPU scheduling / trace data.
4. Theo dõi `/sys/kernel/livepatch/.../transition` liên tục.
5. Theo dõi per-task patch state nếu cần lab transition sâu.
6. Dùng workload có khả năng đi vào KVM MMU path thường xuyên hơn.
7. Capture kernel trace/ftrace nếu cần chứng minh function redirection.
8. Dùng nhiều vòng test để giảm khả năng kết luận từ một sample duy nhất.

---

# 29. Điều chưa được chứng minh ở Lab 3

Lab 3 chứng minh được:

```text
livepatch load thành công
transition hoàn tất
VM tiếp tục chạy
không quan sát thấy packet loss quanh transition
network workload vẫn hoạt động
```

Lab 3 **chưa chứng minh**:

- mọi loại workload đều không downtime,
- mọi KVM MMU code path đều đã bị exercise,
- mọi task luôn transition trong 1–2 giây,
- không tồn tại bất kỳ interruption ở độ phân giải microsecond/nanosecond,
- patch này phù hợp production ngay lập tức.

Những vấn đề này cần lab chuyên sâu hơn.

---

# 30. Checklist audit Lab 3

| Hạng mục | Trạng thái |
|---|---|
| Kernel host đúng target | PASS |
| VM1 running trước patch | PASS |
| VM2 running trước patch | PASS |
| QEMU dùng KVM acceleration | PASS |
| Ping workload active | PASS |
| TCP workload active | PASS |
| Kernel log monitoring | PASS |
| Livepatch load | PASS |
| Patch transition start | PASS |
| Patch transition complete | PASS |
| Patch enabled | PASS |
| transition=0 sau load | PASS |
| Không reboot host | PASS |
| Không migrate VM | PASS |
| Ping sequence quanh patch liên tục | PASS |
| Không quan sát packet loss quanh transition | PASS |
| Không thấy RTT spike đáng kể | PASS |
| VM1 running sau patch | PASS |
| VM2 running sau patch | PASS |
| Post-patch ping 0% loss | PASS |
| Post-patch iperf ~42.4 Gbit/s | PASS |
| Post-patch Retr=0 | PASS |
| Module signature trusted | WARNING / chưa ký trusted key |

---

# 31. Kết luận Lab 3

Livepatch:

```text
kvm_mmu_livepatch
```

đã được load thành công vào KVM host:

```text
6.8.0-134-generic
```

trong khi:

```text
VM1 đang running
VM2 đang running
ping đang chạy
TCP workload đang chạy
```

Kernel log xác nhận:

```text
starting patching transition
patching complete
```

`kpatch` xác nhận:

```text
transition complete (2 seconds)
```

Sau transition:

```text
enabled = 1
transition = 0
```

Ping có timestamp quanh đúng cửa sổ transition cho thấy:

```text
icmp_seq=123 -> icmp_seq=137
```

liên tục, không có sequence gap.

RTT quanh transition:

```text
~0.155 – 0.351 ms
```

Post-patch ping:

```text
0% packet loss
avg RTT = 0.343 ms
```

Post-patch TCP:

```text
42.4 Gbit/s
Retr = 0
```

Hai VM tiếp tục:

```text
running
```

mà không:

```text
reboot host
live migrate VM
```

## Kết luận kỹ thuật

Trong điều kiện workload và độ phân giải đo của Lab 3, **không quan sát thấy downtime của VM connectivity khi áp livepatch lên KVM host**.

Livepatch transition diễn ra trong khoảng 1–2 giây theo log/tooling, nhưng transition duration không đồng nghĩa với service downtime.

Kết quả lab minh họa mục tiêu quan trọng của live kernel patching:

```text
patch kernel host
+
không reboot
+
không migrate VM
+
workload vẫn tiếp tục hoạt động
```

Đây là cơ sở để chuyển sang Lab 4, nơi cần chủ động nghiên cứu trường hợp **transition bị stalled do task không đạt trạng thái phù hợp để hoàn tất patching**.
