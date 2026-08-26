# 09 – Observability, Troubleshooting và Recovery cho Livepatch Systems

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [Các lớp observability: CLI, sysfs, log, task, thread và stack](#1-các-lớp-observability-cli-sysfs-log-task-thread-và-stack)
3. [Chẩn đoán stalled transition](#2-chẩn-đoán-stalled-transition)
4. [Recovery ladder và nguyên tắc không phản xạ kill workload](#3-recovery-ladder-và-nguyên-tắc-không-phản-xạ-kill-workload)
5. [Các failure mode ngoài stalled transition](#4-các-failure-mode-ngoài-stalled-transition)
6. [Evidence, case KVM, force checklist và post-incident](#5-evidence-case-kvm-force-checklist-và-post-incident)
7. [Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **Observability** | System Observability (Khả năng quan sát hệ thống) | Khả năng theo dõi trạng thái nội tại của hệ thống Livepatch qua procfs, sysfs và log. |
| **Recovery Ladder** | Multi-tier Escalation Plan (Thang ứng phó phân tầng) | Kịch bản ứng phó sự cố phân tầng theo mức độ rủi ro (Wait -> Quiesce -> Signal -> Reverse -> Force -> Reboot). |
| **Force Transition** | Forced Patch Switch (Cưỡng bức chuyển đổi) | Thao tác cưỡng bức ghi đè `transition = 0` bỏ qua Safe State (Rủi ro cao, yêu cầu Reboot sau đó). |
| **Quiesce** | Quiesce Workload (Tạm dừng/Giảm tải Workload) | Việc chủ động giảm tải hoặc tạm dừng giao dịch workload để tạo cơ hội cho Task đạt Safe State. |

---

## Chuỗi chẩn đoán và recovery

```text
LIVEPATCH OPERATION
       │
       ▼
 transition kéo dài?
    /       \
  Không      Có
   │          │
   ▼          ▼
 DONE   Collect evidence
             │
             ▼
        identify blocker
             │
             ▼
        inspect stack
             │
             ▼
       recovery ladder
             │
   +---------+----------+-----------+
   │         │          │           │
  wait     quiesce    signal     reverse
                                       │
                                       ▼
                               force (last resort)
                                       │
                                       ▼
                              migrate / reboot
```

---

## 1. Các lớp observability: CLI, sysfs, log, task, thread và stack

### Nguyên tắc vận hành

> **Observe → Identify → Explain → Mitigate → Reverse/Force/Fallback**

Khi hệ thống Livepatch phát sinh bất thường, quy tắc vàng là **không được vội vã đưa ra quyết định xử lý khi chưa thu thập đủ thông tin quan sát**.

```text
                        6 LỚP OBSERVABILITY CỦA LIVEPATCH
                                       │
     ┌──────────────┬──────────────┬───┴──────────┬──────────────┬──────────────┐
     ▼              ▼              ▼              ▼              ▼              ▼
1. CLI Shell   2. Sysfs Interface 3. Kernel Log  4. Procfs State 5. Thread Identity 6. Callstack
 (kpatch list) (/sys/kernel/...)  (dmesg -wT)    (/proc/PID/...) (QEMU vCPU TID) (/proc/TID/stack)
```

### 1.1. Lớp 1 – `kpatch` CLI Shell

```bash
# Xem danh sách các livepatch modules đang nạp trong kernel
kpatch list

# Xem thông tin metadata chi tiết của file module
kpatch info livepatch-kvm-mmu-fix.ko
```

### 1.2. Lớp 2 – Interface `sysfs` (/sys/kernel/livepatch)

```bash
# Xem thư mục các bản vá đang nạp
ls /sys/kernel/livepatch

# Xem trạng thái kích hoạt và chuyển đổi
cat /sys/kernel/livepatch/<patch_name>/enabled
cat /sys/kernel/livepatch/<patch_name>/transition
```

- **`enabled=1, transition=0`:** Bản vá đã ổn định hoàn toàn (**Stable Patched**).
- **`enabled=1, transition=1`:** Bản vá đang trong quá trình chuyển đổi (**Patching In Progress**).
- **`enabled=0, transition=1`:** Bản vá đang trong quá trình gỡ bỏ (**Unpatching In Progress**).
- Thư mục biến mất: Bản vá đã bị gỡ bỏ hoàn toàn khỏi Kernel.

### 1.3. Lớp 3 – Kernel Ring Buffer Log (`dmesg`)

```bash
# Theo dõi các thông điệp ghi nhận từ Livepatch core
sudo dmesg -T | grep -Ei 'livepatch|kpatch'
```

### 1.4. Lớp 4 – Procfs Per-Task State (`/proc/<PID>/patch_state`)

```bash
# Quét tìm các Task có patch_state chưa đạt target
for f in /proc/*/task/*/patch_state; do
  [ -r "$f" ] || continue
  echo "$f $(cat "$f")"
done
```

### 1.5. Lớp 5 – Thread Identity (Định danh Thread cụ thể)

```bash
# Định danh chính xác TID của các vCPU threads trong QEMU
for pid in $(pgrep -f '/usr/bin/qemu-system-x86_64'); do
  ps -T -p "$pid" -o pid,tid,comm
done
```

### 1.6. Lớp 6 – Callstack Trace (`/proc/<PID>/task/<TID>/stack`)

```bash
# Đọc vết hàm đang thực thi của Thread bị kẹt
sudo cat /proc/<PID>/task/<TID>/stack
```

---

## 2. Chẩn đoán stalled transition

### Dấu hiệu nhận biết Transition Stall:

- Trạng thái `sysfs: transition = 1` kéo dài bất thường (vượt quá ngưỡng cho phép của hệ thống).
- Xuất hiện một số ít Task có `patch_state` khác với `target_state`.
- Log `dmesg` xuất hiện thông điệp Kernel bắt đầu gửi tín hiệu giải cứu: `"livepatch: signaling remaining tasks..."`.

```text
               TRANSITION STALL DIAGNOSIS FLOW
                              │
                              ▼
                Kiểm tra sysfs: transition = 1?
                              │
                              ▼
            Xác định chiều Transition (Direction):
         - Patching (Target = 1): Tìm Task có state = 0
         - Unpatching (Target = 0): Tìm Task có state = 1
                              │
                              ▼
         Lấy PID / TID của các Task chưa chịu hội tụ
                              │
                              ▼
         Đọc Callstack: sudo cat /proc/PID/task/TID/stack
                              │
                              ▼
         Phân tích nguyên nhân kẹt:
         - Task kẹt ở Syscall I/O dài ngày?
         - vCPU Thread nằm trong vòng lặp KVM_RUN?
```

---

## 3. Recovery ladder và nguyên tắc không phản xạ kill workload

### Thang ứng phó sự cố (Recovery Ladder) 6 cấp độ

Khi xảy ra sự cố Livepatch Transition bị kẹt, hãy áp dụng các bước trong **Recovery Ladder** theo thứ tự từ nhẹ đến nặng:

```text
                         THANG ỨNG PHÓ SỰ CỐ (RECOVERY LADDER)
                                           │
  [ Level 1: WAIT ] ───────────────────────┼──> Chờ thêm 30-60 giây nếu Workload vẫn bình thường.
                                           │
  [ Level 2: QUIESCE WORKLOAD ] ───────────┼──> Tạm dừng Traffic / I/O giảm tải cho Guest VM.
                                           │
  [ Level 3: SIGNAL KICK ] ────────────────┼──> Gửi Fake Signal: `sudo kpatch signal`.
                                           │
  [ Level 4: REVERSE TRANSITION ] ─────────┼──> Hủy bỏ an toàn: `echo 0 > sysfs/enabled`.
                                           │
  [ Level 5: FORCE TRANSITION ] ───────────┼──> ⚠️ Cưỡng bức: `echo 1 > sysfs/force` (Cần Reboot!).
                                           │
  [ Level 6: OPERATIONAL FALLBACK ] ───────└──> Live Migrate VM sang Host khác -> Reboot Host.
```

### Nguyên tắc vàng: Không phản xạ `kill -9` Workload!

Việc dùng lệnh `kill -9` với Process QEMU/VM sẽ biến sự cố chuyển đổi Livepatch (vẫn giữ VM an toàn) thành một sự cố sụp đổ dịch vụ nghiêm trọng (**Downtime / Outage**).

---

## 4. Các failure mode ngoài stalled transition

### 4.1. Module Load Failure (Thất bại khi Nạp Module)

Nếu lệnh `kpatch load` bị từ chối:
1. Giữ nguyên output lỗi và đọc ngay thông điệp log `dmesg`.
2. Kiểm tra `vermagic` của file module với `uname -r`.
3. Kiểm tra tính hợp lệ của chữ ký số (Module Signing enforcement).

### 4.2. Post-Patch Service Anomaly (Bất thường dịch vụ sau khi nạp)

Ngay cả khi `sysfs: transition = 0` (hội tụ thành công), dịch vụ có thể gặp bất thường về mặt logic mã mới:
- Theo dõi các chỉ số: Packet loss, đọ trễ (latency spike), tụt giảm throughput, rò rỉ bộ nhớ (memory leak).
- Nếu phát hiện chỉ số bất thường tương quan với việc nạp patch -> Kích hoạt ngay kịch bản **Level 4: Reverse Transition (`kpatch unload`)**.

---

## 5. Evidence, case KVM, force checklist và post-incident

### 5.1. Mẫu nhật ký sự cố (Evidence Collection Template)

```text
=================== LIVEPATCH INCIDENT REPORT ===================
Thời điểm (Timestamp): 2026-08-26 04:11:00 UTC
Host / Kernel Release: compute-node-01 | 6.8.0-134-generic
Tên Patch Module: livepatch-kvm-mmu-fix.ko
Chiều Transition: Unpatching (Target = 0)
Trạng thái Sysfs: enabled = 1 | transition = 1 (Stalled)
TID bị kẹt (Blocking TID): TID 4321 (QEMU vCPU 0 Thread)
Callstack vết hàm: [<ffffffff81a01234>] kvm_arch_vcpu_ioctl_run+0x12/0x50
Nhật ký dmesg log: "livepatch: signaling remaining tasks..."
Hành động ứng phó (Recovery Action): Level 3 Signal Kick -> Level 4 Reverse Transition
Kết quả (Result): Unpatch hoàn tất thành công, VM giữ nguyên SLO Uptime.
================================================================
```

### 5.2. Force Transition Checklist (Điểm kiểm tra trước khi Force)

```text
[ ] Đã xác định rõ chiều Transition (Patching 0->1 hay Unpatching 1->0).
[ ] Đã xác định chính xác PID/TID và đọc Callstack của Task bị kẹt.
[ ] Đã thử giảm tải Workload (Quiesce) và gửi Signal Kick.
[ ] Phương án Reverse Transition (`enabled = 0`) không phù hợp hoặc thất bại.
[ ] Đã nhận được sự phê duyệt (Approval) của cấp có thẩm quyền.
[ ] Đã lên kế hoạch Live Migrate VMs và Reboot máy chủ ngay sau đó.
```

---

## 6. Tài liệu tham khảo

- [Linux Kernel Livepatch Architecture Documentation](https://docs.kernel.org/livepatch/livepatch.html)
- [kpatch Manual Page](https://github.com/dynup/kpatch/blob/master/man/kpatch.1)
- [Linux Kernel Bug Hunting & Debugging](https://docs.kernel.org/admin-guide/bug-hunting.html)
