#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <time.h>
#include <poll.h>
#include <sys/ptrace.h>
#include <sys/wait.h>
#include <sys/user.h>
#include <sys/syscall.h>
#include <sys/ioctl.h>
#include <linux/userfaultfd.h>

#ifndef __NR_pidfd_open
#define __NR_pidfd_open 434
#endif
#ifndef __NR_pidfd_getfd
#define __NR_pidfd_getfd 438
#endif

// Helper: read memory from tracee
static int read_mem(pid_t pid, unsigned long addr, void *buf, size_t len) {
    size_t count = 0;
    while (count < len) {
        errno = 0;
        long data = ptrace(PTRACE_PEEKDATA, pid, (void *)(addr + count), NULL);
        if (errno != 0) return -1;
        size_t chunk = sizeof(long);
        if (len - count < chunk) chunk = len - count;
        memcpy((char *)buf + count, &data, chunk);
        count += sizeof(long);
    }
    return 0;
}

// Helper: write memory to tracee
static int write_mem(pid_t pid, unsigned long addr, const void *buf, size_t len) {
    size_t count = 0;
    while (count < len) {
        long data = 0;
        size_t chunk = sizeof(long);
        if (len - count < chunk) {
            data = ptrace(PTRACE_PEEKDATA, pid, (void *)(addr + count), NULL);
            chunk = len - count;
        }
        memcpy(&data, (const char *)buf + count, chunk);
        if (ptrace(PTRACE_POKEDATA, pid, (void *)(addr + count), (void *)data) < 0)
            return -1;
        count += sizeof(long);
    }
    return 0;
}

// Helper: remote syscall via ptrace
static long remote_syscall(pid_t pid, long sys_no,
                           unsigned long arg1, unsigned long arg2,
                           unsigned long arg3, unsigned long arg4,
                           unsigned long arg5, unsigned long arg6) {
    struct user_regs_struct orig_regs, regs;
    if (ptrace(PTRACE_GETREGS, pid, NULL, &orig_regs) < 0) {
        perror("PTRACE_GETREGS");
        return -1;
    }

    regs = orig_regs;
    regs.rax = sys_no;
    regs.rdi = arg1;
    regs.rsi = arg2;
    regs.rdx = arg3;
    regs.r10 = arg4;
    regs.r8  = arg5;
    regs.r9  = arg6;

    // Place syscall instruction (0x0f, 0x05) at rip
    unsigned long orig_code;
    read_mem(pid, regs.rip, &orig_code, sizeof(orig_code));
    unsigned short syscall_code = 0x050f;
    write_mem(pid, regs.rip, &syscall_code, 2);

    if (ptrace(PTRACE_SETREGS, pid, NULL, &regs) < 0) {
        perror("PTRACE_SETREGS");
        write_mem(pid, orig_regs.rip, &orig_code, sizeof(orig_code));
        return -1;
    }

    // Step once to execute syscall
    if (ptrace(PTRACE_SINGLESTEP, pid, NULL, NULL) < 0) {
        perror("PTRACE_SINGLESTEP");
        write_mem(pid, orig_regs.rip, &orig_code, sizeof(orig_code));
        return -1;
    }

    int status;
    waitpid(pid, &status, 0);

    struct user_regs_struct res_regs;
    ptrace(PTRACE_GETREGS, pid, NULL, &res_regs);
    long ret = (long)res_regs.rax;

    // Restore original code and registers
    write_mem(pid, orig_regs.rip, &orig_code, sizeof(orig_code));
    ptrace(PTRACE_SETREGS, pid, NULL, &orig_regs);

    return ret;
}

