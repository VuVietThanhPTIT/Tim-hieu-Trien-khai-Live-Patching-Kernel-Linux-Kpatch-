

## 1. Mục tiêu

Kiểm chứng hành vi vận hành (operational behavior) khi nạp live patch (kpatch/livepatch, module `livepatch_noble`) vá lỗ hổng use-after-free trong shadow-paging MMU của KVM (`kvm_mmu_get_child_sp()` và `__link_shadow_page()`), tập trung vào:

- Khả năng mô phỏng "stall" (kẹt) ở bước chuyển trạng thái (`transition`) của livepatch dưới tải cao trên guest.
- Ảnh hưởng của việc dùng cờ `force` khi transition không tự hoàn tất.

## 2. Môi trường thử nghiệm

- **2 VM** chạy song song trên cùng host.
    
- Cấu trúc tiến trình QEMU: **1 tiến trình emulator chính** + các **luồng con** đảm nhiệm từng vCPU (mục đích tách riêng để việc tăng tải trên vCPU con không làm nghẽn/ảnh hưởng tiến trình QEMU chính).
    
- Công cụ tạo tải trong guest:
    
    ```bash
    stress-ng --vm 4 --vm-bytes 80% --page-in -t 1800s
    ```
    
    (4 worker cấp phát 80% RAM, buộc page-in liên tục, chạy 30 phút).
    

## 3. Các kịch bản đã test

### 3.1. Kịch bản 1 – Mô phỏng stall khi nạp patch dưới tải bộ nhớ (page fault storm)

- **Cách làm:** chạy `stress-ng --vm ...` trên cả 2 VM để tạo áp lực page-fault/memory, sau đó nạp livepatch và theo dõi `/sys/kernel/livepatch/livepatch_noble/transition`.
- **Kết quả: KHÔNG THÀNH CÔNG** — không tái hiện được trạng thái `transition = 1` kéo dài.
- **Nguyên nhân (đã xác nhận qua phân tích):**
    - Hàm KVM MMU bị vá thực thi trên Host với thời gian tính bằng **micro-giây (µs)**.
    - Dù vCPU chạy `stress-ng` 100% CPU hoặc sinh page fault liên tục, phần lớn tuyệt đối thời gian thực tế của vCPU vẫn là chạy code **trong Guest** hoặc **chuyển ngữ cảnh**, không phải đang đứng trong đúng đoạn code bị patch trên Host.
    - Khi engine livepatch quét call stack của các luồng vCPU, xác suất "bắt đúng khoảnh khắc" vCPU đang nằm trong hàm KVM MMU đó là cực thấp.
    - Kết quả: ngay lần quét đầu tiên (~1–2 giây sau khi enable patch), stack của toàn bộ luồng vCPU đã "sạch" hàm cũ → kernel chuyển trạng thái (transition) thành công ngay lập tức, không có khoảng chờ đáng kể để quan sát.

### 3.2. Kịch bản 2 – Tải CPU-bound thuần trên guest

- **Cách làm:** đổi tải sang dạng CPU-bound (thay vì memory/page-fault-bound) trên guest.
- **Kết quả:** tương tự kịch bản 1 — không tạo ra được stall quan sát được ở transition, vì lý do bản chất giống mục 3.1: bản thân hàm bị vá không sleep, không giữ CPU lâu, nên dù guest CPU-bound 100% thì thời gian luồng vCPU "đi qua" đúng đoạn code Host bị vá vẫn chỉ chiếm tỉ trọng cực nhỏ trong toàn bộ vòng đời thực thi của luồng.

### 3.3. Kịch bản 3 – Ép chuyển trạng thái bằng `force`
![Kết quả force transition](img/Pasted%20image%2020260903095029.png)
- **Lệnh thực hiện:**
    
    ```bash
    echo 1 | sudo tee /sys/kernel/livepatch/livepatch_noble/force
    ```
    
- **Kết quả:** phát sinh lỗi khi thao tác nạp/gỡ patch sau đó ("Lỗi không patch được nữa" — chi tiết theo ảnh chụp màn hình đính kèm, _chưa có nguyên văn thông báo lỗi trong tài liệu này_).
    
