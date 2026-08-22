- Vì sao cần CS , mỗi tiến trình chạy được trong 1 timeslice 



## 1. PCB (Process Control Block)  — "hồ sơ lý lịch" của tiến trình

Trước khi vào 6 bước, cần hiểu PCB: đây là **1 cấu trúc dữ liệu kernel giữ cho mỗi tiến trình**, giống như "phiếu theo dõi" — chứa mọi thứ cần để sau này "phục hồi lại y hệt trạng thái đang chạy dở". PCB gồm:

- Program Counter (PC) — đang chạy tới câu lệnh nào.
- Giá trị các thanh ghi CPU (registers) — biến tạm CPU đang xử lý.
- Trạng thái tiến trình (Running/Ready/Blocked).
- Con trỏ tới bảng trang (Page Table) của tiến trình đó.
- Thông tin khác: PID, độ ưu tiên, danh sách FD đang mở...



## 2. Đi chi tiết từng bước trong 6 bước

### Bước 1: Lưu trạng thái CPU hiện tại vào PCB

- Khi có tín hiệu ngắt (interrupt) báo "tới lúc chuyển tiến trình", CPU đang chạy dở tiến trình A với Program Counter đang trỏ tới 1 lệnh cụ thể, và các thanh ghi (registers) đang giữ giá trị tính toán tạm thời.
- Kernel copy toàn bộ những giá trị này (PC + registers) từ CPU **ra** PCB của tiến trình A, lưu vào RAM.
- **Vì sao bắt buộc phải làm bước này?** Vì thanh ghi CPU chỉ có 1 bộ vật lý duy nhất, dùng chung cho mọi tiến trình. Nếu không lưu lại, khi B chạy và ghi đè lên các thanh ghi đó, thông tin tính toán dở của A sẽ **mất vĩnh viễn** — không cách nào chạy tiếp A đúng chỗ cũ được.

### Bước 2: Cập nhật trạng thái tiến trình cũ

Tiến trình A chuyển từ **Running** sang:

- **Ready** (nếu chỉ là hết time slice, A vẫn có thể chạy tiếp, chỉ đang đợi tới lượt) — giống bạn tạm dừng game, sẵn sàng chơi tiếp bất cứ lúc nào.
- **Blocked** (nếu A đang đợi I/O, ví dụ đợi đọc xong dữ liệu từ đĩa) — A không có gì để làm cho tới khi I/O xong, nên không nằm trong hàng đợi "sẵn sàng chạy".

### Bước 3: Di chuyển PCB vào hàng đợi tương ứng

- Kernel có sẵn các **hàng đợi (queue)** khác nhau: Ready queue, Blocked queue (hoặc Wait queue theo từng loại tài nguyên).
- PCB của A được đưa vào đúng hàng đợi tương ứng với trạng thái mới ở Bước 2.

### Bước 4: Scheduler chọn tiến trình mới từ Ready Queue

- **Scheduler** là "bộ não" quyết định "tiếp theo chạy ai" — dựa trên thuật toán điều phối (Round Robin, Priority-based, CFS của Linux...).
- Giả sử Scheduler chọn ra tiến trình B.

### Bước 5: Cập nhật cấu trúc quản lý bộ nhớ (đổi Page Table)

- Đây là bước **quan trọng và tốn kém nhất** — liên quan trực tiếp tới phần cô lập bộ nhớ đã học trước đó.
- CPU có 1 thanh ghi đặc biệt (trên x86 gọi là **CR3**) trỏ tới **bảng trang của tiến trình đang chạy**. Kernel phải đổi giá trị thanh ghi này để trỏ sang bảng trang của B.
- Từ giờ, mọi địa chỉ ảo CPU phát ra sẽ được dịch theo bảng trang của **B**, không còn theo A nữa.

### Bước 6: Khôi phục ngữ cảnh của tiến trình mới và chạy tiếp