int main(int argc, char *argv[]) {
    if (argc < 4) {
        fprintf(stderr, "Usage: %s <qemu_pid> <target_hva_hex> <hold_seconds>\n", argv[0]);
        return 1;
    }

    pid_t qemu_pid = atoi(argv[1]);
    unsigned long target_hva = strtoul(argv[2], NULL, 16);
    int hold_sec = atoi(argv[3]);

    printf("=== USERFAULTFD INJECTOR ===\n");
    printf("Target QEMU PID: %d\n", qemu_pid);
    printf("Target HVA:      0x%lx\n", target_hva);
    printf("Hold Duration:   %d seconds\n", hold_sec);

    // Step 1: Attach to QEMU via ptrace
    printf("[1] Attaching to QEMU PID %d...\n", qemu_pid);
    if (ptrace(PTRACE_ATTACH, qemu_pid, NULL, NULL) < 0) {
        perror("PTRACE_ATTACH");
        return 1;
    }
    int status;
    waitpid(qemu_pid, &status, 0);
    printf("[1] Attached successfully.\n");

    // Step 2: Call syscall(userfaultfd, O_CLOEXEC | O_NONBLOCK) in QEMU
    long qemu_uffd = remote_syscall(qemu_pid, SYS_userfaultfd, O_CLOEXEC | O_NONBLOCK, 0, 0, 0, 0, 0);
    if (qemu_uffd < 0) {
        fprintf(stderr, "userfaultfd failed in QEMU: %ld (%s)\n", qemu_uffd, strerror(-qemu_uffd));
        ptrace(PTRACE_DETACH, qemu_pid, NULL, NULL);
        return 1;
    }
    printf("[2] userfaultfd() in QEMU created fd = %ld\n", qemu_uffd);

    // Step 3: Setup scratch space on QEMU's stack for ioctl structs
    struct user_regs_struct regs;
    ptrace(PTRACE_GETREGS, qemu_pid, NULL, &regs);
    unsigned long scratch_rsp = regs.rsp - 512;

    struct uffdio_api api;
    memset(&api, 0, sizeof(api));
    api.api = UFFD_API;
    api.features = 0;
    write_mem(qemu_pid, scratch_rsp, &api, sizeof(api));

    long r_api = remote_syscall(qemu_pid, SYS_ioctl, qemu_uffd, UFFDIO_API, scratch_rsp, 0, 0, 0);
    if (r_api < 0) {
        fprintf(stderr, "UFFDIO_API handshake failed in QEMU: %ld (%s)\n", r_api, strerror(-r_api));
        ptrace(PTRACE_DETACH, qemu_pid, NULL, NULL);
        return 1;
    }
    printf("[3] UFFDIO_API handshake succeeded in QEMU.\n");

    // Target single 4KB page
    size_t page_len = 4096;

    // Evict page in target address so subsequent access triggers fault
    printf("[3b] Calling madvise(MADV_DONTNEED) in QEMU for 4KB page 0x%lx...\n", target_hva);
    long r_madv = remote_syscall(qemu_pid, SYS_madvise, target_hva, page_len, 4 /* MADV_DONTNEED */, 0, 0, 0);
    if (r_madv < 0) {
        fprintf(stderr, "madvise failed in QEMU: %ld\n", r_madv);
    }

    struct uffdio_register reg;
    memset(&reg, 0, sizeof(reg));
    reg.range.start = target_hva;
    reg.range.len = page_len; // Exactly 4KB
    reg.mode = UFFDIO_REGISTER_MODE_MISSING;
    write_mem(qemu_pid, scratch_rsp, &reg, sizeof(reg));

    long r_reg = remote_syscall(qemu_pid, SYS_ioctl, qemu_uffd, UFFDIO_REGISTER, scratch_rsp, 0, 0, 0);
    if (r_reg < 0) {
        fprintf(stderr, "UFFDIO_REGISTER failed on 0x%lx: %ld (%s)\n", target_hva, r_reg, strerror(-r_reg));
        ptrace(PTRACE_DETACH, qemu_pid, NULL, NULL);
        return 1;
    }
    printf("[4] UFFDIO_REGISTER registered 4KB page 0x%lx in QEMU.\n", target_hva);

    // Step 5: Duplicate qemu_uffd to our process via pidfd_getfd
    int pfd = syscall(__NR_pidfd_open, qemu_pid, 0);
    int our_uffd = syscall(__NR_pidfd_getfd, pfd, qemu_uffd, 0);
    close(pfd);
    if (our_uffd < 0) {
        perror("pidfd_getfd");
        ptrace(PTRACE_DETACH, qemu_pid, NULL, NULL);
        return 1;
    }
    printf("[5] Duplicated userfaultfd into controller process as fd = %d\n", our_uffd);

    // Close in QEMU so QEMU doesn't leak fd
    remote_syscall(qemu_pid, SYS_close, qemu_uffd, 0, 0, 0, 0, 0);

    // Step 6: Detach from QEMU
    printf("[6] Detaching from QEMU...\n");
    ptrace(PTRACE_DETACH, qemu_pid, NULL, NULL);
    printf("[6] QEMU resumed normal execution.\n");

    printf("\n>>> USERFAULTFD ACTIVE. WAITING FOR PAGE FAULT ON 0x%lx <<<\n", target_hva);
    fflush(stdout);

    // Persistent Hold Loop: does NOT resolve on early signals/retries
    struct pollfd pfd_poll = { .fd = our_uffd, .events = POLLIN };
    time_t t_start = 0;
    int fault_count = 0;
    int last_printed = 0;

    while (1) {
        int pr = poll(&pfd_poll, 1, 1000); // 1s timeout
        time_t now = time(NULL);

        // Check if hold duration elapsed
        if (t_start > 0 && (now - t_start >= hold_sec)) {
            printf("\n[HOLD COMPLETED] %d seconds elapsed. Resolving page fault with zeropage...\n", hold_sec);
            struct uffdio_zeropage zp;
            memset(&zp, 0, sizeof(zp));
            zp.range.start = target_hva;
            zp.range.len = 4096;
            zp.mode = 0;
            if (ioctl(our_uffd, UFFDIO_ZEROPAGE, &zp) < 0) {
                perror("UFFDIO_ZEROPAGE");
            } else {
                printf("Page fault resolved successfully.\n");
            }
            break;
        }

        if (pr > 0 && (pfd_poll.revents & POLLIN)) {
            struct uffd_msg msg;
            ssize_t n = read(our_uffd, &msg, sizeof(msg));
            if (n > 0 && msg.event == UFFD_EVENT_PAGEFAULT) {
                fault_count++;
                if (t_start == 0) {
                    t_start = time(NULL);
                    printf("\n[!!! EVENT: UFFD_PAGEFAULT_TRIGGERED !!!]\n");
                    printf("Fault Address HVA: 0x%lx\n", (unsigned long)msg.arg.pagefault.address);
                    printf("HOLDING vCPU IN direct_page_fault FOR %d SECONDS...\n", hold_sec);
                    fflush(stdout);
                } else {
                    printf("  -> Re-fault #%d caught during hold (vCPU re-entered direct_page_fault)\n", fault_count);
                    fflush(stdout);
                }
            }
        }

        if (t_start > 0) {
            int elapsed = (int)(now - t_start);
            if (elapsed != last_printed && (elapsed % 5 == 0 || elapsed == 75)) {
                printf("  -> Real wall-clock held duration: %d / %d seconds...\n", elapsed, hold_sec);
                fflush(stdout);
                last_printed = elapsed;
            }
        }
    }

    close(our_uffd);
    printf("=== USERFAULTFD STALLER FINISHED ===\n");
    return 0;
}
