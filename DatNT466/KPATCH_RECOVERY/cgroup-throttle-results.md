# Kết quả thực nghiệm whole-domain CPU throttle

## 1. Kết luận

Ba quota đã được áp tại parent cgroup của `vm1` ở recovery trigger `T=10s`. Read-back và `cpu.stat` xác nhận treatment hợp lệ; run cực đoan thực sự bị throttle mạnh. Tuy nhiên không run nào tạo early recovery trước cửa sổ KLP signaling.

```text
WHOLE_DOMAIN_THROTTLE_TREATMENT = PASS
THROTTLE_EARLY_RECOVERY         = NOT OBSERVED
THROTTLE_PERFORMANCE_IMPACT     = PARTIAL (cpu.stat only)
```

Kết luận này chỉ áp dụng cho controlled UFFD condition và ba run hiện có; không phải tuyên bố throttle luôn vô ích với mọi blocker.

## 2. Environment và điều kiện cố định

| Thành phần | Giá trị |
|---|---|
| Host / kernel | `datnt466-kpatch` / `6.8.0-134-generic` |
| Domain | `vm1`, 2 vCPU |
| Source patch SHA256 | `5b155448ad83ce9b3183be9ae272dc75bd058c579bcb71feb8f0204a7ce4edec` |
| Module SHA256 | `582d5f874fedf92ca5977b66055fca2f83f17170ba0db37227ce204f0c60d011` |
| Blocker | UFFD, `TID 2250370`, `direct_page_fault` |
| Intervention | `T=10s`, khi `transition=1`, `patch_state=0` |
| Parent scope | `/sys/fs/cgroup/machine.slice/machine-qemu\x2d6\x2dvm1.scope` |

Wait-only baseline hoàn tất tại `17.09s`, `17.09s`, `17.10s`.

## 3. Step 1 — Resolve đúng whole-domain scope

**Mục đích:** bảo đảm quota áp cho emulator, vCPU và các descendant, không chỉ một thread con.

```bash
QEMU_PID=$(cat /run/libvirt/qemu/vm1.pid)
cat /proc/$QEMU_PID/cgroup
find /sys/fs/cgroup/machine.slice -maxdepth 1 -type d -name '*vm1.scope'
```

**Output thực tế:**

```text
QEMU_PID=2250361
0::/machine.slice/machine-qemu\x2d6\x2dvm1.scope/libvirt/emulator
/sys/fs/cgroup/machine.slice/machine-qemu\x2d6\x2dvm1.scope
```

Treatment target:

```bash
CGROUP_DIR='/sys/fs/cgroup/machine.slice/machine-qemu\x2d6\x2dvm1.scope'
```

Không ghi quota vào `$CGROUP_DIR/libvirt/emulator`.

## 4. Step 2 — Chụp baseline và cài rollback

**Mục đích:** có điểm đối chiếu và luôn khôi phục quota ban đầu.

```bash
ORIGINAL_CPU_MAX=$(cat "$CGROUP_DIR/cpu.max")
cat "$CGROUP_DIR/cpu.max"
cat "$CGROUP_DIR/cpu.stat"
trap 'printf "%s\n" "$ORIGINAL_CPU_MAX" | sudo tee "$CGROUP_DIR/cpu.max" >/dev/null' EXIT
```

**Output quota trước treatment:**

```text
max 100000
```

## 5. Step 3 — Áp ba treatment

**Mục đích:** kiểm tra từ quota vừa đến quota cực đoan trên cùng blocker condition.

| Run | Lệnh ghi `cpu.max` | Capacity |
|---|---|---|
| 1 | `printf '%s\n' '40000 100000'` | 0.4 CPU, khoảng 20% aggregate của VM 2 vCPU |
| 2 | `printf '%s\n' '20000 100000'` | 0.2 CPU, khoảng 10% aggregate |
| 3 | `printf '%s\n' '1000 100000'` | 0.01 CPU, khoảng 0.5% aggregate |

Mẫu lệnh cho từng run:

```bash
printf '%s\n' '<QUOTA> 100000' | sudo tee "$CGROUP_DIR/cpu.max"
cat "$CGROUP_DIR/cpu.max"
cat "$CGROUP_DIR/cpu.stat" > cpu-stat-before.txt

# Quan sát transition và patch_state từ T=10s tới khi transition=0.

cat "$CGROUP_DIR/cpu.stat" > cpu-stat-after.txt
printf '%s\n' "$ORIGINAL_CPU_MAX" | sudo tee "$CGROUP_DIR/cpu.max"
cat "$CGROUP_DIR/cpu.max"
```

