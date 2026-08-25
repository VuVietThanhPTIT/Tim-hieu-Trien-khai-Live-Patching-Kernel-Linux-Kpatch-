
# Lab 4 

**Host:** Ubuntu 24.04 live server — kernel `6.8.0-134.134-generic` **Patch:** `livepatch-noble.ko` (build từ `noble.patch` bằng `kpatch-build`, sửa 2 hàm trong `kvm.ko`: `__link_shadow_page`, `kvm_mmu_get_child_sp`)

---

## 1. Mục tiêu Lab 4

Giả lập 1 tiến trình userspace `qemu-system-x86_64` (của 1 trong 2 VM đang chạy) bị **stalled** đúng lúc `kpatch load` đang chạy, để trả lời 4 câu hỏi:

1. Tại sao không thể đạt được safe state?
2. Transition kẹt bao lâu thì coi là thất bại?
3. Khi thất bại, kernel có tự rollback không?
4. Ftrace của các process đã transition xong có bị loạn không?

---

## 2. Bối cảnh kỹ thuật — vì sao 2 hàm này khó bị "bắt gọn"

### 2.1. EPT vs Shadow Paging

Khi VM chạy, cần dịch địa chỉ 2 tầng (guest ảo → guest "vật lý" → vật lý thật). Có 2 cách:

- **EPT (mặc định, phần cứng lo):** CPU tự dịch tầng 2 bằng mạch chuyên dụng. Khi bật, 2 hàm bị patch **gần như không bao giờ được gọi**.
- **Shadow Paging (tắt EPT, `ept=0`):** kernel host phải tự dựng bảng dịch bằng phần mềm — chính là lúc `__link_shadow_page` và `kvm_mmu_get_child_sp` được gọi, mỗi khi guest gặp page fault mới.

→ Điều kiện bắt buộc đầu tiên: **tắt EPT** để 2 hàm bị patch thực sự chạy.

### 2.2. Hàm chạy quá nhanh

Đo bằng bpftrace xác nhận: dưới tải `stress-ng --page-in`, `kvm_mmu_get_child_sp` được gọi tới **~192.000 lần/giây** — nhưng mỗi lần chỉ chạy trong vài **micro giây**. Đây là lý do các cách "đứng ngoài quan sát rồi phản ứng" đều thất bại hoặc không đáng tin cậy.

---

## 3. Các hướng đã thử (theo thứ tự thời gian)

### Hướng 1 — Polling bằng Bash (`/proc/<pid>/task/<tid>/stack`)

```bash
while [ -z "$STOPPED_TID" ]; do
  for TID in $(ls /proc/"$QEMU_PID"/task/); do
    cat "/proc/$QEMU_PID/task/$TID/stack" | grep -q "$FN" && kill -SIGSTOP "$TID"
  done
  sleep 0.01
done
```

**Kết quả: KHÔNG bắt được.** **Nguyên nhân:** mỗi vòng lặp bash phải `fork` tiến trình con (`cat`) — chi phí spawn process (vài ms) làm tốc độ polling thực tế chậm hơn nhiều so với con số `sleep 0.01` (10ms) tưởng như vậy. So với tần suất hàm chạy (micro giây), xác suất trúng gần như 0.

### Hướng 2 — Polling bằng Python (đọc file trực tiếp, không spawn process)

```python
fd = os.open(path, os.O_RDONLY)
data = os.read(fd, 65536)
os.close(fd)
```

**Kết quả: nhanh hơn Bash nhiều nhưng vẫn không đáng tin cậy 100%** — vẫn là polling theo mẫu (sampling), có thể bỏ lỡ khoảng thời gian giữa 2 lần đọc.

### Hướng 3 — bpftrace kprobe + `signal("SIGSTOP")`

```bash
sudo bpftrace --unsafe -e '
kprobe:__link_shadow_page,kprobe:kvm_mmu_get_child_sp
{
    printf("%s | TID=%d\n", strftime("%H:%M:%S.%f", nsecs), tid);
    signal("SIGSTOP");
    exit();
}'
```

