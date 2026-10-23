#!/usr/bin/env python3
"""고정 로컬 검사만 실행한다. 전체 도구 감사·격리·자동 복구 기능은 아니다."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(Path(sys.executable).resolve())
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
MAX_AUDIT_BYTES = 65536
GRACE_SECONDS = 0.25
POLL_SECONDS = 0.02


@dataclass(frozen=True)
class Check:
    argv: tuple
    timeout: float
    inputs: tuple


COMMON_INPUTS = (("wrapper", "scripts/run_local_check.py"),
                 ("parent_config", ".codex/config.toml"))
CHECKS = {
    "team-config": Check(
        (PYTHON, "-B", str(ROOT / "scripts/check_ai_team.py")), 30,
        COMMON_INPUTS + (("checker", "scripts/check_ai_team.py"),
                         ("team", "config/ai/team.toml"),
                         ("queue", "config/ai/execution-queue.json"),
                         ("catalog", "docs/evidence/env-model-catalog-2026-10-20.json"),
                         ("execution_checklist", "docs/execution-checklist.md"),
                         ("approval_register", "docs/approval-register.md"))
        + tuple((name, f".codex/agents/{name}.toml") for name in (
            "qh_researcher", "qh_architect", "qh_implementer", "qh_reviewer",
            "qh_security_reviewer", "qh_validator"))),
    "environment-profiles": Check(
        (PYTHON, "-B", str(ROOT / "scripts/validate_environment.py")), 150,
        COMMON_INPUTS + (("checker", "scripts/validate_environment.py"),
                         ("policy", "config/ai/development-policy.toml"))),
}


@dataclass(frozen=True)
class Result:
    run_id: str
    status: str
    reason: str

    @property
    def exit_code(self):
        return 0 if self.status == "success" else 1


class AuditError(Exception):
    """원문을 출력하지 않는 로컬 저장 실패."""


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _valid_id(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _audit_location():
    base = Path(tempfile.gettempdir()).resolve()
    if base.is_relative_to(ROOT.resolve()):
        raise AuditError()
    namespace = f"quantharbor-local-checks-{os.getuid()}"
    repository = hashlib.sha256(str(ROOT).encode("utf-8")).hexdigest()[:16]
    return base, namespace, repository


def _check_directory(fd, private):
    metadata = os.fstat(fd)
    mode = stat.S_IMODE(metadata.st_mode)
    if not stat.S_ISDIR(metadata.st_mode):
        raise AuditError()
    if private:
        if metadata.st_uid != os.getuid() or mode != 0o700:
            raise AuditError()
    elif (metadata.st_uid not in (0, os.getuid())
          or (mode & 0o022 and not (metadata.st_uid == 0 and mode & stat.S_ISVTX))):
        raise AuditError()


@contextmanager
def _open_audit_directory(create):
    """시스템 임시 경로 이후 두 전용 디렉터리는 소유자 전용 0700이어야 한다."""
    base, namespace, repository = _audit_location()
    fd = os.open("/", DIR_FLAGS)
    try:
        for component in base.parts[1:]:
            child = os.open(component, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
            _check_directory(fd, private=False)
        for component in (namespace, repository):
            if create:
                try:
                    os.mkdir(component, 0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(component, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
            _check_directory(fd, private=True)
        yield fd
    finally:
        os.close(fd)


def _hash_inputs(check):
    """고정 공개 파일만 openat으로 읽는다. symlink와 비정규 파일은 거부한다."""
    hashes = {}
    for label, relative in check.inputs:
        fd = os.open(ROOT, DIR_FLAGS)
        try:
            parts = Path(relative).parts
            for part in parts[:-1]:
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = child
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
            with os.fdopen(file_fd, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise AuditError()
                hashes[label] = hashlib.file_digest(source, "sha256").hexdigest()
        finally:
            os.close(fd)
    return hashes


def _append(stream, directory_fd, record):
    """호출 성공은 file flush/fsync와 부모 directory fsync 완료를 뜻한다."""
    stream.write((json.dumps(record, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii"))
    stream.flush()
    os.fsync(stream.fileno())
    os.fsync(directory_fd)


@contextmanager
def _new_audit(directory_fd, run_id):
    fd = os.open(f"{run_id}.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, "wb") as stream:
        metadata = os.fstat(stream.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
            raise AuditError()
        yield stream


@contextmanager
def _interrupts():
    pending = []

    def remember(signum, _frame):
        if not pending:
            pending.append(signum)

    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for sig in previous:
            signal.signal(sig, remember)
        yield pending
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def _cleanup(child):
    """현재 실행이 만든 process group만 종료하고 직접 자식은 wait한다."""
    clean = True
    try:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + GRACE_SECONDS
        while _group_exists(child.pid) and time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    except OSError:
        clean = False
        # group 제어가 실패해도 현재 직접 자식의 종료는 시도한다.
        try:
            child.kill()
        except OSError:
            pass
    try:
        child.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        clean = False
    return clean


def _execute(check, pending, started):
    child = None
    status, reason = "startup_error", "spawn_failed"
    try:
        if pending:
            return "interrupted", "signal_received", None
        if time.monotonic() >= started + check.timeout:
            return "timeout", "deadline_exceeded", None
        child = subprocess.Popen(check.argv, shell=False, cwd=ROOT,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        deadline = started + check.timeout
        while True:
            if pending:
                status, reason = "interrupted", "signal_received"
                break
            if time.monotonic() >= deadline:
                status, reason = "timeout", "deadline_exceeded"
                break
            try:
                code = child.wait(timeout=min(POLL_SECONDS, max(0.001, deadline - time.monotonic())))
                status, reason = ("success", "exit_zero") if code == 0 else ("failed", "exit_nonzero")
                break
            except subprocess.TimeoutExpired:
                continue
    except (OSError, subprocess.SubprocessError):
        status, reason = "startup_error", "spawn_failed"
    finally:
        if child is not None and not _cleanup(child):
            if status == "success":
                status = "failed"
            reason = "cleanup_failed"
    if pending:
        status, reason = "interrupted", "signal_received" if reason != "cleanup_failed" else reason
    return status, reason, child.returncode if child is not None else None


def run_check(check_id):
    """운영 인자는 allowlist ID뿐이다. 내부 함수 patch는 합성 테스트에만 쓴다."""
    if check_id not in CHECKS:
        return Result("", "invalid", "invalid_request")
    run_id = str(uuid.uuid4())
    check = CHECKS[check_id]
    started = time.monotonic()
    common = {"schema_version": 1, "run_id": run_id, "check_id": check_id,
              "attempt": 1, "timeout_seconds": check.timeout}
    start_persisted = False
    try:
        with _interrupts() as pending, _open_audit_directory(create=True) as directory_fd:
            hashes = _hash_inputs(check)
            with _new_audit(directory_fd, run_id) as stream:
                _append(stream, directory_fd, {**common, "event": "start", "utc": _utc(), "input_sha256": hashes})
                start_persisted = True
                status, reason, code = _execute(check, pending, started)
                offset = stream.tell()
                try:
                    _append(stream, directory_fd, {**common, "event": "terminal", "utc": _utc(),
                            "duration_seconds": round(max(0, time.monotonic() - started), 6),
                            "exit_code": code, "status": status, "reason": reason})
                except (OSError, ValueError):
                    # 관측 가능한 미완성 terminal을 성공으로 오인하지 않게 rollback을 시도한다.
                    # 저장 장치 전체 실패 시 rollback의 영속성까지 보장할 수는 없다.
                    try:
                        stream.seek(offset)
                        stream.truncate()
                        stream.flush()
                        os.fsync(stream.fileno())
                    except (OSError, ValueError):
                        pass
                    return Result(run_id, "failed", "audit_terminal_failed")
                return Result(run_id, status, reason)
    except (OSError, ValueError, AuditError):
        if start_persisted:
            return Result(run_id, "failed", "audit_terminal_failed")
        return Result(run_id, "startup_error", "audit_start_failed")


def _read_audit(directory_fd, run_id):
    fd = os.open(f"{run_id}.jsonl", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                 dir_fd=directory_fd)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1
                or metadata.st_size > MAX_AUDIT_BYTES):
            raise AuditError()
        data = bytearray()
        while len(data) <= MAX_AUDIT_BYTES:
            part = os.read(fd, min(8192, MAX_AUDIT_BYTES + 1 - len(data)))
            if not part:
                return bytes(data)
            data.extend(part)
        raise AuditError()
    finally:
        os.close(fd)


def _valid_common(record, run_id, check_id):
    try:
        timestamp = datetime.fromisoformat(record["utc"])
        return (record["schema_version"] == 1 and type(record["schema_version"]) is int
                and record["run_id"] == run_id and record["check_id"] == check_id
                and type(record["attempt"]) is int and record["attempt"] == 1
                and type(record["timeout_seconds"]) in (int, float)
                and record["timeout_seconds"] == CHECKS[check_id].timeout
                and timestamp.utcoffset() is not None and timestamp.utcoffset().total_seconds() == 0)
    except (KeyError, ValueError, TypeError):
        return False


def _inspect_bytes(data, run_id):
    common_keys = {"schema_version", "run_id", "check_id", "attempt", "timeout_seconds", "event", "utc"}
    lines = data.splitlines(keepends=True)
    try:
        if not lines or not lines[0].endswith(b"\n"):
            return Result(run_id, "invalid", "invalid_audit")
        start = json.loads(lines[0])
        if not isinstance(start, dict):
            raise ValueError()
        check_id = start.get("check_id")
        if (not isinstance(check_id, str) or check_id not in CHECKS
                or set(start) != common_keys | {"input_sha256"}
                or start["event"] != "start" or not _valid_common(start, run_id, check_id)):
            raise ValueError()
        hashes = start["input_sha256"]
        if (not isinstance(hashes, dict) or set(hashes) != {label for label, _ in CHECKS[check_id].inputs}
                or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values())):
            raise ValueError()
        if len(lines) == 1 or (len(lines) == 2 and not lines[1].endswith(b"\n")):
            return Result(run_id, "incomplete", "terminal_missing")
        if len(lines) != 2:
            raise ValueError()
        terminal = json.loads(lines[1])
        if (not isinstance(terminal, dict)
                or set(terminal) != common_keys | {"duration_seconds", "exit_code", "status", "reason"}
                or terminal["event"] != "terminal" or not _valid_common(terminal, run_id, check_id)):
            raise ValueError()
        status, reason = terminal["status"], terminal["reason"]
        allowed = {"success": {"exit_zero"}, "failed": {"exit_nonzero", "cleanup_failed"},
                   "timeout": {"deadline_exceeded", "cleanup_failed"},
                   "interrupted": {"signal_received", "cleanup_failed"}, "startup_error": {"spawn_failed"}}
        duration, code = terminal["duration_seconds"], terminal["exit_code"]
        if (not isinstance(status, str) or status not in allowed
                or not isinstance(reason, str) or reason not in allowed[status]
                or type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0
                or (code is not None and type(code) is not int)
                or (status == "success" and code != 0)
                or (status == "failed" and reason == "exit_nonzero" and (code is None or code == 0))
                or (status == "startup_error" and code is not None)):
            raise ValueError()
        return Result(run_id, status, reason)
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError, OverflowError):
        return Result(run_id, "invalid", "invalid_audit")


def inspect_run(run_id):
    """terminal 없음은 incomplete다. 생존 여부 추측·PID 복구·재실행은 하지 않는다."""
    if not _valid_id(run_id):
        return Result("", "invalid", "invalid_request")
    try:
        with _open_audit_directory(create=False) as directory_fd:
            data = _read_audit(directory_fd, run_id)
        return _inspect_bytes(data, run_id)
    except (OSError, ValueError, AuditError):
        return Result(run_id, "invalid", "invalid_audit")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or (args[0] == "run" and args[1] not in CHECKS) or args[0] not in ("run", "inspect"):
        print("invalid_request")
        return 2
    if args[0] == "inspect" and not _valid_id(args[1]):
        print("invalid_request")
        return 2
    try:
        result = run_check(args[1]) if args[0] == "run" else inspect_run(args[1])
        print(f"{result.run_id} {result.status} {result.reason}")
        return result.exit_code
    except Exception:
        # 예외 원문에는 명령·경로·환경값이 들어갈 수 있어 출력하지 않는다.
        print("local_check_error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
