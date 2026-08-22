
  

## 1. Bối cảnh: Trước khi có "distro"

  

Câu chuyện bắt đầu không phải với một bản phân phối, mà với một **nhân (kernel)**.

  

- **25/8/1991**: Linus Torvalds, khi đó là sinh viên khoa học máy tính tại Đại học Helsinki (Phần Lan), đăng một thông báo nổi tiếng lên nhóm tin Usenet `comp.os.minix`, mô tả một dự án hệ điều hành nhỏ, "chỉ là hobby, sẽ không lớn và chuyên nghiệp như GNU" — câu nói sau này trở thành giai thoại vì hoàn toàn sai.

- **17/9/1991**: Kernel Linux 0.01 được phát hành.

- **5/10/1991**: Linux 0.02 — bản công khai đầu tiên có thể chạy được.

- Bản thân kernel không phải là một hệ điều hành hoàn chỉnh — nó cần trình biên dịch, shell, thư viện… phần lớn lấy từ dự án **GNU** của Richard Stallman (bắt đầu từ 1983), cộng thêm hệ thống X Window để có giao diện đồ họa. Vì vậy nhiều người dùng thuật ngữ "GNU/Linux" để nhấn mạnh vai trò của GNU.

  

Vì bản thân kernel trần trụi rất khó dùng, nhu cầu đóng gói kernel + phần mềm GNU + trình cài đặt thành một bộ hoàn chỉnh đã khai sinh ra khái niệm **"bản phân phối" (distribution/distro)**.

  

## 2. 1992: Những distro đầu tiên

  

- **TAMU Linux (5/1992)** — do nhóm Texas A&M Unix & Linux Users Group tạo, là distro đầu tiên có kèm hệ thống X Window thay vì chỉ chạy dòng lệnh.

- **MCC Interim Linux (2/1992)** — do Owen Le Blanc tại Manchester Computing Centre (Anh) tạo ra, được coi là distro **có thể cài đặt** đầu tiên, gồm đĩa boot/root kết hợp.

- **Softlanding Linux System – SLS (5/1992)** — do Peter MacDonald tạo, với khẩu hiệu "Gentle touchdowns for DOS bailouts". <cite index="17-1">Đây là bản phát hành đầu tiên cung cấp một bản phân phối Linux toàn diện, không chỉ gồm kernel và GNU mà còn có cả một phiên bản của hệ thống X Window.</cite> SLS từng rất phổ biến nhưng nổi tiếng nhiều lỗi, và một quyết định đổi định dạng file thực thi đã khiến người dùng rời bỏ. Điều thú vị là SLS chính là "tổ tiên" trực tiếp của **cả Slackware lẫn Debian** — hai trong số các dòng distro có ảnh hưởng lớn nhất lịch sử.

- **Yggdrasil Linux/GNU/X (11/1992)** — được xem là distro Linux thương mại đầu tiên, phát hành trên CD-ROM với khẩu hiệu "Plug-and-Play Linux".

  

## 3. 1993: Hai "cột trụ" ra đời — Slackware và Debian

  

### Slackware

- <cite index="18-1">Do Patrick Volkerding tạo ra năm 1993, ban đầu dựa trên SLS</cite>, và Slackware chính thức công bố phiên bản 1.0 vào **17/7/1993**.

- <cite index="18-1">Slackware đã trở thành nền tảng cho nhiều bản phân phối Linux khác, đáng chú ý nhất là các phiên bản đầu tiên của SUSE Linux, và hiện là bản phân phối lâu đời nhất vẫn còn được duy trì.</cite>

- <cite index="18-1">Triết lý của Slackware là hướng tới sự ổn định, đơn giản trong thiết kế và cố gắng trở thành bản phân phối Linux "giống Unix" nhất</cite>, không có trình cài đặt đồ họa, không tự động giải quyết phụ thuộc gói — người dùng phải tự quản lý mọi thứ.

- <cite index="7-1">Cho đến giữa những năm 1990, Slackware từng chiếm khoảng 80% thị phần Linux</cite>, trước khi Red Hat xuất hiện và dần lấy mất vị trí dẫn đầu.

  