**Kết quả: BẮT ĐƯỢC sự kiện (log in ra đúng lúc), nhưng `kpatch load` sau đó vẫn chạy trót lọt, không hề kẹt (`transition complete (2 seconds)`).**

**Nguyên nhân cốt lõi (bài học quan trọng nhất):** `SIGSTOP` gửi tới 1 task đang chạy **trong kernel** không dừng nó NGAY LẬP TỨC tại đúng câu lệnh — kernel chỉ đặt cờ "có tín hiệu chờ", và chỉ thực sự kiểm tra cờ đó ở các điểm cố định (chủ yếu là lúc task chuẩn bị return về userspace). Vì hàm bị patch chạy xong trong vài micro giây — nhanh hơn nhiều so với thời gian tới điểm kiểm tra cờ — nên thread **đã thoát khỏi hàm bị patch từ lâu** trước khi thực sự bị dừng. Lúc đó stack sạch, livepatch coi là an toàn, transition qua trót lọt.

**Bài học:** `signal()` là cơ chế **bất đồng bộ**, không phù hợp để "khoá cứng" một task đúng tại một điểm code cụ thể.

###  Xác minh tần suất gọi hàm 
```bash
sudo timeout 10 bpftrace -e '
kprobe:__link_shadow_page,kprobe:kvm_mmu_get_child_sp
{ @calls[func] = count(); }'
```

Kết quả đo được: `kvm_mmu_get_child_sp: 1926918` lần trong 10s (~192.700 lần/giây). Xác nhận: điều kiện EPT tắt + `stress-ng` đã đúng, vấn đề chỉ nằm ở khâu "cách bắt", không phải "chưa đủ điều kiện".

### Hướng 5 — Kernel module với busy-wait cố định (2s, sau đó 5s)

```c
static int handler_pre(struct kprobe *p, struct pt_regs *regs) {
    if (triggered) return 0;
    triggered = true;
    start = jiffies;
    while (time_before(jiffies, start + N*HZ)) {
        cpu_relax();
    }
    return 0;
}
```

**Kết quả: BẮT ĐƯỢC và GIỮ ĐƯỢC thật (khác hẳn signal) — nhưng thời gian giữ cố định (2s rồi 5s) không đủ để phản ứng tay** (chuyển terminal, gõ lệnh `kpatch load` kịp trong cửa sổ đó).

**Đây là bước ngoặt quan trọng:** khác với `signal()`, vòng lặp `while` bên trong chính kprobe handler (context của thread đang chạy) **chặn CPU đồng bộ, ngay tại đúng dòng code** — vì `pre_handler` của kprobe chạy trong chính ngữ cảnh của thread bị bắt, trước khi nó kịp chạy tiếp hàm gốc. Đây mới là cách thật sự tạo ra "stalled process" đúng nghĩa.

**Lưu ý an toàn:** 2 hàm này chạy trong lúc giữ `mmu_lock` (spinlock) của KVM — busy-wait tại đây có nguy cơ gây `soft lockup`/treo VM nếu giữ quá lâu. Cần giới hạn thời gian.

---

## 4. Hướng thành công — Kernel module với điều khiển thả tay qua `/proc`

### 4.1. Thiết kế

Thay vì hẹn giờ cố định, module:

- Bắt đúng khoảnh khắc 1 trong 2 hàm bị patch được gọi (dùng `kprobe`, giống hướng 5)
- Giữ CPU bằng busy-wait (`cpu_relax()`) **cho tới khi nhận lệnh thả** qua file `/proc/stall_sim_release`
- Có giới hạn an toàn tự động: tối đa 60 giây nếu quên thả tay (tránh treo VM vĩnh viễn)

### 4.2. Code chính (rút gọn — bản đầy đủ trong file `stall_sim.c` đính kèm riêng)