**Read-back thực tế:**

```text
Run 1: 40000 100000
Run 2: 20000 100000
Run 3: 1000 100000
Rollback: max 100000
```

## 6. Step 4 — Transition observations

Các run bắt đầu treatment khi blocker vẫn pending tại khoảng 10 giây.

| Run | Sample đầu sau action | Sample cuối còn pending | Hoàn tất |
|---|---|---|---:|
| 20% aggregate | `10.07s: transition=1, patch_state=0` | `14.92s: 1/0` | `16.54s` |
| 10% aggregate | `10.06s: transition=1, patch_state=0` | `14.11s: 1/0` | `16.54s` |
| 0.5% aggregate | `10.06s: transition=1, patch_state=0` | `14.92s: 1/0` | `16.54s` |

Sau đó `patch_state` đổi sang `1`, rồi `transition` đổi sang `0`. Completion nằm trong cửa sổ KLP signaling đã quan sát ở wait-only/long-stall run; không có trace đủ để gán nguyên nhân completion trực tiếp cho throttle.

Quan trọng hơn, không run nào hoàn tất trước mốc signaling khoảng 15 giây. Vì vậy không quan sát được early recovery do throttle.

## 7. Step 5 — Xác nhận treatment bằng `cpu.stat`

| Run | Δ `usage_usec` | Δ `nr_periods` | Δ `nr_throttled` | Δ `throttled_usec` |
|---|---:|---:|---:|---:|
| 20% aggregate | +561,003 | +65 | +1 | +57,520 |
| 10% aggregate | +607,273 | +65 | +1 | +76,512 |
| 0.5% aggregate | +383,281 | +65 | +65 | +5,298,456 |

**Cách đọc:**

- Hai quota đầu đã được read-back đúng nhưng chỉ chạm giới hạn ở 1/65 period trong cửa sổ đo.
- Quota cực đoan bị throttle 65/65 period và hơn 5.29 giây, nên đây là treatment mạnh nhất.
- Dù treatment mạnh, blocker vẫn pending tới cửa sổ signaling; kết quả không ủng hộ giả thuyết throttle tạo early recovery.

## 8. Step 6 — So với wait-only baseline

| Method | Số run | Transition hoàn tất | Early recovery trước 15s? |
|---|---:|---:|---|
| Wait-only | 3 | `17.09–17.10s` | Không |
| Throttle | 3 mức, 1 run/mức | `16.54s` | Không |

Chênh lệch khoảng 0.55 giây nhỏ hơn độ chắc chắn cần thiết để kết luận throttle cải thiện recovery, do sampling cadence và mỗi quota mới có một run. Kết luận phù hợp là `NOT OBSERVED`, không phải `HELPED` hay một khẳng định phổ quát `NEGATIVE`.

## 9. VM impact và giới hạn

Evidence hiện có định lượng CPU throttling bằng `cpu.stat`. Chưa có ping và throughput đồng timeline cho từng quota trên chính controlled pending run, vì vậy chưa đủ để so sánh đầy đủ service impact giữa các mức.

Các giới hạn cần giữ trong báo cáo:

- mỗi quota chỉ có một run;
- 20% và 10% tạo ít throttled period trong cửa sổ đo;
- built-in KLP signaling là confounder sau khoảng 15 giây;
- kết quả chỉ áp dụng cho UFFD blocker hiện tại.

## 10. Cleanup và gate

**Lệnh:**

```bash
printf '%s\n' "$ORIGINAL_CPU_MAX" | sudo tee "$CGROUP_DIR/cpu.max"
cat "$CGROUP_DIR/cpu.max"
virsh domstate vm1
```

**Output thực tế:**

```text
max 100000
running
```

| Gate | Trạng thái |
|---|---|
| Đúng parent domain cgroup | **PASS** |
| `cpu.max` read-back đúng | **PASS** |
| `cpu.stat` chứng minh throttle | **PASS** |
| Rollback về quota ban đầu | **PASS** |
| Throttle tạo early recovery | **NOT OBSERVED** |
| Performance/health comparison đầy đủ | **PARTIAL** |

## 11. Kết quả thực nghiệm automation throttle trên host (`recovery-v4`)

Automation đã resolve unified cgroup v2 trực tiếp từ QEMU PID (`/sys/fs/cgroup/machine.slice/machine-qemu\x2d6\x2dvm1.scope/cpu.max`), lưu quota ban đầu, áp quota mới, polling transition và tự động restore quota ban đầu trong `finally`.

### 11.1. Standalone throttle trial (`throttle-auto-01`)