- **Kiểm tra reference count của module:**
    
    ```bash
    cat /sys/module/livepatch_noble/refcnt 2>/dev/null
    # -> 1
    ```
    
- **Phân tích nguyên nhân:**
    
    - `refcnt = 1` là do **chính subsystem livepatch của kernel tự giữ** tham chiếu tới module, không phải do một tiến trình userspace nào khác đang dùng nó.
    - Đây là hành vi **được tài liệu hoá chính thức** (Documentation/livepatch/livepatch.rst): khi dùng `force`, kernel ép toàn bộ task chuyển sang trạng thái "đã patch" bằng cách xoá cờ `TIF_PATCH_PENDING`, **bất kể** có task nào thực sự vẫn đang chạy code cũ hay không. Vì không còn cách nào đảm bảo an toàn 100% rằng không còn task nào thực thi code cũ, kernel **chủ động khoá vĩnh viễn khả năng gỡ (`rmmod`) module patch đó** — nếu cho gỡ, vùng nhớ code cũ có thể bị giải phóng trong khi một task nào đó (trên lý thuyết) vẫn còn đang thực thi nó, dẫn tới crash/UAF ở tầng kernel.
    - Hệ quả trực tiếp: không thể `load` lại (unload trước) patch này nữa trên phiên chạy hiện tại của kernel.
- **Hướng xử lý đã áp dụng:** **reboot lại host** để giải phóng hoàn toàn trạng thái livepatch bị khoá và đưa hệ thống về trạng thái sạch.
    
![Lệnh echo 1 > force](img/Pasted%20image%2020260903111741.png)
## 4. Kết luận

|Kịch bản|Mục tiêu|Kết quả|
|---|---|---|
|1. Stall do tải memory/page-fault|Tái hiện transition kẹt dưới page-fault storm|Không tái hiện được — transition hội tụ gần như tức thời|
|2. Stall do tải CPU-bound guest|Tái hiện transition kẹt dưới tải CPU thuần|Không tái hiện được — cùng nguyên nhân bản chất với (1)|
|3. Force transition|Ép hoàn tất transition khi không kẹt tự nhiên|Thành công về mặt kỹ thuật nhưng khoá vĩnh viễn khả năng unload/reload patch, buộc phải reboot host|

**Nhận định chính:** Với đúng cặp hàm bị vá trong bản patch này (`kvm_mmu_get_child_sp`, `__link_shadow_page`), do đặc tính "chạy cực nhanh, không sleep, không giữ lock qua điểm schedule", việc gây stall bằng cách tăng tải VM (dù là memory-bound hay CPU-bound) là **không khả thi trong điều kiện test thông thường**. Muốn kiểm chứng khả năng vận hành khi transition thực sự kẹt lâu, cần một kịch bản nhân tạo (module test riêng có task rơi vào D-state — uninterruptible sleep) thay vì cố tạo áp lực trên chính subsystem KVM.

## 5. Khuyến nghị cho lần test tiếp theo

- **Không dùng `force`** trên môi trường có ý định load/unload lại patch nhiều lần trong cùng phiên chạy kernel — chỉ dùng khi thực sự chấp nhận phải reboot sau đó (đúng như tài liệu kernel cảnh báo: "used at your own risk").
- Muốn luyện tập/diễn tập quy trình xử lý stall (theo dõi `transition`, đọc `/proc/<pid>/stack`, quyết định có `force` hay không) nên dùng module test độc lập (`stuckmod` + livepatch demo) để mô phỏng D-state có kiểm soát, tách hoàn toàn khỏi subsystem KVM đang chạy production.
- Nếu vẫn muốn thử tái hiện áp lực trên đúng code path KVM MMU, cần chuyển hướng tiếp cận: không nhắm vào việc kéo dài thời gian hàm chạy (vì bản chất không sleep), mà nhắm vào **tăng tần suất gọi hàm cực cao đồng thời trên nhiều pCPU** (oversubscribe pCPU, tắt EPT/NPT để ép shadow-MMU, chạy nested guest với PDE remap loop) — mục tiêu là tăng xác suất "bắt trúng" thời điểm quét stack, dù theo lý thuyết vẫn khó tạo stall kéo dài đáng kể do thời lượng hàm quá ngắn.

