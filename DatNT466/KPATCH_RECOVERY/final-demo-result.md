# Final demo result

## 1. Kết luận 

Đã chứng minh bằng raw evidence:

- đúng host, kernel và module mentor;
- giữ cùng KVM vCPU TID ở old state trên `direct_page_fault` qua mốc 10 giây;
- tự load, scan pending task, map `TID → QEMU PID → vm1`;
- tự `virsh suspend` rồi lập tức `virsh resume`: transition hoàn tất trong observation window `(0,0.501]s`, lặp lại 3/3;
- strategy `signal` bằng `SIGSTOP/SIGCONT` trên đúng pending TID: hoàn tất trong `0.251–0.501s`, lặp lại 3/3;
- cascade `signal → verify → suspend/resume`: hoàn tất trong `0.501–1.253s` (short-circuit trên signal), lặp lại 3/3;
- cascade fallback `throttle → suspend/resume`: tự động rollback quota khi throttle timeout 2s và fallback sang suspend/resume hoàn tất thành công;
- cả 9 completion được ghi khi injector 45s vẫn sống và còn ít nhất `31.864s`, loại trừ natural release;
- health sau cleanup synthetic blocker đạt 0% packet loss trên 10/10 run;
- whole-domain throttle áp dụng/rollback đúng nhưng không tạo early recovery (đã chứng minh qua trial standalone 4s exit 7).

Không tái hiện được `transition=1 >=75s`: no-action condition tự hoàn tất ở `17.22s` sau built-in KLP signaling (`#define SIGNALS_TIMEOUT 15` trong kernel). Vì vậy acceptance gốc 75 giây giữ nguyên đánh giá trung thực là `NOT REPRODUCED`. Bộ Scoped Recovery Study tại `T=10s` đạt toàn bộ các tiêu chí: `PASS`.

```text
CONTROLLED_PENDING_10S       = PASS
AUTO_LOAD_SCAN_GROUP         = PASS
SUSPEND_RESUME_3_RUNS        = PASS
THROTTLE_TREATMENT           = PASS
THROTTLE_EARLY_RECOVERY      = NOT OBSERVED
SIGNAL_HOST_RUN              = PASS (3/3)
CASCADE_HOST_RUN             = PASS (3/3 default + 1 fallback + 1 all)
CAUSAL_SEPARATION_45S        = PASS (9/9 recovery runs)
POST_CLEANUP_HEALTH          = PASS (10/10, 0% loss)
SCOPED_RECOVERY_10S          = PASS
LONG_STALL_75S               = NOT REPRODUCED
ORIGINAL_ACCEPTANCE_75S      = NOT MET IN FULL
```

## 2. Demo đã có evidence

### Bước 1 — Khóa môi trường

**Mục đích:** chứng minh không dùng fake patch hoặc sai kernel.

```bash
hostname
uname -r
sha256sum "$PATCH_MODULE"
```

**Output thực tế:**

```text
datnt466-kpatch
6.8.0-134-generic
582d5f874fedf92ca5977b66055fca2f83f17170ba0db37227ce204f0c60d011
```

**Gate:** `ARTIFACT_IDENTITY=PASS`.

### Bước 2 — Chứng minh pending condition

**Mục đích:** xác nhận đúng một vCPU task giữ old state trên affected function đến recovery trigger.

```bash
grep -E 'CHECKPOINT|TID:|patch_state:|transition:|direct_page_fault' \
  ../Docs/FINAL_EVIDENCE/same-tid/synchronized-blocker.log
```

**Output thực tế rút gọn:**

```text
TID: 2250370 (CPU 0/KVM)
QEMU PID: 2250361
domain: vm1
checkpoint 1/3/5/8/10s: patch_state=0, transition=1
stack: direct_page_fault
```

**Gate:** `CONTROLLED_PENDING_10S=PASS`.

### Bước 3 — Chạy automation suspend/resume

**Mục đích:** thực hiện đúng exercise chính mentor giao.

```bash
sudo python3 kpatch_recovery.py \
  --module "$PATCH_MODULE" \
  --expected-sha256 "$PATCH_SHA256" \
  --patch-name "$PATCH_NAME" \
  --deadline 10 \
  --strategy suspend-resume \
  --poll-interval 0.5 \
  --recovery-step-timeout 2 \
  --total-timeout 120 \
  --log automation-run.log \
  --output-format both
```

**Output thực tế đại diện:**

```text
stall_deadline_reached observed_seconds=10.246
pending_task tid=2250370 qemu_pid=2250361 domain="vm1"
selected_domain domain="vm1"
domain_suspend returncode=0 duration_seconds=0.042
domain_resume returncode=0 duration_seconds=0.032
transition 1 → 0 within (0,0.501]s
patch_verified transition=0 enabled=1
domain_state_after output="running"
final_result result="recovered" exit_code=0
```

