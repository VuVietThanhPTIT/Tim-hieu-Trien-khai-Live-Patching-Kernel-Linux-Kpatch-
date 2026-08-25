# LAB 5 – PHƯƠNG ÁN XỬ LÝ KHI LIVEPATCH TRANSITION BỊ STALL

## 1. Mục tiêu

Lab 5 tập trung vào **phương án vận hành và recovery** khi Linux livepatch/kpatch không thể hoàn tất transition trong thời gian mong đợi.

Đây là phần hướng dẫn tổng quát theo hướng audit/operation, không phụ thuộc riêng vào một patch cụ thể.

Mục tiêu cần trả lời:

- Khi nào được coi là transition đang bị stall?
- Làm thế nào xác định task đang giữ transition?
- Thứ tự xử lý nào nên ưu tiên?
- Khi nào nên quiesce workload?
- Khi nào nên signal/poke task?
- Khi nào nên reverse/cancel transition?
- `force` dùng khi nào và rủi ro ra sao?
- Khi livepatch không còn phù hợp, khi nào phải quay về live migration / reboot?

---

# 2. Bối cảnh từ các lab trước

Trong Lab 4 đã quan sát được:

```text
transition=1
```

kéo dài, đồng thời:

```text
patch transition has stalled!
```

và kernel phải:

```text
signaling remaining tasks
```

Các QEMU vCPU thread:

```text
CPU 0/KVM
CPU 1/KVM
```

có thời điểm vẫn giữ `patch_state` khác target state.

Điều này cho thấy livepatch không ép tất cả task đổi implementation ngay lập tức.

Thay vào đó kernel duy trì:

```text
per-task consistency
```

và chờ từng task đạt trạng thái phù hợp để chuyển.

---

# 3. Các khái niệm nền tảng cần nhớ

## 3.1. Transition state

Khi enable một patch:

```text
unpatched
    ↓
transition
    ↓
patched
```

Khi disable patch:

```text
patched
    ↓
transition
    ↓
unpatched
```

Trong sysfs:

```text
/sys/kernel/livepatch/<patch>/transition
```

Giá trị:

```text
1 = transition đang diễn ra
0 = transition đã hoàn tất
```

Một patch có thể ở `transition=1` trong thời gian dài nếu một hoặc nhiều task chưa chuyển được khỏi initial patch state.

---

## 3.2. `patch_state` theo task

Trong lúc transition:

```text
/proc/<pid>/patch_state
```

hoặc theo từng thread:

```text
/proc/<pid>/task/<tid>/patch_state
```

Ý nghĩa:

```text
0 = task đang ở unpatched state
1 = task đang ở patched state
```

Ngoài transition, giá trị thường là:

```text
-1
```

### Khi patching

Target:

```text
1
```

Task còn:

```text
0
```

là task chưa chuyển sang patched state.

### Khi unpatching

Target:

```text
0
```

Task còn:

```text
1
```

là task chưa quay về unpatched state.

---

# 4. Khi nào gọi là stalled transition?

Không nên chỉ nhìn vào việc transition mất vài giây.

Một transition được coi là đáng nghi khi:

- `transition=1` kéo dài bất thường.
- Kpatch báo:
  ```text
  patch transition has stalled!
  ```
- Kernel log có:
  ```text
  signaling remaining tasks
  ```
- Một số task vẫn giữ `patch_state` khác target state.
- Patch không thể enable/disable hoàn toàn trong thời gian operation dự kiến.

Ví dụ:

```text
Patching:
target = 1

Task A = 1
Task B = 1
Task C = 0  ← blocker candidate
```

Hoặc reverse transition:

```text
Unpatching:
target = 0

Task A = 0
Task B = 0
Task C = 1  ← blocker candidate
```

---

# 5. Nguyên tắc recovery tổng quát

Thứ tự xử lý nên đi từ **ít xâm lấn nhất → xâm lấn hơn**:

```text
1. Observe / Wait
        ↓
2. Identify blocking task
        ↓
3. Reduce / Quiesce workload
        ↓
4. Signal / Poke remaining task
        ↓
5. Reverse / Cancel transition
        ↓
6. Force transition
        ↓
7. Operational fallback:
   migrate workload / reboot host
```