### Debian

- <cite index="10-1">Ian Murdock chính thức sáng lập dự án Debian ngày 16/8/1993</cite>, tên gọi "Debian" là ghép từ tên bạn gái khi đó của ông (Debra) và tên ông (Ian).

- Khác với Slackware (bắt nguồn từ SLS), Debian được xây dựng như một dự án độc lập, hướng tới mô hình phát triển mở, cộng đồng, tuân thủ triết lý phần mềm tự do của GNU.

- <cite index="10-1">Phiên bản ổn định đầu tiên chỉ được phát hành năm 1996.</cite>

- Debian sau này trở thành "gốc rễ" của một hệ sinh thái khổng lồ: **Ubuntu, Linux Mint, Kali Linux, MX Linux, Raspberry Pi OS…** — theo DistroWatch, có tới hơn 250 distro bắt nguồn từ Debian.

  

## 4. 1994: SUSE và Red Hat

  

- **SUSE** — bốn người Đức (Thomas Fehr, Roland Dyroff, Burchard Steinbild, Hubert Mantel) lập ra dự án SuSE (Software und System-Entwicklung) năm 1992, ban đầu phân phối bản dịch tiếng Đức của Slackware, sau đó dựa trên Jurix Linux để tạo ra SuSE Linux riêng vào 1994.

- **Red Hat Linux** — ra mắt ngày 3/11/1994, do Marc Ewing tạo (tên "Red Hat" xuất phát từ chiếc mũ đỏ ông hay đội thời đại học), sau đó hợp nhất với công ty ACC Corp của Bob Young để thành **Red Hat Software**. Red Hat giới thiệu định dạng gói **RPM (RPM Package Manager)**, trở thành chuẩn cho cả một họ distro sau này (Fedora, CentOS, openSUSE, Mandriva...).

- **14/3/1994**: Kernel Linux 1.0.0 chính thức phát hành — cột mốc đánh dấu Linux đã "trưởng thành" thành một hệ điều hành hoàn chỉnh, đúng lúc ba trụ cột Slackware, Debian, Red Hat vừa hình thành.

  

## 5. Giữa – cuối thập niên 1990: Linux bước vào doanh nghiệp

  

- Các desktop environment **KDE** (1996) và **GNOME** (1999) ra đời, giúp Linux thân thiện hơn với người dùng phổ thông.

- <cite index="19-1">Năm 1999, IBM bắt tay với Red Hat, tuyên bố hỗ trợ Linux; cùng năm Dell bắt đầu cài sẵn Linux trên một số dòng máy chủ.</cite>

- **Mandrake Linux** (1998) ra đời — một nhánh thân thiện hơn của Red Hat, sau đổi tên thành Mandriva (2005) sau khi sáp nhập với Conectiva.

- **Caldera OpenLinux**, **Corel Linux** cũng là những distro thương mại nổi bật thời kỳ này (phần lớn nay đã ngừng hoạt động).

  

## 6. Đầu những năm 2000: Bùng nổ đa dạng hóa

  

- <cite index="19-1">Năm 2000, IBM đầu tư 1 tỷ USD vào phát triển Linux</cite> — một cột mốc cho thấy giới doanh nghiệp lớn đã coi Linux là chiến lược dài hạn.

- **2000–2003**: Red Hat tái cấu trúc, tách dòng sản phẩm thương mại **Red Hat Enterprise Linux (RHEL)** dành cho doanh nghiệp, còn phiên bản cộng đồng miễn phí trở thành **Fedora** (2003) — sân chơi thử nghiệm công nghệ mới trước khi đưa vào RHEL.

- **CentOS** (2004) ra đời như một bản build lại mã nguồn mở của RHEL, miễn phí, tương thích nhị phân — trở thành lựa chọn phổ biến cho máy chủ trong gần 20 năm.

- **Gentoo Linux** (chính thức 2002, khởi nguồn từ dự án "Enoch" cuối 1999) — distro dựa trên biên dịch mã nguồn (source-based) với hệ thống Portage, cho phép tối ưu hóa cực sâu theo phần cứng.