**Mục đích:** kiểm tra throttle độc lập với timeout bước 4.0s (kết thúc ở giây thứ 14, trước mốc 15s của built-in KLP signal) để xem throttle có tự tạo early transition hay không.

**Lệnh thực tế:**

```bash
sudo python3 -u /home/ubuntu/run_recovery_matrix.py \
  --case throttle-auto-01 \
  --output-dir /home/ubuntu/FINAL_EVIDENCE/recovery-v4
```

**Trích đoạn log thực tế (`throttle-auto-01.log`):**

```text
# [2026-09-04T08:42:24.346+00:00] INFO throttle_applied original_cpu_max="max 100000" requested_cpu_max="1000 100000" readback="1000 100000"
...
# [2026-09-04T08:42:28.347+00:00] WARNING recovery_step_timeout method="throttle" timeout_seconds=4.0 transition=1 enabled=1
# [2026-09-04T08:42:28.347+00:00] INFO throttle_restored restored_cpu_max="max 100000" readback="max 100000"
# [2026-09-04T08:42:28.347+00:00] ERROR final_result result="transition_still_pending" exit_code=7

active-postcheck: transition=1, patch_state=0, injector_alive=true,
fault_hold_elapsed=14.810s, fault_hold_remaining=30.190s
post-cleanup: vm1=running, cpu.max="max 100000", ping=0% loss
```

**Nhận xét:**
1. Trong suốt 4.0 giây áp quota `1000/100000`, `transition` vẫn giữ giá trị 1 liên tục.
2. Đúng timeout 4.0s, chương trình ghi nhận `recovery_step_timeout`, tự động phục hồi `cpu.max` về `max 100000` và thoát với mã lỗi 7 (`EXIT_VERIFY_FAILED`). Đây là **kết quả âm hợp lệ**, chứng minh throttle không tạo early recovery.
3. Snapshot trước cleanup xác nhận blocker vẫn thật sự hoạt động và còn `30.190s` trước natural release. Sau cleanup: `vm1=running`, `cpu.max=max 100000`, ping 3/3 gói đạt 0% packet loss (avg 0.251 ms).

### 11.2. Cascade fallback tự động (`cascade-fallback-01`)

**Mục đích:** chứng minh khi throttle thất bại sau timeout bước (2.0s), automation tự phục hồi quota và chuyển giao sang method kế tiếp (`suspend-resume`) để cứu hộ thành công.

**Lệnh thực tế:**

```bash
sudo python3 -u /home/ubuntu/run_recovery_matrix.py \
  --case cascade-fallback-01 \
  --output-dir /home/ubuntu/FINAL_EVIDENCE/recovery-v4
```

**Trích đoạn log thực tế (`cascade-fallback-01.log`):**

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

## 12. Raw evidence

### Bộ evidence gốc (manual & baseline):
- [`throttle-run-01.log`](../Docs/FINAL_EVIDENCE/throttle/throttle-run-01.log)
- [`throttle-run-02.log`](../Docs/FINAL_EVIDENCE/throttle/throttle-run-02.log)
- [`throttle-run-03.log`](../Docs/FINAL_EVIDENCE/throttle/throttle-run-03.log)
- [`cpu-stat.txt`](../Docs/FINAL_EVIDENCE/throttle/cpu-stat.txt)
- [`wait-run-01.log`](../Docs/FINAL_EVIDENCE/wait/wait-run-01.log)
- [`wait-run-02.log`](../Docs/FINAL_EVIDENCE/wait/wait-run-02.log)
- [`wait-run-03.log`](../Docs/FINAL_EVIDENCE/wait/wait-run-03.log)

### Bộ evidence automation v4:
- [`throttle-auto-01.log`](../Docs/FINAL_EVIDENCE/recovery-v4/throttle-auto-01.log)
- [`throttle-auto-01-active-postcheck.json`](../Docs/FINAL_EVIDENCE/recovery-v4/throttle-auto-01-active-postcheck.json)
- [`throttle-auto-01-postcheck.json`](../Docs/FINAL_EVIDENCE/recovery-v4/throttle-auto-01-postcheck.json)
- [`cascade-fallback-01.log`](../Docs/FINAL_EVIDENCE/recovery-v4/cascade-fallback-01.log)
- [`cascade-fallback-01-active-postcheck.json`](../Docs/FINAL_EVIDENCE/recovery-v4/cascade-fallback-01-active-postcheck.json)
- [`cascade-fallback-01-postcheck.json`](../Docs/FINAL_EVIDENCE/recovery-v4/cascade-fallback-01-postcheck.json)