Không nên nhảy thẳng đến `force`.

---

# 6. Bước 1 – Quan sát trạng thái hiện tại

Đầu tiên xác định patch nào đang active:

```bash
kpatch list
```

Kiểm tra sysfs:

```bash
ls -l /sys/kernel/livepatch/
```

Giả sử patch:

```bash
PATCH=<patch_name>
```

Kiểm tra:

```bash
cat /sys/kernel/livepatch/$PATCH/enabled
cat /sys/kernel/livepatch/$PATCH/transition
```

Ví dụ:

```text
enabled=1
transition=1
```

có nghĩa patch đã được yêu cầu enable nhưng transition chưa hoàn tất.

---

# 7. Bước 2 – Kiểm tra kernel log

```bash
sudo dmesg -T | grep -Ei 'livepatch|kpatch' | tail -n 100
```

Tìm các dòng:

```text
starting patching transition
starting unpatching transition
signaling remaining tasks
patching complete
unpatching complete
```

Nếu chỉ có:

```text
starting ... transition
```

nhưng chưa có:

```text
... complete
```

thì transition vẫn đang pending.

---

# 8. Bước 3 – Xác định task đang block

Dùng:

```bash
for f in /proc/*/task/*/patch_state; do
    [ -r "$f" ] || continue

    state=$(cat "$f")
    tid=$(echo "$f" | awk -F/ '{print $5}')
    pid=$(echo "$f" | awk -F/ '{print $3}')
    comm=$(cat /proc/$pid/task/$tid/comm 2>/dev/null)

    printf "PID=%s TID=%s state=%s comm=%s\n" \
        "$pid" "$tid" "$state" "$comm"
done
```

Sau đó xác định target state.

### Nếu đang patching:

```text
target = 1
```

Tập trung task:

```text
state=0
```

### Nếu đang unpatching:

```text
target = 0
```

Tập trung task:

```text
state=1
```

---

# 9. Bước 4 – Xem stack của blocking task

Nếu xác định được TID nghi ngờ:

```bash
sudo cat /proc/<TID>/stack
```

Hoặc:

```bash
sudo cat /proc/<PID>/task/<TID>/stack
```

Mục tiêu:

- Task đang ngủ ở đâu?
- Có nằm trong function được patch hoặc call chain liên quan không?
- Có phải QEMU vCPU thread?
- Có phải kernel thread?
- Có đang block trên lock / wait / I/O không?

Ví dụ KVM:

```text
kvm_vcpu_ioctl
    ↓
kvm_arch_vcpu_ioctl_run
    ↓
vcpu_run
```

Nếu patched function vẫn liên quan đến execution context của task, livepatch có thể phải chờ task đạt safe state.

---

# 10. Bước 5 – Wait / Observe

Đây là phương án đầu tiên nếu:

- transition mới bắt đầu,
- workload vẫn healthy,
- không có kernel error,
- không có SLA breach.

Có thể monitor:

```bash
watch -n 0.5 \
'cat /sys/kernel/livepatch/<patch>/transition 2>/dev/null'
```

Nếu:

```text
1 → 0
```

thì không cần hành động thêm.

### Khi nào nên chờ?

- Task có khả năng tự rời critical path.
- Workload bình thường.
- Không có deadlock.
- Không có timeout nghiêm trọng.
- Transition mới diễn ra vài giây.

---

# 11. Bước 6 – Reduce / Quiesce workload

Nếu blocker là workload có thể kiểm soát, đây thường là phương án recovery thực tế tốt nhất.

Ví dụ KVM/QEMU:

```text
Guest đang CPU-bound
    ↓
QEMU vCPU thread liên tục KVM_RUN
    ↓
safe-state opportunity giảm
```

Có thể:

- giảm CPU workload,
- dừng stress test,
- tạm ngừng batch job,
- giảm traffic,
- tạm pause một workload không critical,
- đưa application về trạng thái quiescent.

Trong lab:

```bash
Ctrl+C
```

để dừng `stress-ng`.

Sau đó monitor:

```bash
watch -n 0.5 \
'cat /sys/kernel/livepatch/<patch>/transition 2>/dev/null || echo complete'
```

Kỳ vọng:

