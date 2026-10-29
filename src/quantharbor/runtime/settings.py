"""합성 전용 설정. 구성 검사는 실행 자원의 기술적 격리 증명이 아니다.

파일을 읽어 검증할 뿐 디렉터리/DB/세션/스케줄러/외부 연결을 만들지 않는다.
자원 한도는 실행기가 강제해야 하며 이 모듈은 값을 검증한다.
max_cpu_seconds는 프로세스별 CPU 시간이다. Q14 고정 정책 runner는 별도
CPU quota와 wall 상한을 적용하며 이 파일의 임의 변경을 동적 적용하지 않는다.
"""

from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType
import tomllib


class SettingsError(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid synthetic configuration.")


_LIMIT_MAX = MappingProxyType({
    "max_input_bytes": 1048576,
    "max_output_bytes": 1048576,
    "max_cpu_seconds": 2,
    "max_memory_bytes": 134217728,
    "max_wall_seconds": 5,
    "max_disk_bytes": 16777216,
    "max_queue_depth": 1,
    "max_concurrency": 1,
    "liveness_timeout_seconds": 30,
})


@dataclass(frozen=True, slots=True)
class SyntheticLimits:
    max_input_bytes: int
    max_output_bytes: int
    max_cpu_seconds: int
    max_memory_bytes: int
    max_wall_seconds: int
    max_disk_bytes: int
    max_queue_depth: int
    max_concurrency: int
    max_retries: int
    liveness_timeout_seconds: int

    def __post_init__(self) -> None:
        for name, maximum in _LIMIT_MAX.items():
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise SettingsError()
        if type(self.max_retries) is not int or self.max_retries != 0:
            raise SettingsError()


_FIXED = MappingProxyType({
    "schema_version": 1,
    "environment": "synthetic",
    "binding_version": "synthetic-v1",
    "database_namespace": "qh_synthetic",
    "queue_namespace": "qh_synthetic",
    "new_cost_budget": 0,
    "live_enabled": False,
    "paper_enabled": False,
    "automation_enabled": False,
    "external_broker_enabled": False,
    "external_model_enabled": False,
    "external_reporting_enabled": False,
})


@dataclass(frozen=True, slots=True)
class SyntheticSettings:
    schema_version: int
    environment: str
    binding_version: str
    database_namespace: str
    queue_namespace: str
    new_cost_budget: int
    live_enabled: bool
    paper_enabled: bool
    automation_enabled: bool
    external_broker_enabled: bool
    external_model_enabled: bool
    external_reporting_enabled: bool
    limits: SyntheticLimits

    def __post_init__(self) -> None:
        for name, required in _FIXED.items():
            value = getattr(self, name)
            if type(value) is not type(required) or value != required:
                raise SettingsError()
        if type(self.limits) is not SyntheticLimits:
            raise SettingsError()
        self.limits.__post_init__()


def _check_keys(value: object, expected: set[str]) -> None:
    if type(value) is not dict or value.keys() != expected:
        raise SettingsError()


def settings_from_mapping(value: dict[str, object]) -> SyntheticSettings:
    try:
        _check_keys(value, {field.name for field in fields(SyntheticSettings)})
        limits = value["limits"]
        _check_keys(limits, {field.name for field in fields(SyntheticLimits)})
        return SyntheticSettings(**(value | {"limits": SyntheticLimits(**limits)}))
    except (TypeError, ValueError, KeyError):
        raise SettingsError() from None


def load_settings(path: str | Path) -> SyntheticSettings:
    """명시 파일 하나만 읽는다. env/home credential fallback은 없다."""
    try:
        with open(path, "rb") as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise SettingsError()
        return settings_from_mapping(tomllib.loads(raw.decode("utf-8")))
    except (OSError, ValueError, TypeError, RecursionError):
        raise SettingsError() from None
