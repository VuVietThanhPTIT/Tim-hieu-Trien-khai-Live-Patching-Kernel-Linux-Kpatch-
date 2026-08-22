## What : 
- Là lớp trung gian giữa ứng dụng người dùng và lớp file hệ thống bên dưới 
- Cung cấp 1 chuẩn thao tác với file : open  , read , write and clode  , mỗi cái thì được VFS implen khác nhau cho từng loại file 
- Khi 1 ứng dụng gọi sys calll  , VFS routes cái call tới  file system drive thích hợp 
	- Dentry : ánh xạ giữa tên file và inode , mỗi phần của 1 path có 1 dentry riêng , được cache lại 
	- Inodes 
	- Superblocks [[superblock]]