**Gate:** `AUTO_SUSPEND_RESUME=PASS (3/3)`.

Lưu ý provenance: `automation-run.log` là run của phiên bản single-strategy trước khi bổ sung cascade. Logic load/scan/map/suspend/resume không bị thay đổi; muốn khóa hash source mới với log mới phải chạy lại Bước 3 trên host.

### Bước 4 — Kiểm tra whole-domain throttle

**Mục đích:** xác nhận treatment thật và kết quả recovery.

```bash
grep -E 'ACTION|cpu.max|nr_throttled|throttled_usec|TRANSITION_COMPLETE' \
  ../Docs/FINAL_EVIDENCE/throttle/throttle-run-03.log
```

**Output thực tế:**

```text
cpu.max = 1000 100000
nr_throttled delta = 65
throttled_usec delta = 5298456
transition complete = 16.54s
cleanup cpu.max = max 100000
```

**Gate:** treatment PASS; early recovery NOT OBSERVED.

## 3. Demo cascade và signal đã thực nghiệm trên host 

Đây là các luồng can thiệp tự động đã được kiểm chứng bằng 10 lượt chạy với UFFD hold 45 giây. Runner chụp trạng thái transition trước khi cleanup injector; vì vậy natural release không thể tạo PASS giả.

### Bước 1 — Kiểm tra source và module trên host

**Mục đích:** khóa toàn vẹn mã nguồn và artifact trước khi chạy ma trận.

```bash
python3 -m py_compile kpatch_recovery.py
sha256sum kpatch_recovery.py
sha256sum run_recovery_matrix.py
sha256sum "$PATCH_MODULE"
```

**Output thực tế (từ `matrix-metadata.json`):**

```text
kpatch_recovery.py SHA256: 23b58272d3d77f49d48669050989abf607f73778e831e8b035baf9cd409f3cd4
run_recovery_matrix.py SHA256: 521c4eafe20c47568e001198e7d1db16b8498e8323a946c2363ec67e32e09444
trilogy-cve-2026-64561.ko: 582d5f874fedf92ca5977b66055fca2f83f17170ba0db37227ce204f0c60d011
Kernel: 6.8.0-134-generic
```

### Bước 2 — Chạy signal độc lập (3/3 runs PASS)

**Mục đích:** tạo run can thiệp chủ động ở `T=10s` nhắm vào đúng pending TID mà không cần tạm dừng toàn bộ VM.

```bash
sudo python3 -u /home/ubuntu/run_recovery_matrix.py \
  --case signal-01 \
  --output-dir /home/ubuntu/FINAL_EVIDENCE/recovery-v4
```

**Output thực tế đại diện (`signal-01.log`):**

```text
# [2026-09-04T08:40:03.360+00:00] INFO stall_deadline_reached observed_seconds=10.109 pending_task_count=1 blocker_domains=["vm1"]
# [2026-09-04T08:40:03.360+00:00] INFO pending_task pid=2250361 tid=2250371 patch_state=0 comm="CPU 1/KVM" domain="vm1"
# [2026-09-04T08:40:03.368+00:00] INFO task_signal tid=2250371 signal="SIGSTOP" delivered=true
# [2026-09-04T08:40:03.418+00:00] INFO task_signal tid=2250371 signal="SIGCONT" delivered=true
# [2026-09-04T08:40:03.669+00:00] INFO recovery_step_completed method="signal" completion_observed_seconds=0.251
# [2026-09-04T08:40:03.681+00:00] INFO final_result result="recovered" exit_code=0
active-postcheck: injector_alive=true, fault_hold_remaining=33.875s,
completion_before_fault_release=true
post-cleanup: vm1=running, cpu.max="max 100000", ping=0% loss
```

**Gate:** `SIGNAL_HOST_RUN = PASS (3/3)`.

### Bước 3 — Chạy cascade mặc định (`signal,suspend-resume`)

**Mục đích:** chứng minh chương trình tự thử giải pháp nhẹ trước và dừng ngay khi transition hoàn tất.

```bash
sudo python3 -u /home/ubuntu/run_recovery_matrix.py \
  --case cascade-01 \
  --output-dir /home/ubuntu/FINAL_EVIDENCE/recovery-v4
```

**Output thực tế đại diện (`cascade-01.log`):**

```text
# [2026-09-04T08:40:54.673+00:00] INFO recovery_plan_started strategy="cascade" methods=["signal","suspend-resume"]
# [2026-09-04T08:40:54.680+00:00] INFO task_signal tid=2250371 signal="SIGSTOP" delivered=true
# [2026-09-04T08:40:54.730+00:00] INFO task_signal tid=2250371 signal="SIGCONT" delivered=true
# [2026-09-04T08:40:55.733+00:00] INFO recovery_step_completed method="signal" completion_observed_seconds=1.002
# [2026-09-04T08:40:55.745+00:00] INFO final_result result="recovered" exit_code=0
active-postcheck: injector_alive=true, fault_hold_remaining=33.122s,
completion_before_fault_release=true
```

