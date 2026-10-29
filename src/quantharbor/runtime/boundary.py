"""Q14 합성 경계의 trusted host controller용 검사.

같은 Python 프로세스의 악성 코드를 격리하거나 실제 사용자를 인증하지 않는다.
실제 principal/계좌/주문 통합은 Q26 이후다. private 검사는 metadata만 읽으며
검사 이후 별도 open의 안전성을 보장하는 파일 접근 API가 아니다.
"""

from dataclasses import dataclass, fields
import math
import os
from pathlib import Path
import stat
import time
from types import MappingProxyType


_ROOT = Path(__file__).resolve().parents[3]


class BoundaryError(ValueError):
    """원문 경로·환경·예외 대신 고정 reason만 전한다."""

    def __init__(self, reason="boundary_denied"):
        super().__init__(reason)


_BINDING = MappingProxyType({
    "environment": "synthetic", "binding_version": "synthetic-v1",
    "broker": "disabled", "account_ref": "synthetic-account", "host": "disabled",
    "transaction_code": "disabled", "key_ref": "disabled",
    "capability_version": "synthetic-none-v1", "database_namespace": "qh_synthetic",
    "queue_namespace": "qh_synthetic",
})
_ACTIONS = MappingProxyType({
    "research": frozenset(("synthetic.read", "synthetic.compute")),
    "reporting": frozenset(("synthetic.read", "synthetic.report")),
    "controller": frozenset(("synthetic.read", "synthetic.session")),
})


@dataclass(frozen=True, slots=True)
class SyntheticBinding:
    role: str
    environment: str
    binding_version: str
    broker: str
    account_ref: str
    host: str
    transaction_code: str
    key_ref: str
    capability_version: str
    database_namespace: str
    queue_namespace: str

    def __post_init__(self):
        if type(self.role) is not str or self.role not in _ACTIONS:
            raise BoundaryError()
        for key, expected in _BINDING.items():
            actual = getattr(self, key)
            if type(actual) is not str or actual != expected:
                raise BoundaryError()


def binding_from_mapping(value):
    if type(value) is not dict or value.keys() != {item.name for item in fields(SyntheticBinding)}:
        raise BoundaryError()
    return SyntheticBinding(**value)


def synthetic_binding(role):
    return SyntheticBinding(role=role, **_BINDING)


def authorize(binding, action):
    if type(binding) is not SyntheticBinding or type(action) is not str:
        raise BoundaryError()
    binding.__post_init__()
    if action not in _ACTIONS[binding.role]:
        raise BoundaryError()


def validate_private_path(path, *, kind="directory"):
    """기존 경로를 nofollow descriptor로 검사하고 content는 읽지 않는다.

모든 symlink component와 repository 하위를 거부한다. 마지막 객체의 현재
UID·정확한0700/0600·파일 hardlink1을 요구한다. ACL/암호화 증명은 아니다.
"""
    descriptor = None
    try:
        candidate = Path(path)
        if (not candidate.is_absolute() or candidate.anchor != "/" or ".." in candidate.parts or
                candidate == _ROOT or _ROOT in candidate.parents or
                kind not in ("directory", "file")):
            raise BoundaryError()
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        repository_info = _ROOT.stat()
        for index, part in enumerate(candidate.parts[1:]):
            last = index == len(candidate.parts) - 2
            if last and kind == "file":
                parent = os.fstat(descriptor)
                if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
                    raise BoundaryError()
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            if not last or kind == "directory":
                flags |= os.O_DIRECTORY
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
            current = os.fstat(descriptor)
            if (current.st_dev, current.st_ino) == (repository_info.st_dev, repository_info.st_ino):
                raise BoundaryError()
        info = os.fstat(descriptor)
        directory = kind == "directory"
        if (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
                or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
                or (not directory and info.st_nlink != 1)):
            raise BoundaryError()
    except (OSError, TypeError, ValueError):
        raise BoundaryError("private_path_denied") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


class SyntheticController:
    """합성 controller 객체의 identity. 실제 사용자 신원 증명이 아니다."""

    def __init__(self, binding):
        authorize(binding, "synthetic.session")

    def new_liveness(self, *, clock=time.monotonic):
        return SyntheticLiveness(self, clock)


class SyntheticLiveness:
    """고정30초 합성 liveness. disconnect/만료 뒤 renew로 재개하지 않는다."""

    def __init__(self, controller, clock):
        if type(controller) is not SyntheticController:
            raise BoundaryError()
        self._controller = controller
        self._clock = clock
        self._last = None
        self._deadline = None
        self.state = "stopped"

    def _owner(self, controller):
        if controller is not self._controller:
            raise BoundaryError("controller_denied")

    def _now(self):
        try:
            now = self._clock()
            if (type(now) not in (int, float) or not math.isfinite(now) or now < 0
                    or (self._last is not None and now < self._last)
                    or not math.isfinite(now + 30)):
                raise ValueError()
        except Exception:
            self.state = "faulted"
            self._deadline = None
            raise BoundaryError("clock_invalid") from None
        self._last = now
        return now

    def resume(self, controller):
        self._owner(controller)
        now = self._now()
        self._deadline = now + 30
        self.state = "running"

    def check(self):
        now = self._now()
        if self.state == "running" and self._deadline is not None and now < self._deadline:
            return True
        if self.state == "running":
            self.state = "faulted"
            self._deadline = None
        return False

    def renew(self, controller):
        self._owner(controller)
        if not self.check():
            raise BoundaryError("session_inactive")
        self._deadline = self._last + 30

    def disconnect(self, controller):
        self._owner(controller)
        self.state = "paused"
        self._deadline = None