```text
transition=1
    ↓
quiesce workload
    ↓
blocking task đạt safe state
    ↓
patch_state đổi về target
    ↓
transition=0
```

---

# 12. Tại sao quiesce workload có tác dụng?

Livepatch không cần toàn bộ hệ thống dừng.

Nó cần từng task đạt điểm mà việc đổi implementation là an toàn.

Nếu một task liên tục chạy trong affected execution path:

```text
patched function
    ↓
nested calls
    ↓
busy workload
```

thì task có thể mất nhiều thời gian hơn để đạt điểm chuyển.

Giảm workload tạo thêm cơ hội cho task:

- return khỏi affected stack,
- schedule,
- interrupt,
- sleep/wakeup,
- đi qua livepatch safe switching point.

---

# 13. Bước 7 – Signal / Poke blocking task

Linux livepatch có cơ chế signal remaining tasks.

Trong Lab 4 đã thấy:

```text
livepatch: signaling remaining tasks
```

Mục tiêu không phải kill process.

Mục tiêu là làm task được interrupt/wakeup để có cơ hội update patch state.

Với kpatch:

```bash
sudo kpatch signal
```

Tuy nhiên trên một số kernel, signaling được kernel tự động thực hiện.

Kpatch có thể báo:

```text
Livepatch process signaling is performed automatically on your system.
Skipping manual process signaling.
```

Trong trường hợp đó không cần lặp manual signal.

---

# 14. Không nên dùng SIGKILL như recovery mặc định

Không nên suy luận:

```text
task block transition
→ kill -9 task
```

Đặc biệt với:

- QEMU,
- storage process,
- network service,
- critical kernel-related userspace,
- database.

`SIGKILL` có thể gây service outage lớn hơn vấn đề livepatch.

Chỉ xử lý process theo lifecycle và operational policy của workload.

---

# 15. Bước 8 – Reverse / Cancel transition

Nếu transition không thể hoàn tất và operator muốn quay về trạng thái ban đầu, Linux livepatch cho phép reverse transition bằng cách ghi **giá trị ngược lại** vào:

```text
/sys/kernel/livepatch/<patch>/enabled
```

## Nếu đang patching nhưng muốn cancel

Patching đang hội tụ:

```text
0 → 1
```

Có thể yêu cầu quay lại unpatched:

```bash
echo 0 | sudo tee \
/sys/kernel/livepatch/<patch>/enabled
```

Kernel sẽ cố đưa task quay về:

```text
state=0
```

## Nếu đang unpatching nhưng muốn quay lại patched state

Unpatch đang hội tụ:

```text
1 → 0
```

Có thể reverse lại:

```bash
echo 1 | sudo tee \
/sys/kernel/livepatch/<patch>/enabled
```

Kernel sẽ cố hội tụ task về:

```text
state=1
```

---

# 16. Reverse transition không phải "instant rollback"

Một hiểu nhầm cần tránh:

```text
echo 0 > enabled
```

không có nghĩa toàn bộ task ngay lập tức quay về code cũ.

Reverse cũng là một transition.

Ví dụ:

```text
patching stalled
    ↓
operator cancel
    ↓
reverse transition
    ↓
tasks hội tụ về original state
    ↓
transition=0
```

Vì vậy reverse/cancel cũng phải được monitor.

---

# 17. Khi nào nên cancel/reverse?

Nên cân nhắc khi:

- patch transition kéo dài không chấp nhận được,
- blocker không thể quiesce,
- workload production nhạy cảm,
- patch chưa critical đến mức phải force,
- có dấu hiệu patch gây bất ổn,
- operator muốn quay về known-good state.

---

# 18. Bước 9 – Force transition

Sysfs:

```text
/sys/kernel/livepatch/<patch>/force
```

Có thể:

```bash
echo 1 | sudo tee \
/sys/kernel/livepatch/<patch>/force
```

**Đây là phương án rủi ro cao.**

Force bỏ qua cơ chế chờ task đạt trạng thái chuyển an toàn theo consistency model.

---

# 19. Rủi ro của `force`

Force chỉ nên dùng khi:

