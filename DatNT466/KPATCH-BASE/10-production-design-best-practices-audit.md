# 10 – Production design, best practices và audit

## Mục lục

1. [1. Production pipeline và phân tách trách nhiệm](#1-production-pipeline-và-phân-tách-trách-nhiệm)
2. [2. Quản lý artifact identity và compatibility matrix](#2-quản-lý-artifact-identity-và-compatibility-matrix)
3. [3. Staging, canary và wave rollout](#3-staging-canary-và-wave-rollout)
4. [4. Metrics, alerting và rollback policy](#4-metrics-alerting-và-rollback-policy)
5. [5. Vòng đời dài hạn: reboot debt, cumulative patch, signing và change control](#5-vòng-đời-dài-hạn-reboot-debt-cumulative-patch-signing-và-change-control)
6. [6. Decision matrix, Go/No-Go và governance/audit](#6-decision-matrix-gono-go-và-governanceaudit)
7. [7. Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

## Vòng đời livepatch trong production

```text
CVE / BUG FIX
     |
     v
Patch engineering review
     |
     v
Patchability + artifact build
     |
     v
Static/binary validation
     |
     v
Staging + workload test
     |
     v
Canary compute node
     |
     v
Wave rollout
     |
     +--> metrics / alerts / rollback
     |
     v
Fleet coverage
     |
     v
Patch retirement / cumulative patch / planned reboot
```

## 1. Production pipeline và phân tách trách nhiệm

**Livepatch production là một pipeline, không phải một lệnh**

```text
CVE/fix
  ↓
source analysis
  ↓
patchability review
  ↓
reproducible build
  ↓
artifact validation/signing
  ↓
staging
  ↓
canary
  ↓
wave rollout
  ↓
continuous observation
  ↓
cumulative patch / planned reboot retirement
```

---

**Role separation**

**Kernel/Patch engineering**

- hiểu upstream fix;
- redesign patch nếu cần;
- review struct/data/locking;
- build artifact.

**Platform/SRE**

- host eligibility;
- canary/rollout;
- metrics;
- transition monitoring;
- rollback/fallback.

**Security**

- CVE priority;
- deadline;
- risk acceptance;
- signing/audit requirements.

---

## 2. Quản lý artifact identity và compatibility matrix

**Artifact identity**

Mỗi patch phải có metadata tối thiểu:

```text
Patch ID
CVE/bug ID
Source commit(s)
Target distro/kernel package
Kernel release/vermagic
Architecture
Build tool version
Compiler/binutils
Changed functions
Artifact hash
Signature status
Owner/reviewer
```

---

**Compatibility matrix**

Không deploy theo “major/minor giống nhau”. Dùng exact target matrix:

| Patch | Distro kernel | Arch | Config/ABI | Status |
|---|---|---|---|---|
| P1 | 6.8.0-134.134 generic | x86_64 | exact | approved |
| P1 | 6.8.0-138.x | x86_64 | khác | rebuild/review |

---

## 3. Staging, canary và wave rollout

**Staging strategy**

Staging phải exercise code path bị patch, không chỉ “server boot được”.

KVM patch cần test tùy relevance:

- VM create/destroy;
- CPU load;
- memory pressure;
- network/storage I/O;
- pause/resume;
- migration nếu platform dùng;
- nested virtualization nếu production có;
- load/unload transition;
- deliberate stall scenario nếu hot path.

---

**Canary**

Không rollout toàn fleet ngay sau staging.

Canary chọn host đại diện:

```text
same kernel
same CPU generation
same VM density/workload class
good observability
low blast radius
```

Canary gate:

```text
transition=0
no kernel errors
VM SLO normal
no unexpected task stall
```

---

**Wave rollout**

Ví dụ:

```text
1 host
 ↓
1% fleet
 ↓
10%
 ↓
25%
 ↓
50%
 ↓
100%
```

Giữa wave có soak time và automatic stop condition.

---

## 4. Metrics, alerting và rollback policy

**Metrics cần theo dõi**

**Livepatch**

- transition duration;
- number of blockers;
- signaling remaining tasks event;
- load/unload failure;
- patch count/stack depth.

**Host**

- CPU/run queue;
- memory pressure;
- kernel error rate;
- network/storage latency.

**VM/SLO**

- packet loss;
- latency percentile;
- throughput;
- VM pause/reset/crash;
- application health.

---

**Alert conditions**

```text
transition > threshold
kernel Oops/BUG/panic
VM error spike
latency > SLO
patch_state blockers không giảm
artifact mismatch
unexpected kernel taint/policy failure
```

Threshold phải dựa trên environment baseline, không hard-code từ lab.

---

**Rollback policy**

Rollback không đơn giản “rmmod”.

Phải phân biệt:

```text
normal unload
reverse transition stalled
patch semantic bug
force đã dùng
```

Nếu force đã dùng, reboot plan trở thành priority.

---

## 5. Vòng đời dài hạn: reboot debt, cumulative patch, signing và change control

**Reboot debt**

Livepatch giúp trì hoãn reboot, không loại bỏ nhu cầu reboot mãi mãi.

Càng stack nhiều runtime patches:

- reasoning khó hơn;
- audit phức tạp;
- test combinatorial tăng;
- divergence khỏi clean vendor kernel tăng.

Nên có policy kiểu:

```text
sau N patch / maintenance window / critical cumulative update → reboot về clean baseline
```

---

**Cumulative patch strategy**

Thay vì stack P1 + P2 + P3 độc lập, ưu tiên cumulative replacement khi tooling/kernel hỗ trợ và patch author review xác nhận.

---

**Signing và supply chain**

Production artifact phải có:

- controlled build environment;
- source provenance;
- artifact hash;
- signing key policy;
- access control;
- immutable storage;
- audit log deploy/unload.

Lab warning “module verification failed” không nên được xem là production norm.

---

**Change control**

Mỗi rollout cần change record:

```text
WHY: CVE/impact
WHAT: functions changed
WHERE: host pool/kernel
WHEN: window
WHO: approver/operator
HOW: commands/automation
ROLLBACK: unload/reverse/fallback
EVIDENCE: logs/metrics
```

---

## 6. Decision matrix, Go/No-Go và governance/audit

**Decision matrix: livepatch vs migrate+reboot**

| Điều kiện | Livepatch | Migrate + reboot |
|---|---|---|
| Localized function fix | Ưu tiên xem xét | vẫn khả thi |
| Struct/ABI deep change | thường no-go | phù hợp hơn |
| Exact artifact chưa build được | không | cần update path khác |
| Critical uptime | mạnh | tốn migration |
| Force required nhưng risk cao | tránh | fallback tốt |
| Kernel patch stack quá sâu | giảm ưu tiên | clean baseline |

---

**Production Go/No-Go gate**

```text
SOURCE
[ ] fix understood
[ ] data/locking semantics reviewed

BUILD
[ ] exact target
[ ] changed functions expected
[ ] artifact signed

STAGING
[ ] relevant workload
[ ] load + unload tested
[ ] stall/recovery tested nếu cần

CANARY
[ ] transition complete
[ ] VM SLO healthy
[ ] no kernel anomaly

ROLLOUT
[ ] waves + soak
[ ] stop condition configured

RETIREMENT
[ ] cumulative/reboot plan
```

---

**Audit questions cho mentor/team**

1. Patch này fix chính xác invariant nào?
2. Vì sao livepatch-safe?
3. Function nào thực sự bị thay trong binary?
4. Object owner là `vmlinux` hay module nào?
5. Exact target kernel là gì?
6. Transition sử dụng consistency model nào?
7. Nếu task stall, tìm nó ở đâu?
8. Force có hậu quả gì?
9. VM SLO được đo bằng metric nào?
10. Khi nào bỏ livepatch và migrate/reboot?

Nếu chưa trả lời được, chưa nên coi quy trình production-ready.

---

**Mô hình governance cuối cùng**

```text
Livepatch không phải “tránh reboot bằng mọi giá”.

Mục tiêu đúng:
Security fix
   +
Consistency
   +
Availability
   +
Auditability
```

Nếu livepatch không thỏa cả bốn, fallback maintenance workflow là quyết định engineering đúng.

---

## 7. Tài liệu tham khảo

- https://github.com/dynup/kpatch
- https://docs.kernel.org/livepatch/livepatch.html
- https://docs.redhat.com/
