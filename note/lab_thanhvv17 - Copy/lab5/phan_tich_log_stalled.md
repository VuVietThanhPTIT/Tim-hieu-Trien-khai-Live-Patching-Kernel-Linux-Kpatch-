**Tổng quan kịch bản thử nghiệm**

  

Nhật ký ghi lại quá trình kiểm thử độ tin cậy của cơ chế **Kernel Livepatching (KLP)** khi kernel đang rơi vào trạng thái treo CPU (**vCPU/MMU Stall**):

  

1. Module `stall_sim.ko` sử dụng **kprobe** để đón đầu hàm quản lý bộ nhớ của KVM (`kvm_mmu_get_child_sp` hoặc `__link_shadow_page`) và ép CPU chạy vòng lặp bận (busy-wait) trong tối đa 60 giây.
    
      
    
2. Trong lúc CPU đang bị kẹt, lệnh nạp bản vá `livepatch_noble` được kích hoạt để kiểm tra phản ứng của nhân Linux.
    
      
    

**Diễn biến phân tích chi tiết theo từng giai đoạn**

  

**1. Giai đoạn 1: Kprobe bắt trúng mục tiêu và ép treo CPU**

  

- Lệnh `insmod stall_sim.ko` đăng ký kprobe thành công.
    
      
    
- Khi một máy ảo thực hiện phân giải lỗi trang (EPT/Page Fault), hàm `kvm_mmu_get_child_sp` được gọi trên **CPU 3** (tiến trình `CPU 1/KVM`, PID `630331`).
    
      
    
- Kprobe can thiệp qua `handler_pre+0xae` và kích hoạt vòng lặp quay vô tận (`f3 90 pause`) để giữ CPU.
    
      
    

**2. Giai đoạn 2: Hiệu ứng nghẽn dây chuyền (Lock Contention Domino)**

  

- Khi CPU 3 bị giữ lại bên trong luồng xử lý MMU:
    
      
    - Một vCPU khác của máy ảo chạy trên **CPU 2** (tiến trình `CPU 0/KVM`, PID `630330`) cũng gặp page fault (`paging64_page_fault`) và cần cấp phát/tra cứu bảng trang.
        
          
        
    - Để thao tác với Shadow MMU, CPU 2 phải xin quyền ghi của khóa `mmu_lock`. Do cấu trúc bảng trang đang bị CPU 3 giữ dở dang, CPU 2 rơi vào trạng thái chờ tại hàm **`queued_write_lock_slowpath`**.
        
          
        
    - Kết quả: Cả 2 vCPU của máy ảo đều bị kẹt cứng (CPU 3 bị kẹt do mã giả lập, CPU 2 bị kẹt do chờ Spinlock).
        
          
        

**3. Giai đoạn 3: Hệ thống giám sát Kernel kích hoạt cảnh báo**

  

- **Watchdog Soft Lockup:** Sau 22 giây không nhường CPU, bộ đếm watchdog phát hiện luồng kernel không chịu chuyển đổi ngữ cảnh và in cảnh báo:
    
      
    - `watchdog: BUG: soft lockup - CPU#3 stuck for 22s! / 48s!` (kẹt tại `handler_pre` của `stall_sim`).
        
          
        
    - `watchdog: BUG: soft lockup - CPU#2 stuck for 26s! / 52s!` (kẹt tại `queued_write_lock_slowpath` chờ khóa MMU).
        
          
        
- **RCU Stall Detector:** Kernel RCU ghi nhận CPU 3 không đi qua trạng thái nghỉ (quiescent state) suốt 60.000 jiffies ($\approx$ 60 giây):
    
      
    - `rcu: INFO: rcu_preempt self-detected stall on CPU 3-....`.
        
          
        

**4. Giai đoạn 4: Phản ứng của Kernel Livepatching (KLP Transition)**

  

- Lệnh nạp livepatch chạy: `livepatch: 'livepatch_noble': starting patching transition`.
    
      
    
- Kernel áp dụng mô hình nhất quán **Consistency Model**: Không được phép chuyển đổi mã thực thi của một hàm nếu có bất kỳ tiến trình nào đang chạy hàm đó hoặc đang nằm trong stack trace của hàm đó.
    
      
    
- Do PID `630331` đang bị kẹt bên trong `kvm_mmu_get_child_sp`, Livepatch **tạm dừng và chờ đợi** (`livepatch: signaling remaining tasks`) chứ không cưỡng chế thay thế mã nguồn để tránh gây lỗi Kernel Panic hay làm hỏng bộ nhớ.
    
      
    

**5. Giai đoạn 5: Giải phóng và hoàn tất vá nóng an toàn**

  

- Sau 60 giây, cơ chế bảo vệ của module kích hoạt: `stall_sim: het gio an toan (60s), tu dong tha ra`.
    
      
    
- CPU 3 thoát khỏi vòng lặp bận, nhả tài nguyên và giải phóng khóa `mmu_lock`.
    
      
    
- CPU 2 lấy được khóa và tiếp tục xử lý xong page fault.
    
      
    
- Toàn bộ các luồng vCPU rời khỏi stack frame của hàm cũ, KLP nhận diện trạng thái an toàn và hoàn tất quá trình vá nóng ngay lập tức:
    
      
    - **`livepatch: 'livepatch_noble': patching complete`**.
        
          
        

**Kết luận kỹ thuật**

  

- **Module `stall_sim.ko` hoạt động chính xác:** Giả lập thành công tình trạng treo vCPU thực tế và kiểm chứng được hiện tượng tranh chấp khóa đọc/ghi (`queued_write_lock_slowpath`) của hệ thống phân trang KVM.
    
      
    
- **Cơ chế Livepatching vận hành an toàn:** KLP không ghi đè hàm khi đang có luồng thực thi bên trong, kiên nhẫn chờ tác vụ thoát ra ngoài rồi mới hoàn tất quá trình thay thế nhị phân trong RAM mà không làm sập OS.