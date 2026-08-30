
## 0. Chuẩn bị

```bash
# Đảm bảo EPT tắt, 2 VM đang chạy, đang có tải MMU liên tục
cat /sys/module/kvm_intel/parameters/ept   # phải ra N
```

Trong VM: `stress-ng --vm 4 --vm-bytes 80% --page-in -t 1800s` 

Trên host: build lại `stall_sim.ko` y như Lab 4.

## 1. Tạo 4 lần kẹt riêng biệt — mỗi lần thử đúng 1 phương án

Vì mỗi phương án cần quan sát độc lập, chạy tuần tự 4 vòng (không dồn cùng lúc), mỗi vòng đều bắt đầu từ trạng thái sạch:

```bash
sudo rmmod stall_sim 2>/dev/null   # đảm bảo module cũ đã gỡ
sudo kpatch list                    # xác nhận chưa có patch nào đang load dở
```

### Vòng 1 — Phương án A: Chờ có kiểm soát

```bash
sudo insmod stall_sim.ko
sudo dmesg -Tw &   # theo dõi log

# Terminal khác, ngay khi thấy "BAT DUOC..."
sudo kpatch load ~/kpatch-lab/livepatch-noble.ko &

# KHÔNG làm gì cả — chỉ theo dõi
watch -n1 'cat /sys/kernel/livepatch/*/transition 2>/dev/null'
```

Vì `stall_sim` giữ busy-wait tối đa 60s bất kể bạn làm gì, "chờ thuần" ở đây sẽ hết hạn theo đúng safety cap chứ không tự giải phóng sớm — mục đích của vòng này là **đo baseline**: transition tự nhiên mất bao lâu nếu không can thiệp gì, để so sánh với các vòng sau. Ghi lại thời điểm `transition complete` hoặc `stalled`.

### Vòng 2 — Phương án B: Kích thích task tự đạt safe state

```bash
sudo insmod stall_sim.ko
sudo dmesg -Tw &
sudo kpatch load ~/kpatch-lab/livepatch-noble.ko &

# Ngay lập tức, thử ép có VM-exit / đổi CPU cho vCPU thread đang kẹt
# 1. Lấy TID của vCPU thread đang chạy trên host (không phải PID QEMU chính)
ps -eLo pid,tid,psr,comm | grep qemu

# 2. Thử di chuyển sang CPU khác (nếu đang pin cố định gây đói)
sudo taskset -pc 2 <TID>

# 3. Hoặc gửi 1 tác động I/O nhẹ vào VM đó qua QEMU monitor để ép VM-exit
virsh qemu-monitor-command <vm-name> --hmp "info status"
```

Ghi lại: transition có hoàn tất **sớm hơn** vòng 1 không, hay do `stall_sim` block cứng bằng `cpu_relax()` trong kprobe handler (context thread bị bắt) nên các tác động "từ bên ngoài" này **không có tác dụng** — đây chính là điểm khác biệt quan trọng bạn đã tự phát hiện ở Lab 4 (busy-wait trong pre_handler chặn đồng bộ, không giống stall do lock nghẽn thông thường). Nếu B không hiệu quả, đó tự nó là 1 kết luận đáng ghi (không phải mọi kiểu "stall" đều xử lý được bằng cách nudge task).

### Vòng 3 — Phương án C: Force transition

```bash
sudo insmod stall_sim.ko
sudo dmesg -Tw &
sudo kpatch load ~/kpatch-lab/livepatch-noble.ko &

# Chờ thấy "stalled" trong log kpatch, rồi force ngay (không đợi hết 60s)
sudo cat /sys/kernel/livepatch/*/transition   # xác nhận vẫn =1
echo 1 | sudo tee /sys/kernel/livepatch/*/force

date '+%H:%M:%S.%N'   # ghi lại thời điểm force
cat /sys/kernel/livepatch/*/transition   # kiểm tra đã về 0 chưa (patched)
```

Đây là bằng chứng thực nghiệm quan trọng nhất của Lab 5: **force có thực sự rút ngắn thời gian transition so với chờ tự nhiên (vòng 1) không**, và **sau khi force, hệ thống có ổn định không** (kiểm tra tiếp):

```bash
# Sau force, kiểm tra hệ thống còn sống khỏe không
dmesg -T | tail -30        # có cảnh báo/oops nào không
sudo kpatch list            # patch đã enabled chưa
ping <vm-ip>                 # VM vẫn hoạt động bình thường
cat /proc/<QEMU_PID>/task/<TID>/stack   # thread bị force có còn "kẹt" logic gì không
```

**Lưu ý an toàn thật sự**: vì `stall_sim` là module tự viết, thread bị bắt vẫn đang **chạy đúng bên trong `handler_pre` chờ `release_now`**, chưa hề return về hàm gốc `__link_shadow_page`/`kvm_mmu_get_child_sp`. Nếu bạn force **trước khi** thread đó thoát khỏi kprobe handler, về lý thuyết task này bị đánh dấu "đã patch" trong khi thực chất vẫn đang treo giữa chừng ở phiên bản code cũ — đây chính là rủi ro mà phần lý thuyết Lab 5 đã cảnh báo. Ghi lại quan sát: sau khi force, task đó khi cuối cùng cũng thoát ra (do bạn `echo 1 > /proc/stall_sim_release`) thì nó chạy tiếp bằng **bản hàm nào** — cách kiểm tra:

```bash
# Sau khi force + release, kiểm tra xem còn log gì bất thường không
echo 1 | sudo tee /proc/stall_sim_release
sudo rmmod stall_sim
dmesg -T | tail -20
```

### Vòng 4 — Phương án D: Unload/hủy patch khi không chắc an toàn

```bash
sudo insmod stall_sim.ko
sudo dmesg -Tw &
sudo kpatch load ~/kpatch-lab/livepatch-noble.ko &

# Chờ thấy stalled, thay vì force -> hủy hẳn
sudo kpatch unload livepatch-noble

date '+%H:%M:%S.%N'
cat /sys/kernel/livepatch/*/transition   # kỳ vọng file biến mất hoặc patch gỡ hoàn toàn
```

Ghi lại: `kpatch unload` trong lúc đang stalled có tự thành công ngay không, hay bản thân lệnh unload **cũng phải đợi transition kết thúc** trước (vì unload về bản chất cũng là 1 dạng transition ngược) — đây là câu hỏi thực nghiệm đáng trả lời, vì nếu đúng vậy thì "hủy patch" không phải lối thoát tức thời như nhiều người tưởng khi task đang kẹt cứng.