- Kernel lấy PCB của B ra, **nạp ngược lại** các giá trị Program Counter + thanh ghi đã lưu từ lần trước vào CPU.
- CPU tiếp tục chạy đúng từ chỗ B đã dừng lại trước đó — B hoàn toàn không biết là mình vừa "bị đóng băng" một khoảng thời gian.

---

## 3. Vì sao Context Switch giữa 2 tiến trình lại tốn kém — giải thích sâu hơn

Đoạn gốc chỉ nói gọn "vì phải nạp lại bảng trang" — mình giải thích rõ tại sao đổi bảng trang lại đắt:

### a) Chi phí trực tiếp: đổi CR3

- Bản thân việc ghi giá trị mới vào thanh ghi CR3 thì nhanh (1 lệnh CPU). Cái đắt nằm ở **hệ quả** của việc đổi này.

### b) Chi phí gián tiếp lớn nhất: TLB bị vô hiệu hoá (TLB flush)

- Nhớ lại: **TLB (Translation Lookaside Buffer)** là cache nhỏ trong CPU, lưu sẵn các ánh xạ địa chỉ ảo → vật lý _vừa dùng gần đây_, để không phải tra bảng trang trong RAM (chậm) mỗi lần truy cập bộ nhớ.
- Nhưng TLB đang cache là ánh xạ của **A**. Khi đổi sang bảng trang của B, các mục trong TLB đó **hoàn toàn sai** đối với B (vì B có ánh xạ địa chỉ ảo → vật lý khác hẳn).
- → Kernel phải **xoá sạch (flush) TLB**, và B phải bắt đầu lại từ đầu: mỗi lần truy cập bộ nhớ mới đều bị **TLB miss**, phải tra bảng trang thật trong RAM (chậm hơn nhiều so với tra TLB) — cho tới khi TLB "làm nóng lại" (dần dần cache lại ánh xạ của B).
- Đây chính là phần chi phí **âm thầm nhưng lớn nhất**: không phải chi phí lúc switch, mà là **chi phí chậm dần trong 1 khoảng thời gian sau đó**, vì liên tục bị cache miss.

### c) Chi phí gián tiếp khác: Cache CPU (L1/L2) cũng "lạnh"

- Tương tự TLB, cache dữ liệu/lệnh (L1, L2 cache) đang chứa dữ liệu "nóng" của A. Khi B chạy, dữ liệu B cần chưa có trong cache → nhiều cache miss → phải lấy từ RAM chậm hơn.
- Vấn đề này gọi là **cache pollution / cold cache** sau context switch.

---

## 4. Vì sao Thread Switch (chuyển giữa 2 luồng cùng 1 tiến trình) lại rẻ hơn nhiều

**Điểm mấu chốt:** các **thread trong cùng 1 tiến trình dùng chung 1 không gian địa chỉ ảo** (chung 1 bảng trang) — chỉ khác nhau ở: Program Counter riêng, thanh ghi riêng, và **stack riêng** cho mỗi thread. Còn heap, code, data thì dùng chung.

→ Khi chuyển từ thread 1 sang thread 2 (cùng tiến trình):

- Vẫn cần lưu/khôi phục Program Counter + thanh ghi (Bước 1 và 6 như cũ) — chi phí này **không tránh được** dù là process switch hay thread switch.
- Nhưng **Bước 5 (đổi bảng trang) không cần làm** — vì 2 thread dùng chung 1 bảng trang, CR3 không đổi.
- → **TLB không bị flush**, cache không bị "lạnh" theo cùng mức độ — vì phần lớn dữ liệu/code vẫn dùng chung, vẫn còn "nóng" trong cache.


[Kernel Space vs User Space: Key Differences, Kernel Threads, Processes, Stack Explained & Why This Differentiation Matters — linuxvox.com](https://linuxvox.com/blog/what-is-the-difference-between-the-kernel-space-and-the-user-space/)
