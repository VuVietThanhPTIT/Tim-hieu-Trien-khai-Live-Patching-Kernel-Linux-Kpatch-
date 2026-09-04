#!/usr/bin/env python3
"""Recover a pending Linux livepatch transition owned by libvirt QEMU guests.

The program intentionally uses only the Python standard library and executes
commands without a shell.  Run it as root on the KVM host so that it can read
per-task ``patch_state`` files and operate libvirt domains.  The recovery
trigger is a policy threshold; it is not itself proof of a 75-second stall.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, TextIO, Tuple


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_LOAD_FAILED = 3
EXIT_TRANSITION_MISSED = 4
EXIT_NO_DOMAIN_BLOCKER = 5
EXIT_RECOVERY_FAILED = 6
EXIT_VERIFY_FAILED = 7
EXIT_TIMEOUT = 8
EXIT_INTERRUPTED = 130

RECOVERY_METHODS = ("wait", "signal", "throttle", "suspend-resume", "force")
DEFAULT_CASCADE = ("signal", "suspend-resume")


class RecoveryError(RuntimeError):
    """A controlled failure carrying the program exit code and result name."""

    def __init__(self, result: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.result = result
        self.exit_code = exit_code


@dataclass(frozen=True)
class CommandResult:
    argv: Tuple[str, ...]
    returncode: int
    stdout: str
    duration_seconds: float
    timed_out: bool = False
    interrupted: bool = False


@dataclass(frozen=True)
class PendingTask:
    pid: int
    tid: int
    patch_state: int
    comm: str
    qemu_pid: Optional[int]
    domain: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "tid": self.tid,
            "patch_state": self.patch_state,
            "comm": self.comm,
            "qemu_pid": self.qemu_pid,
            "domain": self.domain,
        }


class EventLogger:
    """Emit evidence to stdout and, optionally, mirror one execution to a log file."""

    def __init__(self, output_format: str, log_path: Optional[Path]) -> None:
        self.output_format = output_format
        self.started = time.monotonic()
        self._file: Optional[TextIO] = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = log_path.open("w", encoding="utf-8", buffering=1)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()

    def _write(self, line: str) -> None:
        print(line, flush=True)
        if self._file is not None:
            self._file.write(line + "\n")

    def event(self, event: str, level: str = "INFO", **fields: Any) -> None:
        record: Dict[str, Any] = {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "level": level,
            "event": event,
        }
        record.update(fields)
        if self.output_format in ("human", "both"):
            details = " ".join(
                f"{key}={json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
                for key, value in fields.items()
            )
            self._write(f"# [{record['timestamp_utc']}] {level} {event}" + (f" {details}" if details else ""))
        if self.output_format in ("jsonl", "both"):
            self._write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))


class CommandRunner:
    """Run argv directly, enforcing command and global deadlines."""

    def __init__(self, logger: EventLogger, stop_event: threading.Event, global_deadline: float) -> None:
        self.logger = logger
        self.stop_event = stop_event
        self.global_deadline = global_deadline

    def remaining(self) -> float:
        return self.global_deadline - time.monotonic()

    def run(
        self,
        argv: Sequence[str],
        timeout: float,
        *,
        log_event: str = "command",
        acceptable_codes: Iterable[int] = (0,),
        safety_critical: bool = False,
    ) -> CommandResult:
        if self.remaining() <= 0 and not safety_critical:
            raise RecoveryError("total_timeout", "Total timeout expired before command execution", EXIT_TIMEOUT)
        # Resume is availability cleanup. It must still be attempted after a
        # signal or an expired global deadline, within its own command timeout.
        effective_timeout = timeout if safety_critical else min(timeout, self.remaining())
        command = tuple(str(item) for item in argv)
        started = time.monotonic()
        env = os.environ.copy()
        env.update({"LC_ALL": "C", "LANG": "C"})
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except OSError as exc:
            result = CommandResult(command, 127, str(exc), time.monotonic() - started)
            self.logger.event(log_event, "ERROR", argv=list(command), returncode=127, output=str(exc))
            return result

        output = ""
        timed_out = False
        interrupted = False
        while True:
            if self.stop_event.is_set() and not safety_critical:
                interrupted = True
                process.terminate()
            elapsed = time.monotonic() - started
            if elapsed >= effective_timeout:
                timed_out = True
                process.terminate()
            try:
                chunk, _ = process.communicate(timeout=0.2)
                output += chunk or ""
                break
            except subprocess.TimeoutExpired:
                if timed_out or interrupted:
                    try:
                        chunk, _ = process.communicate(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        chunk, _ = process.communicate()
                    output += chunk or ""
                    break

        result = CommandResult(
            command,
            int(process.returncode),
            output.strip(),
            time.monotonic() - started,
            timed_out,
            interrupted,
        )
        level = "INFO" if result.returncode in set(acceptable_codes) and not timed_out and not interrupted else "ERROR"
        self.logger.event(
            log_event,
            level,
            argv=list(command),
            returncode=result.returncode,
            duration_seconds=round(result.duration_seconds, 3),
            timed_out=timed_out,
            interrupted=interrupted,
            output=result.stdout,
        )
        return result


class RecoveryController:
    def __init__(self, args: argparse.Namespace, logger: EventLogger, stop_event: threading.Event) -> None:
        self.args = args
        self.logger = logger
        self.stop_event = stop_event
        self.global_deadline = time.monotonic() + args.total_timeout
        self.commands = CommandRunner(logger, stop_event, self.global_deadline)
        self.livepatch_root = Path(args.livepatch_root)
        self.proc_root = Path(args.proc_root)
        self.patch_name: Optional[str] = args.patch_name
        self.transition_seen = False
        self.transition_first_seen_at: Optional[float] = None
        self.qemu_domain_cache: Dict[int, Optional[str]] = {}
        self.recovered_domains: List[str] = []
        self.affected_domains: List[str] = []
        self.recovery_steps_attempted: List[str] = []
        self.completion_observed_during: Optional[str] = None

    def recovery_plan(self) -> List[str]:
        if self.args.strategy == "cascade":
            return list(self.args.cascade_order)
        return [self.args.strategy]

    def check_stop(self) -> None:
        if self.stop_event.is_set():
            raise RecoveryError("interrupted", "Interrupted by signal", EXIT_INTERRUPTED)
        if time.monotonic() >= self.global_deadline:
            raise RecoveryError("total_timeout", "Total timeout expired", EXIT_TIMEOUT)

    def _virsh_argv(self, *arguments: str) -> List[str]:
        argv = [self.args.virsh]
        if self.args.connect:
            argv.extend(["--connect", self.args.connect])
        argv.extend(arguments)
        return argv

    @staticmethod
    def _read_text(path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8", errors="replace").strip()
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            return None

    def _read_int(self, path: Path) -> Optional[int]:
        value = self._read_text(path)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _valid_patch_name(name: str) -> bool:
        return bool(name) and Path(name).name == name and "/" not in name and "\\" not in name

    def _patch_dirs(self) -> Set[str]:
        try:
            return {entry.name for entry in self.livepatch_root.iterdir() if entry.is_dir()}
        except (FileNotFoundError, PermissionError, OSError):
            return set()

    def _choose_patch(self, before: Set[str]) -> Optional[str]:
        if self.patch_name:
            return self.patch_name if (self.livepatch_root / self.patch_name).is_dir() else None
        current = self._patch_dirs()
        new_names = sorted(current - before)
        if len(new_names) == 1:
            self.patch_name = new_names[0]
            self.logger.event("patch_discovered", patch_name=self.patch_name, method="new_sysfs_directory")
            return self.patch_name
        transitioning = [name for name in sorted(current) if self._read_int(self.livepatch_root / name / "transition") == 1]
        if len(transitioning) == 1:
            self.patch_name = transitioning[0]
            self.logger.event("patch_discovered", patch_name=self.patch_name, method="only_transitioning_patch")
            return self.patch_name
        return None

    def _state(self) -> Tuple[Optional[int], Optional[int]]:
        if not self.patch_name:
            return None, None
        base = self.livepatch_root / self.patch_name
        return self._read_int(base / "transition"), self._read_int(base / "enabled")

    def _mark_transition_seen(self) -> None:
        self.transition_seen = True
        if self.transition_first_seen_at is None:
            self.transition_first_seen_at = time.monotonic()

    def preflight(self) -> Optional[Path]:
        if os.name != "posix" or not Path("/proc").exists():
            raise RecoveryError("unsupported_platform", "This program must run on the Linux KVM host", EXIT_USAGE)
        if not self.livepatch_root.is_dir():
            raise RecoveryError(
                "livepatch_unavailable",
                f"Livepatch sysfs root is unavailable: {self.livepatch_root}",
                EXIT_USAGE,
            )
        if self.patch_name and not self._valid_patch_name(self.patch_name):
            raise RecoveryError("invalid_patch_name", "--patch-name must be a single sysfs directory name", EXIT_USAGE)
        if not self.args.monitor_only and self.args.expected_enabled != 1:
            raise RecoveryError("invalid_target", "Module load mode requires --expected-enabled 1", EXIT_USAGE)
        if shutil.which(self.args.virsh) is None:
            raise RecoveryError("virsh_not_found", f"Command not found: {self.args.virsh}", EXIT_USAGE)
        if "force" in self.recovery_plan() and not self.args.allow_force:
            raise RecoveryError(
                "force_not_authorized",
                "The force method requires the explicit --allow-force flag",
                EXIT_USAGE,
            )

        module: Optional[Path] = None
        if not self.args.monitor_only:
            if not self.args.module:
                raise RecoveryError("module_required", "--module is required unless --monitor-only is used", EXIT_USAGE)
            module = Path(self.args.module).expanduser().resolve()
            if not module.is_file():
                raise RecoveryError("module_not_found", f"Patch module does not exist: {module}", EXIT_USAGE)
            if shutil.which(self.args.loader) is None:
                raise RecoveryError("loader_not_found", f"Command not found: {self.args.loader}", EXIT_USAGE)
            if Path(self.args.loader).name == "kpatch" or self.args.loader.endswith("/kpatch"):
                raise RecoveryError(
                    "blocking_loader_unsupported",
                    "Use --loader insmod. The kpatch CLI may wait for transition completion and would block recovery at the deadline",
                    EXIT_USAGE,
                )
            actual_sha256 = self._sha256(module)
            if self.args.expected_sha256 and actual_sha256.lower() != self.args.expected_sha256.lower():
                raise RecoveryError(
                    "module_hash_mismatch",
                    f"Expected SHA-256 {self.args.expected_sha256.lower()}, got {actual_sha256.lower()}",
                    EXIT_USAGE,
                )
            self.logger.event(
                "module_identity",
                path=str(module),
                size_bytes=module.stat().st_size,
                sha256=actual_sha256,
                expected_sha256=self.args.expected_sha256,
                hash_verified=bool(self.args.expected_sha256),
                loader=self.args.loader,
            )
        if os.geteuid() != 0 and not (self.args.dry_run and not self.args.monitor_only):
            raise RecoveryError(
                "root_required",
                "Run as root to read every task patch_state and operate blocker domains",
                EXIT_USAGE,
            )
        uname = os.uname()
        self.logger.event(
            "environment",
            hostname=uname.nodename,
            kernel_release=uname.release,
            kernel_version=uname.version,
            machine=uname.machine,
            python=sys.version.split()[0],
            livepatch_root=str(self.livepatch_root),
        )
        self.logger.event(
            "preflight_ok",
            mode="monitor_only" if self.args.monitor_only else "load_and_recover",
            patch_name=self.patch_name,
            deadline_seconds=self.args.deadline,
            total_timeout_seconds=self.args.total_timeout,
            expected_enabled=self.args.expected_enabled,
            strategy=self.args.strategy,
            recovery_plan=self.recovery_plan(),
            recovery_step_timeout_seconds=self.args.recovery_step_timeout,
            dry_run=self.args.dry_run,
        )
        return module

    def load_patch(self, module: Path) -> None:
        before = self._patch_dirs()
        if self.patch_name and self.patch_name in before:
            raise RecoveryError(
                "patch_already_present",
                f"Patch {self.patch_name!r} already exists; use --monitor-only to attach",
                EXIT_LOAD_FAILED,
            )
        argv = [self.args.loader]
        if Path(self.args.loader).name == "kpatch" or self.args.loader.endswith("/kpatch"):
            argv.append("load")
        argv.append(str(module))
        if self.args.dry_run:
            self.logger.event("dry_run_plan", load_argv=argv, recovery_plan=self.recovery_plan())
            return

        started = time.monotonic()
        env = os.environ.copy()
        env.update({"LC_ALL": "C", "LANG": "C"})
        with tempfile.TemporaryFile(mode="w+b") as output:
            try:
                process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, env=env)
            except OSError as exc:
                raise RecoveryError("load_failed", f"Cannot start loader: {exc}", EXIT_LOAD_FAILED) from exc
            timed_out = False
            try:
                while process.poll() is None:
                    self.check_stop()
                    self._choose_patch(before)
                    transition, enabled = self._state()
                    if transition == 1:
                        self._mark_transition_seen()
                    if transition is not None:
                        self.logger.event(
                            "load_transition_sample",
                            patch_name=self.patch_name,
                            transition=transition,
                            enabled=enabled,
                        )
                    if time.monotonic() - started >= min(self.args.command_timeout, self.commands.remaining()):
                        timed_out = True
                        process.terminate()
                        break
                    time.sleep(min(0.1, self.args.poll_interval))
            except BaseException:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise
            try:
                returncode = process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait()
            output.seek(0)
            loader_output = output.read().decode("utf-8", errors="replace").strip()

        self._choose_patch(before)
        transition, enabled = self._state()
        if transition == 1:
            self._mark_transition_seen()
        self.logger.event(
            "load_command_result",
            "INFO" if returncode == 0 and not timed_out else "ERROR",
            argv=argv,
            returncode=returncode,
            duration_seconds=round(time.monotonic() - started, 3),
            timed_out=timed_out,
            output=loader_output,
            patch_name=self.patch_name,
            transition=transition,
            enabled=enabled,
        )
        if returncode != 0 or timed_out:
            raise RecoveryError("load_failed", "Patch loader returned failure or timed out", EXIT_LOAD_FAILED)
        if not self.patch_name or transition is None:
            raise RecoveryError("patch_not_discovered", "Loader succeeded but no matching livepatch sysfs entry was found", EXIT_LOAD_FAILED)

    def attach_monitor(self) -> None:
        before: Set[str] = set()
        if not self._choose_patch(before):
            raise RecoveryError(
                "patch_not_found",
                "Specify --patch-name or ensure exactly one patch is transitioning",
                EXIT_USAGE,
            )
        transition, enabled = self._state()
        self.logger.event(
            "monitor_attached",
            patch_name=self.patch_name,
            transition=transition,
            enabled=enabled,
        )
        if transition == 1:
            self._mark_transition_seen()

    @staticmethod
    def _is_qemu(comm: str, cmdline: Sequence[str]) -> bool:
        candidates = [comm]
        if cmdline:
            candidates.append(Path(cmdline[0]).name)
        return any(value.startswith("qemu-system") or value in ("qemu-kvm", "qemu") for value in candidates)

    def _cmdline(self, pid: int) -> List[str]:
        try:
            raw = (self.proc_root / str(pid) / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            return []
        return [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]

    @staticmethod
    def _option_value(argv: Sequence[str], option: str) -> Optional[str]:
        for index, token in enumerate(argv):
            if token == option and index + 1 < len(argv):
                return argv[index + 1]
            if token.startswith(option + "="):
                return token[len(option) + 1 :]
        return None

    def _domain_for_qemu(self, pid: int, cmdline: Sequence[str]) -> Optional[str]:
        if pid in self.qemu_domain_cache:
            return self.qemu_domain_cache[pid]
        domain: Optional[str] = None
        uuid = self._option_value(cmdline, "-uuid")
        if uuid:
            result = self.commands.run(
                self._virsh_argv("domname", uuid),
                self.args.command_timeout,
                log_event="map_uuid_to_domain",
            )
            if result.returncode == 0 and not result.timed_out and result.stdout:
                domain = result.stdout.splitlines()[-1].strip()
        if not domain:
            name_arg = self._option_value(cmdline, "-name")
            if name_arg:
                match = re.search(r"(?:^|,)guest=([^,]+)", name_arg)
                if match:
                    domain = match.group(1)
        if domain:
            state = self.commands.run(
                self._virsh_argv("domstate", domain),
                self.args.command_timeout,
                log_event="validate_domain_mapping",
            )
            if state.returncode != 0 or state.timed_out:
                domain = None
        # Cache only validated mappings. A transient libvirt error early in the
        # observation window must not make the final blocker unmapped.
        if domain:
            self.qemu_domain_cache[pid] = domain
        return domain

    def scan_pending_tasks(self) -> List[PendingTask]:
        pending: List[PendingTask] = []
        try:
            process_dirs = list(self.proc_root.iterdir())
        except (PermissionError, OSError) as exc:
            raise RecoveryError("proc_scan_failed", f"Cannot scan {self.proc_root}: {exc}", EXIT_VERIFY_FAILED) from exc
        for process_dir in process_dirs:
            if not process_dir.name.isdigit():
                continue
            pid = int(process_dir.name)
            task_root = process_dir / "task"
            try:
                task_dirs = list(task_root.iterdir())
            except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
                continue
            process_tasks: List[Tuple[int, int, str]] = []
            for task_dir in task_dirs:
                if not task_dir.name.isdigit():
                    continue
                patch_state = self._read_int(task_dir / "patch_state")
                if patch_state is None or patch_state == -1 or patch_state == self.args.expected_enabled:
                    continue
                tid = int(task_dir.name)
                task_comm = self._read_text(task_dir / "comm") or ""
                process_tasks.append((tid, patch_state, task_comm))
            if not process_tasks:
                continue
            comm = self._read_text(process_dir / "comm") or ""
            cmdline = self._cmdline(pid)
            qemu_pid = pid if self._is_qemu(comm, cmdline) else None
            domain = self._domain_for_qemu(pid, cmdline) if qemu_pid is not None else None
            for tid, patch_state, task_comm in process_tasks:
                pending.append(PendingTask(pid, tid, patch_state, task_comm or comm, qemu_pid, domain))
        return pending

    @staticmethod
    def _group_domains(tasks: Sequence[PendingTask]) -> Dict[str, List[PendingTask]]:
        groups: Dict[str, List[PendingTask]] = {}
        for task in tasks:
            if task.domain:
                groups.setdefault(task.domain, []).append(task)
        return groups

    def _log_sample(self, transition_age: float, transition: int, enabled: Optional[int], tasks: Sequence[PendingTask]) -> None:
        groups = self._group_domains(tasks)
        truncated = len(tasks) > self.args.max_log_tasks
        self.logger.event(
            "transition_sample",
            patch_name=self.patch_name,
            transition=transition,
            enabled=enabled,
            transition_observed_seconds=round(transition_age, 3),
            pending_task_count=len(tasks),
            mapped_domain_count=len(groups),
            domains={domain: [task.tid for task in members] for domain, members in sorted(groups.items())},
            pending_tasks=[task.as_dict() for task in tasks[: self.args.max_log_tasks]],
            tasks_truncated=truncated,
        )

    def wait_for_deadline(self) -> Tuple[List[PendingTask], Dict[str, List[PendingTask]]]:
        transition_started = self.transition_first_seen_at
        observation_started = time.monotonic()
        while True:
            self.check_stop()
            transition, enabled = self._state()
            if transition == 1:
                if transition_started is None:
                    transition_started = time.monotonic()
                    self.logger.event("transition_observed", patch_name=self.patch_name, enabled=enabled)
                self._mark_transition_seen()
                pending = self.scan_pending_tasks()
                age = time.monotonic() - transition_started
                self._log_sample(age, transition, enabled, pending)
                if age >= self.args.deadline:
                    groups = self._group_domains(pending)
                    self.logger.event(
                        "stall_deadline_reached",
                        patch_name=self.patch_name,
                        deadline_seconds=self.args.deadline,
                        observed_seconds=round(age, 3),
                        pending_task_count=len(pending),
                        blocker_domains=sorted(groups),
                    )
                    for task in pending:
                        self.logger.event("pending_task", **task.as_dict())
                        if task.qemu_pid is not None:
                            self.logger.event(
                                "task_to_qemu",
                                tid=task.tid,
                                qemu_pid=task.qemu_pid,
                            )
                        if task.qemu_pid is not None and task.domain:
                            self.logger.event(
                                "qemu_to_domain",
                                qemu_pid=task.qemu_pid,
                                domain=task.domain,
                            )
                    if not groups:
                        raise RecoveryError(
                            "no_domain_blocker",
                            "Deadline reached but no pending QEMU task could be mapped to a libvirt domain",
                            EXIT_NO_DOMAIN_BLOCKER,
                        )
                    return pending, groups
            elif transition == 0:
                if self.transition_seen:
                    self._verify_patch_state()
                    raise RecoveryError(
                        "completed_without_recovery",
                        "Transition completed before the recovery deadline",
                        EXIT_TRANSITION_MISSED,
                    )
                if time.monotonic() - observation_started >= self.args.observe_timeout:
                    if enabled == self.args.expected_enabled:
                        raise RecoveryError(
                            "transition_missed",
                            "Patch has the target enabled state, but transition=1 was never observed",
                            EXIT_TRANSITION_MISSED,
                        )
                    raise RecoveryError(
                        "transition_not_started",
                        "No livepatch transition was observed and enabled is not the target state",
                        EXIT_TRANSITION_MISSED,
                    )
            else:
                raise RecoveryError("patch_state_unavailable", "Patch sysfs state disappeared or is unreadable", EXIT_VERIFY_FAILED)
            time.sleep(self.args.poll_interval)

    @staticmethod
    def _normalized_domain_state(output: str) -> str:
        return output.strip().splitlines()[-1].strip().lower() if output.strip() else ""

    @staticmethod
    def _is_running_state(state: str) -> bool:
        return state == "running" or state.startswith("running ")

    def _domain_state(self, domain: str, event: str) -> Tuple[CommandResult, str]:
        result = self.commands.run(
            self._virsh_argv("domstate", domain),
            self.args.command_timeout,
            log_event=event,
        )
        return result, self._normalized_domain_state(result.stdout)

    def _resume_with_retries(self, domain: str) -> bool:
        for attempt in range(1, self.args.resume_retries + 1):
            result = self.commands.run(
                self._virsh_argv("resume", domain),
                self.args.command_timeout,
                log_event="domain_resume",
                safety_critical=True,
            )
            if result.returncode == 0 and not result.timed_out:
                return True
            self.logger.event("domain_resume_retry", "WARNING", domain=domain, attempt=attempt)
            if attempt < self.args.resume_retries:
                time.sleep(self.args.resume_retry_interval)
        # A lost virsh response does not necessarily mean that resume failed.
        state = self.commands.run(
            self._virsh_argv("domstate", domain),
            self.args.command_timeout,
            log_event="domain_state_after_resume_failure",
            safety_critical=True,
        )
        if state.returncode == 0 and self._is_running_state(self._normalized_domain_state(state.stdout)):
            self.logger.event("domain_resume_confirmed_by_state", "WARNING", domain=domain)
            return True
        return False

    def recover_domains(self, groups: Mapping[str, Sequence[PendingTask]]) -> None:
        failures: List[str] = []
        for domain in sorted(groups):
            self.check_stop()
            self.logger.event(
                "selected_domain",
                domain=domain,
                blocker_tids=[task.tid for task in groups[domain]],
            )
            state_result, state = self._domain_state(domain, "domain_state_before")
            if state_result.returncode != 0 or state_result.timed_out:
                failures.append(f"{domain}: cannot query state")
                continue
            if not self._is_running_state(state):
                failures.append(f"{domain}: expected running, found {state!r}")
                self.logger.event(
                    "domain_not_running",
                    "ERROR",
                    domain=domain,
                    state=state,
                    action="skip_to_avoid_resuming_a_previously_paused_domain",
                )
                continue
            tids = [task.tid for task in groups[domain]]
            if self.args.dry_run:
                self.logger.event(
                    "dry_run_recovery",
                    domain=domain,
                    blocker_tids=tids,
                    planned_actions=["suspend", "resume"],
                )
                continue

            suspended = False
            resumed = False
            try:
                suspend = self.commands.run(
                    self._virsh_argv("suspend", domain),
                    self.args.command_timeout,
                    log_event="domain_suspend",
                )
                suspended = suspend.returncode == 0 and not suspend.timed_out
            finally:
                # A successful suspend must always be followed immediately by a
                # resume attempt, even after SIGINT/SIGTERM or another failure.
                if not suspended:
                    uncertain_state = self.commands.run(
                        self._virsh_argv("domstate", domain),
                        self.args.command_timeout,
                        log_event="domain_state_after_uncertain_suspend",
                        safety_critical=True,
                    )
                    suspended = (
                        uncertain_state.returncode == 0
                        and self._normalized_domain_state(uncertain_state.stdout).startswith("paused")
                    )
                    if suspended:
                        self.logger.event(
                            "suspend_confirmed_by_state",
                            "WARNING",
                            domain=domain,
                            message="Suspend command did not report success, but the domain is paused",
                        )
                if suspended:
                    resumed = self._resume_with_retries(domain)
                    if not resumed:
                        failures.append(f"{domain}: resume failed after successful suspend")
                    else:
                        self.recovered_domains.append(domain)
            if not suspended:
                failures.append(f"{domain}: suspend failed")
            self.logger.event(
                "domain_recovery_pair",
                "INFO" if suspended and resumed else "ERROR",
                domain=domain,
                blocker_tids=tids,
                suspend_succeeded=suspended,
                resume_succeeded=resumed,
            )
        if self.args.dry_run:
            raise RecoveryError("dry_run_complete", "Recovery actions were planned but not executed", EXIT_OK)
        if failures:
            raise RecoveryError("recovery_failed", "; ".join(failures), EXIT_RECOVERY_FAILED)

    def _wait_for_transition(self, method: str, timeout: float) -> bool:
        started = time.monotonic()
        while True:
            self.check_stop()
            transition, enabled = self._state()
            elapsed = time.monotonic() - started
            self.logger.event(
                "recovery_step_sample",
                method=method,
                transition=transition,
                enabled=enabled,
                step_seconds=round(elapsed, 3),
            )
            if transition == 0:
                self._verify_patch_state()
                self.completion_observed_during = method
                self.logger.event(
                    "recovery_step_completed",
                    method=method,
                    completion_observed_seconds=round(elapsed, 3),
                )
                return True
            if transition is None:
                raise RecoveryError(
                    "patch_state_unavailable",
                    "Patch sysfs state disappeared during recovery",
                    EXIT_VERIFY_FAILED,
                )
            if elapsed >= timeout:
                self.logger.event(
                    "recovery_step_timeout",
                    "WARNING",
                    method=method,
                    timeout_seconds=timeout,
                    transition=transition,
                    enabled=enabled,
                )
                return False
            time.sleep(min(self.args.poll_interval, max(0.0, timeout - elapsed)))

    def _signal_pending_tasks(self, tasks: Sequence[PendingTask]) -> bool:
        targets = sorted({task.tid for task in tasks if task.qemu_pid is not None and task.domain})
        qemu_pids = sorted({task.qemu_pid for task in tasks if task.qemu_pid is not None and task.domain})
        if not targets:
            self.logger.event("signal_step_skipped", "WARNING", reason="no_mapped_qemu_tid")
            return False
        if self.args.dry_run:
            self.logger.event(
                "dry_run_signal",
                target_tids=targets,
                planned_actions=["SIGSTOP", "SIGCONT"],
            )
            return True

        stopped: List[int] = []
        continued_qemu_pids: List[int] = []
        failures: List[str] = []
        try:
            for tid in targets:
                try:
                    os.kill(tid, signal.SIGSTOP)
                    stopped.append(tid)
                    self.logger.event("task_signal", tid=tid, signal="SIGSTOP", delivered=True)
                except (ProcessLookupError, PermissionError, OSError) as exc:
                    failures.append(f"{tid}: SIGSTOP: {exc}")
                    self.logger.event(
                        "task_signal",
                        "ERROR",
                        tid=tid,
                        signal="SIGSTOP",
                        delivered=False,
                        error=str(exc),
                    )
            if stopped:
                time.sleep(self.args.signal_pause)
        finally:
            # SIGCONT is availability cleanup and must be attempted even when
            # the program is interrupted after SIGSTOP.
            for tid in stopped:
                try:
                    os.kill(tid, signal.SIGCONT)
                    self.logger.event("task_signal", tid=tid, signal="SIGCONT", delivered=True)
                except (ProcessLookupError, PermissionError, OSError) as exc:
                    failures.append(f"{tid}: SIGCONT: {exc}")
                    self.logger.event(
                        "task_signal",
                        "ERROR",
                        tid=tid,
                        signal="SIGCONT",
                        delivered=False,
                        error=str(exc),
                    )
            # A SIGSTOP directed at a thread can create a group stop. Also send
            # SIGCONT to the QEMU process ID as an idempotent availability
            # safeguard if a task disappeared between the paired operations.
            for qemu_pid in qemu_pids:
                assert qemu_pid is not None
                try:
                    os.kill(qemu_pid, signal.SIGCONT)
                    continued_qemu_pids.append(qemu_pid)
                    self.logger.event(
                        "signal_cleanup",
                        qemu_pid=qemu_pid,
                        signal="SIGCONT",
                        delivered=True,
                    )
                except (ProcessLookupError, PermissionError, OSError) as exc:
                    failures.append(f"QEMU {qemu_pid}: SIGCONT: {exc}")
                    self.logger.event(
                        "signal_cleanup",
                        "ERROR",
                        qemu_pid=qemu_pid,
                        signal="SIGCONT",
                        delivered=False,
                        error=str(exc),
                    )
        self.logger.event(
            "signal_recovery_pair",
            "INFO" if stopped and not failures else "WARNING",
            target_tids=targets,
            stopped_tids=stopped,
            continued_qemu_pids=continued_qemu_pids,
            pause_seconds=self.args.signal_pause,
            failures=failures,
        )
        return bool(stopped)

    def _qemu_cpu_max_paths(self, tasks: Sequence[PendingTask]) -> List[Path]:
        root = Path(self.args.cgroup_root).resolve()
        paths: Set[Path] = set()
        for pid in sorted({task.qemu_pid for task in tasks if task.qemu_pid is not None and task.domain}):
            assert pid is not None
            content = self._read_text(self.proc_root / str(pid) / "cgroup")
            if not content:
                continue
            unified_path: Optional[str] = None
            for line in content.splitlines():
                fields = line.split(":", 2)
                if len(fields) == 3 and fields[0] == "0" and fields[1] == "":
                    unified_path = fields[2]
                    break
            if unified_path is None:
                continue
            candidate = (root / unified_path.lstrip("/")).resolve()
            try:
                if os.path.commonpath((str(root), str(candidate))) != str(root):
                    continue
            except ValueError:
                continue
            # QEMU is commonly placed in .../<domain>.scope/libvirt/emulator.
            # Throttle the .scope ancestor so the quota covers emulator, vCPU,
            # I/O and every other descendant in the libvirt domain tree.
            domain_scope: Optional[Path] = None
            cursor = candidate
            while cursor != root:
                if cursor.name.endswith(".scope"):
                    domain_scope = cursor
                    break
                cursor = cursor.parent
            if domain_scope is None:
                self.logger.event(
                    "qemu_cgroup_rejected",
                    "WARNING",
                    qemu_pid=pid,
                    cgroup=str(candidate),
                    reason="no_scope_ancestor",
                )
                continue
            cpu_max = domain_scope / "cpu.max"
            if cpu_max.is_file():
                paths.add(cpu_max)
                self.logger.event(
                    "qemu_to_cgroup",
                    qemu_pid=pid,
                    task_cgroup=str(candidate),
                    domain_scope=str(domain_scope),
                    cpu_max=str(cpu_max),
                )
        return sorted(paths, key=str)

    def _write_control(self, path: Path, value: str) -> None:
        with path.open("w", encoding="ascii") as stream:
            stream.write(value.rstrip() + "\n")

    def _run_throttle_step(self, tasks: Sequence[PendingTask]) -> bool:
        paths = self._qemu_cpu_max_paths(tasks)
        if not paths:
            self.logger.event("throttle_step_skipped", "WARNING", reason="no_cgroup_v2_cpu_max")
            return False
        if self.args.dry_run:
            self.logger.event(
                "dry_run_throttle",
                cpu_max_paths=[str(path) for path in paths],
                planned_cpu_max=self.args.throttle_cpu_max,
            )
            return True

        originals: Dict[Path, str] = {}
        completed = False
        try:
            for path in paths:
                original = self._read_text(path)
                if original is None:
                    raise RecoveryError("throttle_read_failed", f"Cannot read {path}", EXIT_RECOVERY_FAILED)
                originals[path] = original
                self._write_control(path, self.args.throttle_cpu_max)
                readback = self._read_text(path)
                self.logger.event(
                    "throttle_applied",
                    path=str(path),
                    original_cpu_max=original,
                    requested_cpu_max=self.args.throttle_cpu_max,
                    readback=readback,
                )
                if readback != self.args.throttle_cpu_max:
                    raise RecoveryError("throttle_readback_failed", f"cpu.max read-back mismatch at {path}", EXIT_RECOVERY_FAILED)
            completed = self._wait_for_transition("throttle", self.args.recovery_step_timeout)
            return completed
        finally:
            failures: List[str] = []
            for path, original in originals.items():
                try:
                    self._write_control(path, original)
                    readback = self._read_text(path)
                    if readback != original:
                        failures.append(f"{path}: read-back {readback!r}")
                    self.logger.event(
                        "throttle_restored",
                        "INFO" if readback == original else "ERROR",
                        path=str(path),
                        restored_cpu_max=original,
                        readback=readback,
                    )
                except OSError as exc:
                    failures.append(f"{path}: {exc}")
                    self.logger.event("throttle_restore_failed", "ERROR", path=str(path), error=str(exc))
            if failures:
                raise RecoveryError(
                    "throttle_cleanup_failed",
                    "Failed to restore cpu.max: " + "; ".join(failures),
                    EXIT_RECOVERY_FAILED,
                )

    def _force_transition(self) -> bool:
        assert self.patch_name is not None
        force_path = self.livepatch_root / self.patch_name / "force"
        if not force_path.is_file():
            self.logger.event("force_step_skipped", "WARNING", reason="force_attribute_unavailable", path=str(force_path))
            return False
        if self.args.dry_run:
            self.logger.event("dry_run_force", path=str(force_path), planned_value=1)
            return True
        self.logger.event(
            "force_transition_requested",
            "WARNING",
            path=str(force_path),
            warning="force clears pending state and can permanently prevent safe module removal",
        )
        try:
            self._write_control(force_path, "1")
        except OSError as exc:
            raise RecoveryError("force_write_failed", f"Cannot write {force_path}: {exc}", EXIT_RECOVERY_FAILED) from exc
        return True

    def run_recovery_plan(
        self,
        tasks: Sequence[PendingTask],
        groups: Mapping[str, Sequence[PendingTask]],
    ) -> None:
        self.affected_domains = sorted(groups)
        plan = self.recovery_plan()
        self.logger.event(
            "recovery_plan_started",
            strategy=self.args.strategy,
            methods=plan,
            affected_domains=self.affected_domains,
            recovery_step_timeout_seconds=self.args.recovery_step_timeout,
        )
        current_tasks = list(tasks)
        current_groups: Mapping[str, Sequence[PendingTask]] = groups

        for method in plan:
            self.check_stop()
            transition, _ = self._state()
            if transition == 0:
                self._verify_patch_state()
                self.completion_observed_during = "between-steps"
                self.logger.event(
                    "transition_completed_between_steps",
                    "WARNING",
                    next_method=method,
                    attribution="previous_step_or_natural_completion",
                )
                break

            refreshed = self.scan_pending_tasks()
            refreshed_groups = self._group_domains(refreshed)
            if refreshed_groups:
                current_tasks = refreshed
                current_groups = refreshed_groups
            self.recovery_steps_attempted.append(method)
            self.logger.event(
                "recovery_step_started",
                method=method,
                pending_task_count=len(current_tasks),
                blocker_domains=sorted(current_groups),
            )

            completed = False
            if method == "wait":
                completed = self._wait_for_transition(method, self.args.recovery_step_timeout)
            elif method == "signal":
                acted = self._signal_pending_tasks(current_tasks)
                if acted:
                    completed = self._wait_for_transition(method, self.args.recovery_step_timeout)
            elif method == "throttle":
                completed = self._run_throttle_step(current_tasks)
            elif method == "suspend-resume":
                self.recover_domains(current_groups)
                completed = self._wait_for_transition(method, self.args.recovery_step_timeout)
            elif method == "force":
                acted = self._force_transition()
                if acted:
                    completed = self._wait_for_transition(method, self.args.recovery_step_timeout)
            else:  # Protected by argparse/type validation.
                raise RecoveryError("unknown_recovery_method", method, EXIT_USAGE)

            if completed:
                break
            self.logger.event("recovery_step_continuing", "WARNING", method=method, next_step_pending=True)
        else:
            raise RecoveryError(
                "transition_still_pending",
                "Transition remained pending after all configured recovery methods",
                EXIT_VERIFY_FAILED,
            )

        for domain in self.affected_domains:
            self._verify_domain_health(domain)
        self.logger.event(
            "recovery_plan_completed",
            strategy=self.args.strategy,
            methods_attempted=self.recovery_steps_attempted,
            completion_observed_during=self.completion_observed_during,
            affected_domains=self.affected_domains,
        )

    def _verify_patch_state(self) -> None:
        transition, enabled = self._state()
        if transition != 0 or enabled != self.args.expected_enabled:
            raise RecoveryError(
                "patch_verification_failed",
                f"Expected transition=0 and enabled={self.args.expected_enabled}; got transition={transition}, enabled={enabled}",
                EXIT_VERIFY_FAILED,
            )
        self.logger.event(
            "patch_verified",
            patch_name=self.patch_name,
            transition=transition,
            enabled=enabled,
        )

    def _verify_domain_health(self, domain: str) -> None:
        state_result, state = self._domain_state(domain, "domain_state_after")
        if state_result.returncode != 0 or state_result.timed_out or not self._is_running_state(state):
            raise RecoveryError(
                "vm_health_failed",
                f"Domain {domain!r} is not running after recovery (state={state!r})",
                EXIT_VERIFY_FAILED,
            )
        if self.args.health_command:
            try:
                health_argv = [part.replace("{domain}", domain) for part in shlex.split(self.args.health_command)]
            except ValueError as exc:
                raise RecoveryError("invalid_health_command", str(exc), EXIT_USAGE) from exc
            if not health_argv:
                raise RecoveryError("invalid_health_command", "--health-command is empty", EXIT_USAGE)
            health = self.commands.run(
                health_argv,
                self.args.command_timeout,
                log_event="domain_health_command",
            )
            if health.returncode != 0 or health.timed_out:
                raise RecoveryError(
                    "vm_health_failed",
                    f"Health command failed for domain {domain!r}",
                    EXIT_VERIFY_FAILED,
                )
        self.logger.event("domain_health_verified", domain=domain, state=state)

    def execute(self) -> Tuple[str, str]:
        module = self.preflight()
        if self.args.dry_run and not self.args.monitor_only:
            assert module is not None
            self.load_patch(module)
            return "dry_run_complete", "Validated inputs and printed the non-mutating execution plan"
        if self.args.monitor_only:
            self.attach_monitor()
        else:
            assert module is not None
            self.load_patch(module)
        tasks, groups = self.wait_for_deadline()
        self.run_recovery_plan(tasks, groups)
        if self.completion_observed_during == "wait":
            return "completed_during_wait", "Transition completed during the configured wait step"
        return (
            "recovered",
            f"Transition completion observed during {self.completion_observed_during}; affected domains are healthy",
        )


def positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def recovery_order(value: str) -> Tuple[str, ...]:
    methods = tuple(part.strip() for part in value.split(",") if part.strip())
    if not methods:
        raise argparse.ArgumentTypeError("must contain at least one recovery method")
    unknown = [method for method in methods if method not in RECOVERY_METHODS]
    if unknown:
        raise argparse.ArgumentTypeError(
            "unknown method(s): " + ", ".join(unknown) + "; choose from " + ", ".join(RECOVERY_METHODS)
        )
    if len(set(methods)) != len(methods):
        raise argparse.ArgumentTypeError("recovery methods must not be repeated")
    return methods


def cpu_max_value(value: str) -> str:
    normalized = " ".join(value.split())
    match = re.fullmatch(r"([1-9][0-9]*) ([1-9][0-9]*)", normalized)
    if not match:
        raise argparse.ArgumentTypeError("must be QUOTA PERIOD using positive integers, for example '1000 100000'")
    return normalized


def sha256_digest(value: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise argparse.ArgumentTypeError("must be exactly 64 hexadecimal characters")
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load an exact livepatch module, identify pending QEMU tasks by libvirt domain, and run a controlled recovery strategy.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--module", help="Exact mentor-provided livepatch .ko file")
    parser.add_argument("--expected-sha256", type=sha256_digest, help="Fail before load unless MODULE has this SHA-256 digest")
    parser.add_argument("--patch-name", help="Exact directory name under /sys/kernel/livepatch (auto-discovered after load if omitted)")
    parser.add_argument(
        "--loader",
        default="insmod",
        help="Non-blocking module loader executable; use insmod so monitoring/recovery can proceed while transition=1",
    )
    parser.add_argument("--monitor-only", action="store_true", help="Do not load a module; attach to an already-started transition")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report planned mutations without executing them")
    parser.add_argument("--deadline", type=positive_float, default=10.0, help="Continuous observed transition=1 time before recovery; this is not the 75-second acceptance gate")
    parser.add_argument("--observe-timeout", type=positive_float, default=10.0, help="Time to wait when transition=1 has not yet been observed")
    parser.add_argument(
        "--recovery-step-timeout",
        "--verify-timeout",
        dest="recovery_step_timeout",
        type=positive_float,
        default=2.0,
        help="Observation window after each method; --verify-timeout is a backward-compatible alias",
    )
    parser.add_argument("--total-timeout", type=positive_float, default=180.0, help="Hard limit for the entire program")
    parser.add_argument("--poll-interval", type=positive_float, default=1.0, help="Livepatch and /proc sampling interval")
    parser.add_argument("--command-timeout", type=positive_float, default=20.0, help="Per-command limit, capped by total timeout")
    parser.add_argument("--resume-retries", type=positive_int, default=3, help="Resume attempts after a successful suspend")
    parser.add_argument("--resume-retry-interval", type=positive_float, default=1.0, help="Delay between resume retries")
    parser.add_argument("--expected-enabled", type=int, choices=(0, 1), default=1, help="Required final enabled and per-task target state")
    parser.add_argument(
        "--strategy",
        choices=("wait", "signal", "throttle", "suspend-resume", "force", "cascade"),
        default="suspend-resume",
        help="Recovery mode; suspend-resume remains the mentor-required default",
    )
    parser.add_argument(
        "--cascade-order",
        type=recovery_order,
        default=DEFAULT_CASCADE,
        metavar="METHOD[,METHOD...]",
        help="Ordered methods for --strategy cascade; throttle is opt-in because current evidence found no early benefit",
    )
    parser.add_argument("--signal-pause", type=positive_float, default=0.05, help="Seconds between SIGSTOP and mandatory SIGCONT for mapped pending TIDs")
    parser.add_argument(
        "--throttle-cpu-max",
        type=cpu_max_value,
        default="1000 100000",
        metavar="'QUOTA PERIOD'",
        help="Temporary cgroup v2 cpu.max value used by the throttle method",
    )
    parser.add_argument("--allow-force", action="store_true", help="Explicitly authorize the unsafe livepatch force sysfs operation")
    parser.add_argument("--virsh", default="virsh", help="virsh executable")
    parser.add_argument("--connect", help="Optional libvirt connection URI")
    parser.add_argument(
        "--health-command",
        help="Optional shell-free guest health command; {domain} is replaced in each argv element",
    )
    parser.add_argument("--livepatch-root", default="/sys/kernel/livepatch", help=argparse.SUPPRESS)
    parser.add_argument("--proc-root", default="/proc", help=argparse.SUPPRESS)
    parser.add_argument("--cgroup-root", default="/sys/fs/cgroup", help=argparse.SUPPRESS)
    parser.add_argument("--max-log-tasks", type=positive_int, default=100, help="Maximum pending task records in each sample")
    parser.add_argument("--log", type=Path, help="Write this execution evidence to this file, replacing any previous content")
    parser.add_argument("--output-format", choices=("both", "human", "jsonl"), default="both", help="stdout and --log representation")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.total_timeout <= args.deadline and not args.dry_run:
        parser.error("--total-timeout must be greater than --deadline")
    stop_event = threading.Event()

    def request_stop(signum: int, _frame: Any) -> None:
        stop_event.set()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_name, request_stop)

    logger = EventLogger(args.output_format, args.log)
    logger.event("run_start", argv=list(argv) if argv is not None else sys.argv[1:])
    controller = RecoveryController(args, logger, stop_event)
    result = "internal_error"
    message = "Unhandled failure"
    exit_code = EXIT_VERIFY_FAILED
    try:
        result, message = controller.execute()
        exit_code = EXIT_OK
    except RecoveryError as exc:
        result, message, exit_code = exc.result, str(exc), exc.exit_code
    except KeyboardInterrupt:
        result, message, exit_code = "interrupted", "Interrupted by keyboard", EXIT_INTERRUPTED
    except Exception as exc:  # A final evidence record is preferable to a silent traceback.
        result, message, exit_code = "internal_error", f"{type(exc).__name__}: {exc}", EXIT_VERIFY_FAILED
        logger.event("unexpected_exception", "ERROR", exception_type=type(exc).__name__, message=str(exc))
    finally:
        logger.event(
            "final_result",
            "INFO" if exit_code == EXIT_OK else "ERROR",
            result=result,
            message=message,
            exit_code=exit_code,
            patch_name=controller.patch_name,
            transition_seen=controller.transition_seen,
            recovered_domains=controller.recovered_domains,
            affected_domains=controller.affected_domains,
            recovery_steps_attempted=controller.recovery_steps_attempted,
            completion_observed_during=controller.completion_observed_during,
        )
        logger.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