```c
#include <linux/module.h>
#include <linux/kprobes.h>
#include <linux/jiffies.h>
#include <linux/proc_fs.h>
#include <linux/atomic.h>

static struct kprobe kp1, kp2;
static bool triggered = false;
static atomic_t release_now = ATOMIC_INIT(0);
#define SAFETY_CAP_SECONDS 60

static int handler_pre(struct kprobe *p, struct pt_regs *regs)
{
    unsigned long start, cap_end;
    if (triggered) return 0;
    triggered = true;
    atomic_set(&release_now, 0);

    pr_info("stall_sim: BAT DUOC %s tren CPU%d, PID=%d\n",
            p->symbol_name, smp_processor_id(), current->pid);

    start = jiffies;
    cap_end = start + SAFETY_CAP_SECONDS * HZ;
    while (!atomic_read(&release_now) && time_before(jiffies, cap_end))
        cpu_relax();

    return 0;
}

static ssize_t release_write(struct file *f, const char __user *buf,
                              size_t count, loff_t *ppos)
{
    atomic_set(&release_now, 1);
    return count;
}
static const struct proc_ops release_fops = { .proc_write = release_write };

static int __init stall_init(void)
{
    proc_create("stall_sim_release", 0222, NULL, &release_fops);
    kp1.symbol_name = "__link_shadow_page";  kp1.pre_handler = handler_pre;
    kp2.symbol_name = "kvm_mmu_get_child_sp"; kp2.pre_handler = handler_pre;
    register_kprobe(&kp1);
    register_kprobe(&kp2);
    return 0;
}
module_init(stall_init);
MODULE_LICENSE("GPL");
```

### 4.3. Quy trình chạy đầy đủ

**Chuẩn bị môi trường (1 lần):**

```bash
virsh shutdown vm1; virsh shutdown vm2
sudo modprobe -r kvm_intel; sudo modprobe -r kvm
sudo modprobe kvm; sudo modprobe kvm_intel ept=0
echo "options kvm_intel ept=0" | sudo tee /etc/modprobe.d/kvm_intel_ept.conf
cat /sys/module/kvm_intel/parameters/ept   # phải ra N
virsh start vm1; virsh start vm2
```

**Trong VM (tạo tải MMU liên tục):**

```bash
stress-ng --vm 4 --vm-bytes 80% --page-in -t 1800s
```

_(Không dùng `--vm-keep` — flag này giữ nguyên vùng nhớ đã cấp, khiến page fault chỉ xảy ra ở những giây đầu rồi ngưng hẳn.)_

**Trên HOST — build & chạy module:**

```bash
cd ~/stall-module
make clean && make
sudo insmod stall_sim.ko
sudo dmesg -Tw
```

**Ngay khi thấy `BAT DUOC ...` — terminal khác, không vội:**

```bash
sudo kpatch load ~/kpatch-lab/livepatch-noble.ko &
sudo kpatch list
```

**Sau khi lấy đủ bằng chứng — thả tay:**

```bash
echo 1 | sudo tee /proc/stall_sim_release
sudo rmmod stall_sim
```

---

## 5. Bằng chứng thu được (log thật)

```
loading patch module: /root/kpatch-lab/livepatch-noble.ko
waiting (up to 15 seconds) for patch transition to complete...
patch transition has stalled!
kpatch: Livepatch process signaling is performed automatically on your system.
kpatch: Skipping manual process signaling.
waiting (up to 60 seconds) for patch transition to complete...
transition complete (30 seconds)
```

---

## 6. Trả lời 4 câu hỏi của Lab 4 (dựa trên bằng chứng thu được + tài liệu chính thức)

**Q1 — Tại sao không thể đạt safe state?** Livepatch chỉ chuyển 1 task sang code mới an toàn khi: (a) stack của nó lúc sleep không chứa hàm bị patch, hoặc (b) nó vừa return về userspace/qua 1 syscall boundary. vCPU thread của QEMU chạy trong ioctl `KVM_RUN` (không return thường xuyên) và trong lúc tải cao, liên tục có mặt trong `__link_shadow_page`/`kvm_mmu_get_child_sp` trên call stack — cả 2 điều kiện an toàn đều bị vô hiệu.