- **Arch Linux** (2002) — do Judd Vinet sáng lập, lấy cảm hứng từ CRUX, theo triết lý **KISS** (Keep It Simple, Stupid), mô hình **rolling release** (cập nhật liên tục, không có "phiên bản" cố định) và trình quản lý gói **pacman** cùng kho **AUR** nổi tiếng.

- **PCLinuxOS** — bắt nguồn từ các gói RPM cải tiến cho Mandrake.

  

## 7. 2004: Ubuntu — bước ngoặt đưa Linux đến người dùng phổ thông

  

- **20/10/2004**: Mark Shuttleworth (doanh nhân Nam Phi, người từng bay vào vũ trụ) thành lập công ty **Canonical**, phát hành **Ubuntu 4.10 "Warty Warthog"**, dựa trên nền Debian nhưng có chu kỳ phát hành đều đặn (6 tháng/lần), cài đặt dễ dàng, hỗ trợ phần cứng tốt.

- <cite index="5-1">Ubuntu giúp mở rộng đáng kể lượng người dùng desktop Linux, đưa Linux đến gần hơn với cả người dùng gia đình bình thường lẫn lập trình viên chuyên nghiệp.</cite>

- Ubuntu sau đó sinh ra vô số biến thể chính thức: **Kubuntu (KDE), Xubuntu (Xfce), Lubuntu (LXDE/LXQt), Edubuntu**…

  

## 8. 2006: Linux Mint

  

- Do **Clément Lefèbvre** khởi xướng, dựa trên Ubuntu (và qua đó là Debian), tập trung vào trải nghiệm "ra là dùng được ngay" cho người mới — tích hợp sẵn codec đa phương tiện, driver độc quyền. Môi trường desktop **Cinnamon** do chính dự án Mint phát triển sau này trở thành thương hiệu riêng của distro này, đặc biệt sau khi Ubuntu chuyển sang giao diện Unity (2011) gây tranh cãi.

  

## 9. Linux vượt ra ngoài máy tính để bàn

  

- <cite index="5-1">Google phát hành hai hệ điều hành dựa trên nhân Linux: Android cho di động (giữa 2008) và Chrome OS chạy trên Chromebook (2011)</cite> — đưa Linux (dưới lớp vỏ khác) vào tay hàng tỷ người dùng mà họ thậm chí không biết đó là Linux.

- Trong mảng điện toán đám mây, các hãng lớn như AWS, Google Cloud đều xây hạ tầng trên nền Linux.

  

## 10. Thập niên 2010: Chuyên biệt hóa và tranh cãi systemd

  

- **openSUSE** (2005) tách ra làm phiên bản cộng đồng sau khi Novell mua lại SUSE (2004), trong khi SUSE Linux Enterprise là dòng thương mại.

- **Manjaro** (2011) — làm cho Arch Linux dễ tiếp cận hơn với người dùng phổ thông.

- **elementary OS** (2011), **Zorin OS**, **Pop!_OS** (2017, của System76) — các distro tập trung mạnh vào thẩm mỹ và trải nghiệm người dùng, thường dựa trên Ubuntu.

- **Alpine Linux** (2005, phổ biến rộng từ giữa 2010s) — cực nhẹ, dùng musl libc thay glibc, trở thành tiêu chuẩn cho image Docker/container.

- **CoreOS** (2013, sau được Red Hat mua năm 2018 rồi hợp nhất vào Fedora CoreOS) — distro tối giản chuyên cho container.

- Việc **systemd** (khởi động bởi Lennart Poettering, 2010) dần thay thế các hệ thống init truyền thống (SysVinit) trên hầu hết distro lớn (Debian, Fedora, Ubuntu, Arch, openSUSE...) gây ra một trong những cuộc tranh luận gay gắt nhất cộng đồng Linux, dẫn tới sự ra đời của các distro "kháng systemd" như **Devuan** (2016, nhánh của Debian giữ SysVinit) và **Void Linux** (dùng runit).

  

## 11. 2020–2021: Cú sốc CentOS và làn sóng kế nhiệm

  