- transition bị stuck lâu,
- đã thu đủ stack trace,
- đã xác định blocker,
- đã hiểu affected function,
- đã đánh giá rủi ro,
- có approval/vendor clearance phù hợp.

Rủi ro:

```text
task vẫn có thể đang ngủ/chạy trong old code
```

nhưng kernel bị ép coi transition đã hoàn tất.

Điều này có thể gây:

- inconsistent execution,
- crash,
- data corruption tùy patch,
- undefined behavior.

---

# 20. Hệ quả vận hành quan trọng của force

Sau khi force transition, việc remove patch module không còn được đảm bảo an toàn.

Linux livepatch documentation cảnh báo module removal bị vô hiệu hóa sau force vì không thể đảm bảo không còn task tham chiếu code trong module.

Do đó sau force:

```text
plan reboot
```

nên được coi là phương án vận hành cần chuẩn bị.

---

# 21. Bước 10 – Operational fallback

Nếu livepatch không thể hoàn tất an toàn, ưu tiên cuối cùng là quay về maintenance workflow truyền thống.

Ví dụ KVM compute host:

```text
1. Live migrate VM khỏi compute
2. Xác nhận host không còn workload critical
3. Apply normal kernel package
4. Reboot host
5. Verify kernel
6. Return host to service
```

Đây là fallback an toàn hơn việc force livepatch một cách mù quáng.

---

# 22. Decision tree tổng quát

```text
                 Livepatch transition
                         |
                         v
                 transition = 1
                         |
                         v
                Có tự complete?
                  /           \
                Có             Không
                |                |
                v                v
             DONE        Identify blocker
                                 |
                                 v
                      workload có quiesce được?
                         /              \
                       Có                Không
                       |                  |
                       v                  v
                Quiesce workload     Signal / poke
                       |                  |
                       v                  v
                transition=0?        transition=0?
                    /   \               /   \
                  Có    Không          Có    Không
                  |       |             |       |
                  v       v             v       v
                DONE   Reverse       DONE    Reverse
                        /cancel               /cancel
                           |
                           v
                    vẫn không giải quyết?
                           |
                           v
                    đánh giá FORCE
                           |
                     approval + risk
                           |
                           v
                         Force
                           |
                           v
                       Plan reboot
```

---

# 23. Runbook step-by-step đề xuất

## Step 1 – Confirm transition

```bash
PATCH=<patch_name>

cat /sys/kernel/livepatch/$PATCH/enabled
cat /sys/kernel/livepatch/$PATCH/transition
```

---

## Step 2 – Save evidence

```bash
date

sudo dmesg -T | grep -Ei 'livepatch|kpatch' | tail -n 100
```

---

## Step 3 – Identify blocker

```bash
for f in /proc/*/task/*/patch_state; do
    [ -r "$f" ] || continue
    state=$(cat "$f")
    echo "$f state=$state"
done
```

---

## Step 4 – Inspect blocker

```bash
ps -T -p <PID>
sudo cat /proc/<PID>/task/<TID>/stack
```

---

## Step 5 – Wait briefly

```bash
watch -n 0.5 \
"cat /sys/kernel/livepatch/$PATCH/transition"
```

---

## Step 6 – Quiesce workload

Ví dụ:

```text
stop stress-ng
reduce traffic
pause non-critical batch
```

Monitor lại transition.

---

## Step 7 – Signal if needed

```bash
sudo kpatch signal
```

Nếu kernel tự động signal thì chỉ monitor.

---

## Step 8 – Cancel/reverse if necessary

Nếu patching:

```bash
echo 0 | sudo tee \
/sys/kernel/livepatch/$PATCH/enabled
```

Nếu unpatching:

```bash
echo 1 | sudo tee \
/sys/kernel/livepatch/$PATCH/enabled
```

---

## Step 9 – Force only with approval

```bash
echo 1 | sudo tee \
/sys/kernel/livepatch/$PATCH/force
```

Chỉ dùng khi đã hiểu đầy đủ rủi ro.

---

## Step 10 – Fallback

Nếu livepatch không còn phù hợp:

```text
migrate workload
→ reboot host
→ verify
→ restore service
```

---

# 24. Ma trận lựa chọn recovery