**Q2 — Bao lâu thì thất bại?** Không có timeout ở tầng **kernel** (có thể kẹt vô thời hạn). Tầng **công cụ `kpatch`** có timeout riêng: chờ 15s → nếu vẫn kẹt, báo "stalled!" và tự gửi tín hiệu (do kernel tự làm, kpatch tool skip bước signal thủ công) → chờ thêm tối đa 60s. Trong lần đo thực tế: **30 giây**.

**Q3 — Kernel có tự rollback khi thất bại không?** Không tự động ở tầng kernel thuần (`echo 0 > enabled` mới hủy). Nhưng **công cụ `kpatch`** (userspace) có: nếu quá 60s vẫn kẹt, nó tự unload module — đây là hành vi của tool, không phải chính sách mặc định của kernel livepatch core.

**Q4 — Ftrace của process đã transition xong có bị loạn không?** Không. Thiết kế "per-task consistency model" cho phép tồn tại trạng thái trộn (1 số task đã patch, 1 số chưa) an toàn — mỗi hàm có 1 danh sách (`klp_ops`) các phiên bản, ftrace handler route đúng bản tương ứng theo từng task qua `/proc/<pid>/patch_state`.

---

## 7. Bài học kỹ thuật rút ra

| Vấn đề                                          | Bài học                                                                                                                       |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Bash polling không bắt được                     | Overhead spawn process trong bash làm chậm hơn tưởng — không phù hợp để bắt sự kiện cực nhanh                                 |
| bpftrace `signal()` không giữ được              | `SIGSTOP` là bất đồng bộ — không dừng ngay tại điểm code, chỉ có tác dụng khi task quay lại điểm kiểm tra tín hiệu            |
| bpftrace không thể busy-wait                    | BPF verifier cấm vòng lặp không giới hạn; ngữ cảnh atomic (đang giữ spinlock) cấm sleep                                       |
| Giải pháp cuối: module + điều khiển `/proc`     | Tách rời "bắt" và "thả", cho phép kiểm soát hoàn toàn thời điểm, kèm giới hạn an toàn tự động (60s) để tránh treo VM nếu quên |
| `--vm-keep` trong stress-ng                     | Cần bỏ flag này — nó khiến page fault chỉ xảy ra 1 lần đầu, không liên tục                                                    |

---

## 8. Liên kết sang Lab 5 (phương án xử lý)

Log thực tế cho thấy chính `kpatch` tool đã tự thực hiện đúng phương án gửi "fake signal" cho task chặn trong 15s đầu, và tự rollback/unload sau 60s nếu vẫn kẹt — đúng như đã trình bày trong phần lý thuyết Lab 5 trước đó. Phương án `force` (`echo 1 > .../force`) chỉ cần dùng khi cả 2 cơ chế tự động này đều không đủ và cần can thiệp thủ công khẩn cấp.





![](img/Pasted%20image%2020260825153441.png)
	 

![](img/Pasted%20image%2020260825153441.png)

![](img/Pasted%20image%2020260825153454.png)


### Tham khảo : 
[Chapter 22. Applying patches with kernel live patching | Managing, monitoring, and updating the kernel | Red Hat Enterprise Linux | 8 | Red Hat Documentation](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/managing_monitoring_and_updating_the_kernel/applying-patches-with-kernel-live-patching_managing-monitoring-and-updating-the-kernel)

[How to build an Ubuntu Linux kernel - Ubuntu Kernel documentation](https://ubuntu.com/kernel/docs/how-to/develop-customise/build-kernel/)

[A rough patch for live patching [LWN.net]](https://lwn.net/Articles/634649/)
[Livepatch — The Linux Kernel documentation](https://docs.kernel.org/livepatch/livepatch.html)

[Everything You Wanted to Know About Kernel Livepatch in Ubuntu · Matthew Ruffell](https://ruffell.nz/programming/writeups/2020/04/20/everything-you-wanted-to-know-about-kernel-livepatch-in-ubuntu.html)