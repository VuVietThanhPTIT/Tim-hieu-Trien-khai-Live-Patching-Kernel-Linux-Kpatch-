
System calls are the "API" between user space and kernel space
- `read()`: Read data from a file.
- `write()`: Write data to a file.
- `fork()`: Create a new process (Linux/macOS).
**How a System Call Works**:
- The user app invokes a system call 
- The cpu switches  to kernel mode ( via trap instruction like 'syscall' )
- The kernel validates the request ( check  if the FD is valid)
- The kernel perform the operation ( read data from  disk into 'buffer')
- The Cpu switch back to user mode , app resumes execution with the result 

## check  if the FD is valid
- check fd có hợp lệ không ( mở bảng FD xem có truy cập đúng vào cái dòng của tiến trình đó hay không ,và cái trạn thái của nó có đang mở hay không )
	- check tiếp quyền yêu cầu của user có hợp lệ với quyền đã ghi vào hồ sơ mở file hay không ( cái bảng FD)
	- kiểm tra con trỏ buffer có hợp lệ không ( nếu không check có thể đọc hoặc ghi nhầm vào chính dữ liệu của kernel đó )
	- Check tiếp size âm hoặc quá lớn -> từ chối 
	- 
	- check tiếp quyền hạng tầng UID