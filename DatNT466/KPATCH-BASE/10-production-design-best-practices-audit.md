# 10 – Production Design, Best Practices và Audit cho Hệ thống Livepatch

## Mục lục

1. [Thuật ngữ và từ viết tắt](#thuật-ngữ-và-từ-viết-tắt)
2. [Production pipeline và phân tách trách nhiệm](#1-production-pipeline-và-phân-tách-trách-nhiệm)
3. [Quản lý artifact identity và compatibility matrix](#2-quản-lý-artifact-identity-và-compatibility-matrix)
4. [Staging, canary và wave rollout](#3-staging-canary-và-wave-rollout)
5. [Metrics, alerting và rollback policy](#4-metrics-alerting-và-rollback-policy)
6. [Vòng đời dài hạn: reboot debt, cumulative patch, signing và change control](#5-vòng-đời-dài-hạn-reboot-debt-cumulative-patch-signing-và-change-control)
7. [Decision matrix, Go/No-Go và governance/audit](#6-decision-matrix-gono-go-và-governanceaudit)
8. [Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

---

## Thuật ngữ và từ viết tắt

| Thuật ngữ / Từ viết tắt | Tên đầy đủ | Giải thích ngắn gọn |
|---|---|---|
| **Canary Deployment** | Canary Release Strategy (Triển khai chim báo bão) | Chiến lược phát hành thử nghiệm bản vá trên một số ít compute node trước khi mở rộng toàn hạ tầng. |
| **Wave Rollout** | Progressive Deployment Waves (Phát hành theo làn sóng) | Quy trình phân tầng triển khai theo từng làn/tỷ lệ (1% -> 10% -> 50% -> 100%) kèm soak time. |
| **Reboot Debt** | Reboot Technical Debt (Nợ kỹ thuật tích tụ do hoãn Reboot) | Sự tích tụ rủi ro và sai lệch khi áp dụng nhiều livepatch nối tiếp mà không reboot về baseline kernel gốc. |
| **Cumulative Patch** | Cumulative Superseding Patch (Bản vá tổng hợp tích lũy) | Bản vá tổng hợp tích lũy chứa toàn bộ các fix từ trước tới nay để thay thế hoàn toàn các module patch lẻ. |
| **Module Signing** | Cryptographic Module Signing (Ký số bảo mật Kernel Module) | Cơ chế ký số PKCS#7 xác thực nguồn gốc hợp lệ của livepatch module (`modsign`). |
| **Blast Radius** | Failure Impact Scope (Bán kính tác động sự cố) | Phạm vi và quy mô tác động tới dịch vụ nếu một bản vá gặp lỗi trên môi trường production. |

---

## Vòng đời livepatch trong production

```text
CVE / BUG FIX EXPLOIT
         │
         ▼
Patch Engineering Review (Phân tích mã nguồn)
         │
         ▼
Patchability Gate & Reproducible Build (Biên dịch nhị phân)
         │
         ▼
Artifact Validation & PKCS#7 Module Signing (Ký số bảo mật)
         │
         ▼
Staging Environment Testing (Kiểm thử tải & Workload)
         │
         ▼
Canary Compute Node Deployment (Phát hành thử nghiệm 1%)
         │
         ▼
Wave Rollout Execution (1% -> 10% -> 50% -> 100%)
         │
         ├───> Continuous Observability & Metrics Alerting
         │
         ▼
Fleet-wide Patch Active (Phủ sóng toàn hạ tầng)
         │
         ▼
Cumulative Patch Replacement / Planned Maintenance Reboot
```

---

## 1. Production pipeline và phân tách trách nhiệm

Triển khai Livepatch trong môi trường Production **không phải là việc gõ lệnh `kpatch load` thủ công**. Đó là một **Quy trình phân tầng nghiêm ngặt (Production Pipeline)** với sự phân tách trách nhiệm (Role Separation) rõ ràng giữa các bộ phận:

```text
                      PHÂN TÁCH TRÁCH NHIỆM TRONG PRODUCTION
                                         │
     ┌───────────────────────────────────┼───────────────────────────────────┐
     ▼                                   ▼                                   ▼
 1. KERNEL ENGINEERING TEAM          2. PLATFORM / SRE TEAM              3. SECURITY TEAM
 - Phân tích Upstream Fix.           - Xác định danh sách Target Hosts.  - Đánh giá mức độ ưu tiên CVE.
 - Đánh giá Patchability Gate.       - Quản lý Canary & Wave Rollout.    - Đặt deadline khắc phục.
 - Biên dịch Reproducible Build.     - Theo dõi Metrics & Alerting.      - Quản lý PKCS#7 Signing Keys.
 - Tạo Artifact & Ký số PKCS#7.      - Thực hiện Rollback / Unload.      - Audit compliance báo cáo.
```

---

## 2. Quản lý artifact identity và compatibility matrix

### 2.1. Định danh nhị phân (Artifact Identity)

Mỗi file Livepatch Module (`.ko`) khi build ra phải đi kèm một bản ghi định danh tĩnh (Metadata File):

```text
┌────────────────────────────────────────────────────────┐
│               LIVEPATCH ARTIFACT METADATA             │
├────────────────────────────────────────────────────────┤
│ Patch ID:         patch-kvm-mmu-2026-01                │
│ CVE Reference:    CVE-2026-XXXX                        │
│ Target Release:   6.8.0-134-generic                      │
│ Target Arch:      x86_64                               │
│ SHA256 Hash:      e3b0c44298fc1c149afbf4c8996fb92427ae │
│ Changed Funcs:    kvm_mmu_zap_page, kpatch_child_sp    │
│ Build Toolchain:  gcc-13.2.0 | kpatch-build 0.9.9       │
│ Signature Status: Signed via PKCS#7 Enterprise Cert    │
└────────────────────────────────────────────────────────┘
```

### 2.2. Ma trận tương thích (Compatibility Matrix)

Tuyệt đối **không được áp dụng một file `.ko` cho các máy chủ khác Kernel Release** dù chỉ lệch một số bản vá nhỏ.

| Patch Artifact ID | Target Kernel Release | Architecture | Target Config | Approval Status |
|---|---|---|---|---|
| **P-2026-01-A** | `6.8.0-134-generic` | x86_64 | Ubuntu Prod Standard | **APPROVED (Đã duyệt)** |
| **P-2026-01-B** | `6.8.0-138-generic` | x86_64 | Ubuntu Prod Standard | **REBUILD REQUIRED (Bắt buộc build lại)** |

---

## 3. Staging, canary và wave rollout

```text
                     QUY TRÌNH PHÁT HÀNH PHÂN TẦNG (PROGRESSIVE ROLLOUT)
                                              │
    ┌───────────────────┬─────────────────────┼─────────────────────┬───────────────────┐
    ▼                   ▼                     ▼                     ▼                   ▼
1. STAGING ENV     2. CANARY NODE        3. WAVE 1 (10%)       4. WAVE 2 (50%)     5. FLEET (100%)
- Giả lập tải      - Chọn 1-2 compute    - Mở rộng 10% host    - Mở rộng 50% host  - Phủ sóng toàn
  stress KVM         node đại diện        - Soak time: 12h      - Soak time: 24h      bộ hạ tầng
- Test load/unload - Soak time: 4h
```

### 3.1. Môi trường Staging (Staging Environment)
- Staging phải mô phỏng lại đúng các tình huống tải thực tế: Tạo/xóa máy ảo, ép CPU/Memory stress (`stress-ng`), gửi traffic mạng lớn (`iperf3`), và thử nghiệm các tình huống ép kẹt Transition (Stall Scenario) để kiểm tra tính an toàn.

### 3.2. Triển khai Canary (Canary Deployment)
- Chọn một vài Compute Nodes đại diện có tải thật nhưng **Blast Radius (Bán kính tác động sự cố)** thấp.
- Tiêu chí đánh giá Canary Gate:
  ```text
  [ ] Trạng thái transition = 0 hoàn tất trong vòng < 60 giây.
  [ ] Không ghi nhận lỗi Oops, BUG, hay Panic trong dmesg.
  [ ] Chỉ số độ trễ (Latency SLO) của các máy ảo Guest giữ mức ổn định.
  ```

### 3.3. Phát hành theo làn sóng (Wave Rollout)
- Tiến hành triển khai theo các tỷ lệ tăng dần: `1 Node -> 1% -> 10% -> 50% -> 100%`.
- Giữa mỗi đợt Wave phải có thời gian ngâm tải (**Soak Time**) tối thiểu từ 4h đến 24h. Nếu phát hiện bất kỳ cảnh báo nào, tự động dừng (Automatic Stop Condition) quy trình triển khai.

---

## 4. Metrics, alerting và rollback policy

### 4.1. Các chỉ số quan trọng cần theo dõi (Key Operational Metrics)

```text
                           CÁC CHỈ SỐ THEO DÕI TẬP TRUNG
                                         │
    ┌───────────────────────────┬────────┴───────────────────────────┐
    ▼                           ▼                                   ▼
1. METRICS LIVEPATCH        2. METRICS HOST COMPUTE             3. METRICS WORKLOAD / VM
- Thời gian Transition (s).  - CPU Utilization & Run Queue.      - Packet Loss Rate (%).
- Số Task kẹt patch_state.  - Memory Pressure / Swap.           - Storage IOPS & Latency (ms).
- Số lần gửi Signal Kick.   - Tỷ lệ lỗi dmesg / Kernel Error.   - Tỷ lệ VM Crash / Reset.
```

### 4.2. Chính sách Hủy bỏ / Khôi phục (Rollback Policy)

```text
                         PHÂN LOẠI KỊCH BẢN ROLLBACK
                                      │
     ┌────────────────────────────────┼────────────────────────────────┐
     ▼                                ▼                                ▼
1. SỰ CỐ TRANSITION STALL      2. LỖI LOGIC BẢN VÁ (ANOMALY)    3. ĐÃ DÙNG FORCE TRANSITION
- Thực hiện `kpatch unload`.   - Kích hoạt `kpatch unload`.     - BẮT BUỘC Live Migrate VMs
- Trở về mã cũ an toàn.        - Quay về baseline ban đầu.      - Reboot Host trong kỳ bảo trì!
```

---

## 5. Vòng đời dài hạn: reboot debt, cumulative patch, signing và change control

### 5.1. Nợ kỹ thuật do hoãn Reboot (Reboot Debt)

> **Reboot Debt (Nợ Reboot):** Livepatch giúp hoãn thời điểm Reboot máy chủ để duy trì Uptime, nhưng **không thể thay thế hoàn toàn việc Reboot**.

Nếu một máy chủ bị nạp chồng chéo quá nhiều Livepatch Modules lẻ (P1 + P2 + P3...):
- Độ phức tạp khi chẩn đoán lỗi tăng theo cấp số nhân.
- Khả năng tương thích giữa các patch module lẻ trở nên khó kiểm soát.

**Chính sách quản trị Reboot Debt:** Cần quy định số lượng Livepatch tối đa (ví dụ tối đa 5 patches), hoặc sau mỗi 6 tháng bắt buộc phải đăng ký cửa sổ bảo trì để Reboot máy chủ về Kernel gốc sạch (**Clean Baseline Kernel**).

```text
                      QUẢN TRỊ NỢ REBOOT (REBOOT DEBT MANAGEMENT)

 Kernel gốc ──> Livepatch P1 ──> Livepatch P2 ──> Livepatch P3 ──> [ĐẠT NGƯỠNG NỢ] ──> Reboot Baseline sạch
```

### 5.2. Bản vá tích lũy (Cumulative Patch Strategy)

Thay vì nạp nhiều module lẻ P1, P2, P3 độc lập, nhà phát triển nên đóng gói bản vá mới dưới dạng **Cumulative Patch (P_Cumulative = P1 + P2 + P3)** để nạp thay thế (`replace = 1`) toàn bộ các patch cũ chỉ trong 1 thao tác Transition duy nhất.

### 5.3. Bảo mật chuỗi cung ứng & Ký số (Module Signing & Supply Chain Security)

Trên môi trường Production, Kernel phải bật cờ bắt buộc kiểm tra chữ ký số (`CONFIG_MODULE_SIG_FORCE`). Mọi Livepatch Module trước khi đẩy vào pipeline triển khai bắt buộc phải được ký bằng khóa riêng (**PKCS#7 Enterprise Private Key**).

---

## 6. Decision matrix, Go/No-Go và governance/audit

### Ma trận quyết định: Livepatch vs Live Migrate + Reboot

| Tiêu chí kỹ thuật | Chọn Livepatch (`kpatch`) | Chọn Live Migrate + Reboot Host |
|---|---|---|
| **Phạm vi sửa đổi** | Thay đổi logic hàm cục bộ | Thay đổi Struct Layout / ABI lớn |
| **Tính khả vá (Patchability)** | Đạt Patchability Gate | Không đạt Patchability Gate |
| **Độ ưu tiên Uptime** | Cực kỳ cao (Zero Downtime) | Chấp nhận được chuyển vùng VM |
| **Mức độ tích tụ Livepatch** | Ít patch lẻ (Nợ Reboot thấp) | Đã tích tụ quá nhiều patch lẻ |

---

### Quy trình kiểm toán Go / No-Go trước khi triển khai (Production Gate)

```text
┌────────────────────────────────────────────────────────┐
│            PRODUCTION GO / NO-GO CHECKLIST             │
├────────────────────────────────────────────────────────┤
│ [ ] 1. SOURCE: Bản vá đã được Human Review kỹ lưỡng.  │
│ [ ] 2. BUILD: Artifact được build từ đúng vmlinux/ver. │
│ [ ] 3. SIGNING: Module đã được ký số PKCS#7 hợp lệ.    │
│ [ ] 4. STAGING: Kiểm thử nạp/gỡ thành công trên tải.   │
│ [ ] 5. CANARY: Triển khai thành công 1% không lỗi SLO. │
│ [ ] 6. ROLLBACK: Kịch bản unload đã sẵn sàng 100%.     │
└────────────────────────────────────────────────────────┘
```

---

### 10 Câu hỏi Kiểm toán Kiến trúc dành cho Mentor / Reviewer:

1. Bản vá này sửa đổi chính xác logic hoặc điều kiện an toàn (Invariant) nào?
2. Vì sao bản vá này đảm bảo tính khả vá (Livepatch-safe)?
3. Những hàm nào thực sự bị thay đổi mã máy nhị phân (`Changed Functions`)?
4. Đơn vị sở hữu hàm bị vá là `vmlinux` hay một Kernel Module cụ thể?
5. Phiên bản `uname -r` và `vermagic` của Kernel Target chính xác là gì?
6. Quá trình Transition sử dụng mô hình nhất quán nào?
7. Nếu xuất hiện Task bị kẹt (Stall), quy trình tìm vết Callstack thực hiện ra sao?
8. Hậu quả kỹ thuật nghiêm trọng nào xảy ra nếu sử dụng cờ `force = 1`?
9. Chỉ số SLO của máy ảo Guest được đo lường bằng những Metrics cụ thể nào?
10. Khi nào hệ thống bắt buộc phải từ bỏ Livepatch để chuyển sang phương án Reboot?

---

## 7. Tài liệu tham khảo

- [kpatch Production Deployment Guide](https://github.com/dynup/kpatch)
- [Linux Kernel Livepatch Architecture & Signing](https://docs.kernel.org/livepatch/livepatch.html)
- [Red Hat Enterprise Linux Live Kernel Patching Guide](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/)