- Cuối **2020**, Red Hat tuyên bố sẽ ngừng CentOS Linux truyền thống (bản build lại RHEL) và chuyển trọng tâm sang **CentOS Stream** — một bản rolling nằm ở "thượng nguồn" của RHEL thay vì bản sao y hệt. Quyết định này gây phản ứng dữ dội trong cộng đồng máy chủ/doanh nghiệp vốn phụ thuộc vào CentOS miễn phí, ổn định.

- Hệ quả là hai distro mới ra đời để "lấp khoảng trống" CentOS để lại:

  - **Rocky Linux** (2021) — do Gregory Kurtzer, một trong những người sáng lập CentOS ban đầu, khởi xướng.

  - **AlmaLinux** (2021) — do CloudLinux tài trợ.

- Cả hai đều đặt mục tiêu tương thích nhị phân 1:1 với RHEL, tiếp tục vai trò mà CentOS từng đảm nhiệm.

  

## 12. Xu hướng gần đây: distro "bất biến" (immutable) và hình ảnh nguyên khối

  

- **Fedora Silverblue / Fedora Atomic**, **openSUSE MicroOS/Aeon**, dự án **Universal Blue** (Bazzite, Bluefin...) — theo mô hình hệ điều hành gần như chỉ đọc (read-only root filesystem), cập nhật theo dạng "image" nguyên khối kiểu OSTree, ứng dụng chạy chủ yếu qua Flatpak/container để tăng độ ổn định và bảo mật.

- **SteamOS** của Valve (dùng cho Steam Deck) — dựa trên Arch Linux, là ví dụ tiêu biểu cho distro Linux "phổ thông hóa" gaming, một lĩnh vực Linux từng yếu thế so với Windows.

- Các distro tập trung bảo mật/riêng tư như **Tails**, **Qubes OS**, hay pentest như **Kali Linux** (dựa trên Debian, kế thừa từ BackTrack) tiếp tục phát triển mạnh trong giới an ninh mạng.

  

## 13. Tổng quan "cây gia phả" các họ distro chính

  

| Họ gốc | Cơ chế gói | Distro tiêu biểu kế thừa |
| **Slackware** (1993) | tgz/pkgtool | SUSE (ban đầu), Zenwalk, Salix |

| **Debian** (1993) | dpkg/APT | Ubuntu → Mint, Kali, Raspberry Pi OS, MX Linux, Devuan |

| **Red Hat** (1994) | RPM/yum-dnf | Fedora, RHEL → CentOS/Rocky/AlmaLinux, Mandrake→Mandriva |

| **SUSE** (1994) | RPM/zypper | openSUSE, SUSE Linux Enterprise |

| **Arch** (2002) | pacman | Manjaro, EndeavourOS, SteamOS |

| **Gentoo** (2002) | Portage (build từ nguồn) | Calculate Linux, Sabayon (cũ) |

  

## 14. Vài con số thú vị

  

- <cite index="2-1">Theo DistroWatch, khoảng 66 bản phân phối từng bắt nguồn từ Slackware; Red Hat Linux sinh ra khoảng 40 nhánh trực tiếp (cộng thêm ~80 nhánh từ Fedora); trong khi Debian — "ông tổ" lớn nhất — có tới khoảng 250 distro kế thừa.</cite>

- Hiện tại DistroWatch theo dõi hàng trăm bản phân phối đang hoạt động, phản ánh sự đa dạng đáng kinh ngạc của hệ sinh thái mã nguồn mở này — từ những distro siêu tối giản chỉ vài MB đến các bản phân phối máy chủ doanh nghiệp phức tạp, từ Linux chạy trên siêu máy tính đến Linux trong túi quần (Android).

  

---

  

*Tài liệu này tổng hợp từ nhiều nguồn công khai (Wikipedia, DistroWatch, Opensource.com, Red Hat Blog...) tính đến 2026. Nếu bạn muốn mình đào sâu vào một nhánh cụ thể (ví dụ: chi tiết sự phát triển của Ubuntu qua từng phiên bản, hoặc cuộc chiến systemd, hoặc lịch sử Android như một "distro" đặc biệt), cứ nói nhé.*