**Gate:** `CASCADE_HOST_RUN = PASS (3/3)`.

### Bước 4 — Cascade fallback có kiểm chứng (`cascade-fallback-01`)

**Mục đích:** kiểm tra cơ chế chuyển bước khi một method bị timeout. Chuỗi thử nghiệm: `throttle → suspend-resume`.

```bash
sudo python3 -u /home/ubuntu/run_recovery_matrix.py \
  --case cascade-fallback-01 \
  --output-dir /home/ubuntu/FINAL_EVIDENCE/recovery-v4
```

**Output thực tế (`cascade-fallback-01.log`):**

```text
# [2026-09-04T08:41:47.309+00:00] INFO throttle_applied requested_cpu_max="1000 100000" readback="1000 100000"
# [2026-09-04T08:41:49.310+00:00] WARNING recovery_step_timeout method="throttle" timeout_seconds=2.0 transition=1 enabled=1
# [2026-09-04T08:41:49.310+00:00] INFO throttle_restored restored_cpu_max="max 100000" readback="max 100000"
# [2026-09-04T08:41:49.318+00:00] INFO recovery_step_started method="suspend-resume" pending_task_count=1 blocker_domains=["vm1"]
# [2026-09-04T08:41:49.353+00:00] INFO domain_suspend returncode=0 duration_seconds=0.023
# [2026-09-04T08:41:49.369+00:00] INFO domain_resume returncode=0 duration_seconds=0.016
# [2026-09-04T08:41:49.621+00:00] INFO recovery_step_completed method="suspend-resume" completion_observed_seconds=0.251
# [2026-09-04T08:41:49.634+00:00] INFO final_result result="recovered" exit_code=0
active-postcheck: injector_alive=true, fault_hold_remaining=31.864s,
completion_before_fault_release=true
```

**Nhận xét:** Khi throttle timeout sau 2.0s, automation hoàn trả `cpu.max`, chuyển sang `suspend-resume` và hoàn tất trong `0.251s`, hơn 31 giây trước natural release.

### Bước 5 — Cleanup và health sau chuỗi kiểm thử

**Mục đích:** xác nhận host hoàn toàn sạch sẽ sau tất cả các run.

```bash
virsh domstate vm1
ping -c 3 -W 2 192.168.122.204
cat /sys/fs/cgroup/machine.slice/machine-qemu\x2d6\x2dvm1.scope/cpu.max
ls /sys/kernel/livepatch
```

**Output thực tế:**

```text
running
3 packets transmitted, 3 received, 0% packet loss
max 100000
(thư mục rỗng - module đã gỡ an toàn)
```

## 4. Vì sao 75s chưa đạt

### Lệnh validation đã chạy

```bash
grep -E 'ELAPSED|PATCH_STATE|TRANSITION|signaling remaining tasks|FINAL' \
  ../Docs/FINAL_EVIDENCE/long-stall/75s-validation.log
```

### Output thực tế

```text
15.20s: patch_state=0, transition=1
16.21s: patch_state=1
17.22s: transition=0, patch_state=-1
dmesg: livepatch: signaling remaining tasks
```

Controlled UFFD wait là interruptible; fake signal tự động của KLP ở khoảng 15 giây tạo cơ hội rời affected stack và transition hoàn tất. Vì condition kết thúc ở 17.22 giây, không thể dùng nó để claim `>=75s`.

Điều này không chứng minh mọi KVM blocker đều không thể vượt 75 giây. Nó chỉ kết luận condition đã chạy không đạt gate. Không sửa mentor patch, không sửa `patch_state` thủ công và không đổi nhãn 10s thành 75s.

## 5. Gate nghiệm thu

| Gate | Trạng thái |
|---|---|
| Exact artifact | **PASS** |
| Same-TID affected stack đến 10s | **PASS** |
| Auto load/scan/group | **PASS** |
| Suspend/resume 3/3 | **PASS** |
| Whole-domain throttle treatment | **PASS** |
| Throttle early recovery | **NOT OBSERVED** |
| Signal independent run | **PASS (3/3)** |
| Automatic cascade run | **PASS (3/3 default + 1 fallback + 1 all)** |
| Causal separation: completion trước UFFD release | **PASS (9/9 recovery runs)** |
| Health sau cleanup synthetic blocker | **PASS (10/10, 0% packet loss)** |
| Scoped recovery study (`T=10s`) | **PASS** |
| Long stall `>=75s` | **NOT REPRODUCED** |
| Original acceptance 75s | **NOT MET IN FULL** |

