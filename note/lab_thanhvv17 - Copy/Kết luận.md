## Tóm tắt ngắn gọn

**Vấn đề:** Cgroup CPU Throttle chỉ hiệu quả trong một số trường hợp nhất định khi task bị kẹt "transition" (chuyển đổi livepatch).

**Nguyên lý:** Throttle ép task nhả CPU qua `schedule()` → kích hoạt `klp_sched_try_switch()`.

- ✅ **Thành công**: khi task (vCPU) đang bận tính toán (CPU-bound), Call Stack sạch khi bị kéo về Host.
- ❌ **Vô dụng**: khi task kẹt cứng ngay trong hàm bị vá (busy-wait, deadlock, spinlock, D-state) — throttle không xóa được con trỏ hàm cũ trên stack.

**7 phương án xử lý, từ nhẹ đến mạnh:**

| #   | Phương án                    | Phù hợp khi                                                                                         |     |
| --- | ---------------------------- | --------------------------------------------------------------------------------------------------- | --- |
| 1   | Fake signal mặc định         | Task userspace thường, hay qua syscall                                                              |     |
| 2   | Cgroup CPU Throttle          | Guest VM tải nặng CPU-bound                                                                         |     |
| 4   | SIGSTOP/SIGCONT              | Userspace loop không tự nhường CPU                                                                  |     |
| 5   | virsh suspend/resume         | vCPU chạy thuần mã Guest                                                                            |     |
| 6   | Rollback (`enabled=0`)       | An toàn nhất, dùng khi không khẩn cấp                                                               |     |
| 7   | Force transition (`force=1`) | Khẩn cấp (0-Day), task kẹt vĩnh viễn — **chỉ dùng nếu patch không đổi cấu trúc dữ liệu**, kẻo panic |     |

**Bảng chọn nhanh theo tình huống:**

- VM tính toán nặng → Throttle (dự phòng: suspend/resume)
- Hàm gọi siêu nhanh, dày đặc → CPU Pinning (dự phòng: Throttle)
- Userspace loop → SIGSTOP/CONT (dự phòng: fake signal)
- Kẹt sâu trong kernel (deadlock, MMU trap) → Rollback (dự phòng: force)
- D-state chờ I/O → chờ tự nhiên (dự phòng: Rollback)