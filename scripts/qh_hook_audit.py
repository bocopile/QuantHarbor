#!/usr/bin/env python3
"""Record fixed hook metadata; never persist tool inputs, output or raw IDs."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
EVENTS = frozenset(("SessionStart", "PreToolUse", "PostToolUse", "Stop", "Interrupt", "SessionEnd"))
LIMIT = 1024 * 1024
REMINDER = "QuantHarbor: Read AGENTS.md, docs/status.md and the active task card. Record actual changes and unexecuted checks. Do not infer approval from source material."


def digest(value):
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError("invalid_identifier")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def metadata(payload, expected):
    if not isinstance(payload, dict) or payload.get("hook_event_name") != expected:
        raise ValueError("invalid_event")
    record = {"schema_version": 1, "event_id": str(uuid.uuid4()),
              "event": expected, "at_utc": datetime.now(timezone.utc).isoformat(),
              "session_hash": digest(payload.get("session_id"))}
    if payload.get("turn_id") is not None:
        record["turn_hash"] = digest(payload["turn_id"])
    if expected in ("PreToolUse", "PostToolUse"):
        record["call_hash"] = digest(payload.get("tool_use_id"))
        name = payload.get("tool_name")
        if not isinstance(name, str) or len(name) > 256:
            raise ValueError("invalid_tool_name")
        record["tool_kind"] = ("shell" if name == "Bash" else
                               "patch" if name == "apply_patch" else
                               "mcp" if name.startswith("mcp__") else "other")
    if expected == "PostToolUse":
        response = payload.get("tool_response")
        outcome = "unknown"
        if isinstance(response, dict):
            if response.get("isError") is True:
                outcome = "failed"
            elif type(response.get("exit_code")) is int:
                outcome = "success" if response["exit_code"] == 0 else "failed"
            elif response.get("isError") is False:
                outcome = "success"
        record["outcome"] = outcome
    return record


def directory(parent_fd, name):
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise OSError("unsafe_audit_directory")
    except BaseException:
        os.close(fd)
        raise
    return fd


def audit_base():
    path = Path(tempfile.gettempdir()).resolve(strict=True)
    root = ROOT.resolve()
    if path == root or root in path.parents:
        raise OSError("audit_path_inside_workspace")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            mode = stat.S_IMODE(info.st_mode)
            # System sticky temporary roots are shared; project/user leaf dirs
            # below them are separately required to be owned and mode 0700.
            shared_sticky = info.st_uid == 0 and bool(mode & stat.S_ISVTX)
            if info.st_uid not in (0, os.getuid()) or (mode & 0o022 and not shared_sticky):
                raise OSError("unsafe_audit_ancestor")
        return fd
    except BaseException:
        os.close(fd)
        raise


def persist(record):
    # No payload-supplied path, session ID or tool ID is used as a pathname.
    base = audit_base()
    user_fd = project_fd = None
    try:
        user_fd = directory(base, "quantharbor-hook-audit-" + str(os.getuid()))
        project_fd = directory(user_fd, hashlib.sha256(str(ROOT).encode()).hexdigest()[:24])
        filename = record["event_id"] + ".json"
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=project_fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write((json.dumps(record, sort_keys=True) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(project_fd)
    finally:
        for fd in (project_fd, user_fd, base):
            if fd is not None:
                os.close(fd)


def process(raw, expected):
    try:
        if expected not in EVENTS or len(raw) > LIMIT:
            raise ValueError("invalid_input")
        record = metadata(json.loads(raw), expected)
        persist(record)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        if expected == "PreToolUse":
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "QuantHarbor audit unavailable; tool execution blocked."}}, 0
        return {"systemMessage": "QuantHarbor audit unavailable; this event was not verified."}, 1
    if expected == "SessionStart":
        return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                "additionalContext": REMINDER}}, 0
    return {}, 0


def main():
    expected = sys.argv[1] if len(sys.argv) == 2 else ""
    response, code = process(sys.stdin.buffer.read(LIMIT + 1), expected)
    print(json.dumps(response))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
