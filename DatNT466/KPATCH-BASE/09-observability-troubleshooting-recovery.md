# 09 – Observability, troubleshooting và recovery

## Mục lục

1. [1. Các lớp observability: CLI, sysfs, log, task, thread và stack](#1-các-lớp-observability-cli-sysfs-log-task-thread-và-stack)
2. [2. Chẩn đoán stalled transition](#2-chẩn-đoán-stalled-transition)
3. [3. Recovery ladder và nguyên tắc không phản xạ kill workload](#3-recovery-ladder-và-nguyên-tắc-không-phản-xạ-kill-workload)
4. [4. Các failure mode ngoài stalled transition](#4-các-failure-mode-ngoài-stalled-transition)
5. [5. Evidence, case KVM, force checklist và post-incident](#5-evidence-case-kvm-force-checklist-và-post-incident)
6. [6. Tài liệu tham khảo](#6-tài-liệu-tham-khảo)

## Chuỗi chẩn đoán và recovery

```text
LIVEPATCH OPERATION
       |
       v
 transition kéo dài?
    /       \
  Không      Có
   |          |
   v          v
 DONE   Collect evidence
             |
             v
        identify blocker
             |
             v
        inspect stack
             |
             v
      recovery ladder
             |
   +---------+----------+-----------+
   |         |          |           |
  wait     quiesce    signal     reverse
                                      |
                                      v
                              force (last resort)
                                      |
                                      v
                             migrate / reboot
```

## 1. Các lớp observability: CLI, sysfs, log, task, thread và stack

**Nguyên tắc**

Khi livepatch có vấn đề, đừng sửa trước khi biết hệ thống đang ở state nào.

```text
Observe → Identify → Explain → Mitigate → Reverse/Force/Fallback
```

---

**Lớp observability 1 – kpatch CLI**

```bash
kpatch list
kpatch info patch.ko
```

`kpatch list` trả lời patch nào đang loaded/enabled.

---

**Lớp 2 – sysfs**

```bash
ls /sys/kernel/livepatch
cat /sys/kernel/livepatch/<patch>/enabled
cat /sys/kernel/livepatch/<patch>/transition
```

Mental model:

```text
enabled=1, transition=0 → stable patched
enabled=1, transition=1 → patching in progress
enabled=0, transition=1 → unpatching in progress
directory absent          → patch không registered/đã removed
```

---

**Lớp 3 – kernel log**

```bash
sudo dmesg -T | grep -Ei 'livepatch|kpatch'
```

Tìm:

```text
starting patching transition
signaling remaining tasks
patching complete
starting unpatching transition
unpatching complete
module verification failed
Oops / BUG / panic
```

---

**Lớp 4 – per-task state**

```bash
for f in /proc/*/task/*/patch_state; do
  [ -r "$f" ] || continue
  echo "$f $(cat "$f")"
done
```

Biết chiều transition để xác định blocker:

```text
patching target=1   → state=0 đáng chú ý
unpatching target=0 → state=1 đáng chú ý
```

---

**Lớp 5 – thread identity**

QEMU:

```bash
for pid in $(pgrep -f '/usr/bin/qemu-system-x86_64'); do
  ps -T -p "$pid" -o pid,tid,comm
done
```

Map `CPU 0/KVM`, `CPU 1/KVM` với TID cụ thể.

---

**Lớp 6 – stack**

```bash
sudo cat /proc/<PID>/task/<TID>/stack
```

Stack trả lời “task đang ở đâu”, nhưng sampling chỉ là snapshot và unwinding có giới hạn.

---

## 2. Chẩn đoán stalled transition

**Stalled transition diagnosis**

Dấu hiệu:

```text
transition=1 kéo dài
+ một số task chưa target
+ kpatch/kernel bắt đầu signal remaining tasks
```

Không nên gọi mọi transition >1 giây là stall.

---

## 3. Recovery ladder và nguyên tắc không phản xạ kill workload

**Recovery ladder**

**Level 1 – Wait**

Nếu workload healthy và transition mới bắt đầu.

**Level 2 – Quiesce workload**

Giảm stress/traffic/batch để blocking task rời affected path.

**Level 3 – Signal/poke**

`kpatch signal` nếu platform cần manual signaling; kernel mới có thể tự động signal.

**Level 4 – Reverse/cancel**

Đảo `enabled` về initial state nếu patch không cần tiếp tục.

**Level 5 – Force**

Last resort, rủi ro cao, plan reboot.

**Level 6 – Operational fallback**

Migrate workload/evacuate → reboot host.

---

**Không kill QEMU theo phản xạ**

`kill -9 qemu` có thể biến transition problem thành VM outage tức thì.

Nếu blocker là QEMU/vCPU, ưu tiên:

- quiesce guest workload;
- signal theo livepatch mechanism;
- reverse patch;
- controlled migration/restart theo policy.

---

## 4. Các failure mode ngoài stalled transition

**Module load failure**

Nếu `kpatch load` fail:

```text
1. giữ nguyên output
2. xem dmesg
3. kiểm tra vermagic
4. symbol/version error?
5. signing enforcement?
6. patch object/module target tồn tại?
```

Không retry mù nhiều lần.

---

**Transition complete nhưng service anomaly**

Patch có thể `transition=0` nhưng semantic bug vẫn tồn tại.

Theo dõi:

- packet loss;
- latency;
- throughput;
- VM pause/reset/crash;
- CPU/run queue;
- storage latency;
- kernel errors.

Nếu anomaly correlate với patch → reverse/unload theo runbook.

---

## 5. Evidence, case KVM, force checklist và post-incident

**Evidence collection template**

```text
Timestamp:
Host/kernel:
Patch name/hash:
Direction: patching/unpatching
kpatch list:
enabled:
transition:
Blocking PID/TID:
patch_state:
stack:
dmesg excerpt:
VM state:
SLO metrics:
Recovery action:
Result:
```

---

**Case KVM stalled transition**

Observed pattern:

```text
unpatching target = 0
CPU 0/KVM state=1
CPU 1/KVM state=1
transition=1
```

Sau signaling/scheduling opportunity:

```text
1 → 0
```

rồi unpatch complete.

---

**Force checklist**

```text
[ ] biết patching hay unpatching
[ ] biết target state
[ ] biết blocker
[ ] đã xem stack
[ ] đã quiesce thử
[ ] signaling đã diễn ra
[ ] reverse không phù hợp/không thành công
[ ] có approval
[ ] có reboot/migration plan
```

---

**Post-incident**

Sau stall/error phải lưu:

- patch source;
- build log;
- changed functions;
- host kernel identity;
- dmesg;
- task states;
- workload metrics;
- recovery action;
- root cause;
- lesson cho patchability gate.

---

## 6. Tài liệu tham khảo

- https://docs.kernel.org/livepatch/livepatch.html
- https://github.com/dynup/kpatch/blob/master/man/kpatch.1
