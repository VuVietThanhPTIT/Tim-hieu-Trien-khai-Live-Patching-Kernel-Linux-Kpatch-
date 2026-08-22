- Tăng bảo mật tránh sặp user space làm sập toàn bộ hệ thống 
## Privilege Rings
CPU x86 có sẵn 1 thanh ghi lưu **mức Ring hiện tại**.
[Kernel Space vs User Space: Key Differences, Kernel Threads, Processes, Stack Explained & Why This Differentiation Matters — linuxvox.com](https://linuxvox.com/blog/what-is-the-difference-between-the-kernel-space-and-the-user-space/)

## Kernel space là vùng nhớ dành riên cho thằng operating system 
- what it does ? : managing hardware resources ( cpu ram disk net) , security policies  , and coordinatiing system-wide operations 
	- Không bị giới hạn cái gì 
## User space : vùng nhớ dành riêng cho ứng dụng người dùng 
- Có giới hạn quyền , chỉ có thể truy cập được vùng nhớ của chính nó và phải yêu cầu kernel assistance ( system call )đẻ thực hiện 1 số lệnh  như đọc disk 
- 