| Tình trạng | Hành động ưu tiên |
|---|---|
| Transition mới bắt đầu | Wait |
| Task sắp tự rời critical path | Wait |
| QEMU/vCPU workload quá nóng | Quiesce workload |
| Task sleeping / cần wakeup | Signal / poke |
| Patch không cần áp ngay | Cancel / reverse |
| Patch critical, blocker rõ, đã approval | Force cân nhắc |
| Không thể bảo đảm consistency | Migrate + reboot |
| Force đã được sử dụng | Chuẩn bị reboot |

---

# 25. Recovery strategy cho KVM compute node

Trong môi trường compute host có nhiều VM, thứ tự thực tế nên là:

```text
A. Không làm gián đoạn VM nếu chưa cần thiết
        ↓
B. Xác định vCPU/task blocker
        ↓
C. Quiesce workload nhẹ nhất có thể
        ↓
D. Chờ / signal
        ↓
E. Nếu patch không hoàn tất → cancel
        ↓
F. Nếu CVE cực kỳ critical:
      đánh giá force rất thận trọng
        ↓
G. Nếu consistency không bảo đảm:
      live migrate VM
      reboot compute
```

Mục tiêu không phải "bằng mọi giá livepatch".

Mục tiêu là:

```text
security fix
+
system consistency
+
service availability
```

---

# 26. Các lỗi vận hành cần tránh

## 26.1. Force ngay khi thấy transition=1

Sai vì transition bình thường cũng cần thời gian.

## 26.2. Kill QEMU để giải phóng blocker

Có thể biến vấn đề livepatch thành VM outage.

## 26.3. Rmmod module trong khi transition chưa complete

Không bảo đảm an toàn.

## 26.4. Chỉ nhìn `enabled=1`

`enabled=1` không luôn có nghĩa operation đã hoàn tất.

Phải kiểm tra:

```text
transition=0
```

## 26.5. Bỏ qua per-task patch_state

Nếu cần debug stall, đây là dữ liệu quan trọng để biết task nào chưa hội tụ.

---

# 27. Checklist trước khi quyết định force

Trước `force`, phải trả lời được:

```text
[ ] Patch nào đang transition?
[ ] Patching hay unpatching?
[ ] Target patch_state là 0 hay 1?
[ ] PID/TID blocker là task nào?
[ ] /proc/<tid>/stack cho thấy task nằm ở đâu?
[ ] Function nào được patch?
[ ] Workload đã được quiesce chưa?
[ ] Signal đã được thử chưa?
[ ] Reverse/cancel có khả thi không?
[ ] Có backup/failover/migration plan không?
[ ] Có maintenance/reboot plan không?
[ ] Có approval phù hợp không?
```

Nếu chưa trả lời được các mục trên:

```text
không nên force.
```

---

# 28. Kết luận Lab 5

Khi livepatch transition bị stalled, phương án xử lý phù hợp không phải là ép transition ngay lập tức.

Runbook ưu tiên:

```text
Observe
→ Identify blocker
→ Inspect stack
→ Quiesce workload
→ Signal / wake task
→ Reverse / cancel
→ Force only as last resort
→ Migrate / reboot fallback
```

Điểm cốt lõi:

```text
transition=1
```

không phải lỗi tự thân.

Nó cho biết livepatch consistency model vẫn đang chờ các task hội tụ về cùng target patch state.

Operator phải bảo vệ ba mục tiêu:

```text
1. Consistency
2. Availability
3. Security
```

Nếu livepatch không thể đáp ứng cả ba mục tiêu một cách an toàn, fallback về:

```text
live migration + reboot
```

là phương án đúng hơn việc force một transition mà chưa hiểu blocker.

---

# 29. Tóm tắt ngắn để audit

```text
Stalled transition
        ↓
Kiểm tra transition/enabled
        ↓
Xác định task qua patch_state
        ↓
Xem stack
        ↓
Wait nếu có thể
        ↓
Quiesce workload
        ↓
Signal / poke
        ↓
Nếu vẫn stuck → reverse/cancel
        ↓
Force chỉ khi có đánh giá + approval
        ↓
Nếu không bảo đảm an toàn → migrate VM + reboot host
```

Đây là phương án recovery tổng quát nên áp dụng cho livepatch trên KVM compute node.
