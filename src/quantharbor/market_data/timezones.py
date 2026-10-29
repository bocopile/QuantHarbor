"""명시 TZif bytes만 사용하는 Q16 변환 adapter. TZPATH fallback은 없다."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from io import BytesIO
import re
from zoneinfo import ZoneInfo

from quantharbor.domain.calendar import MarketCalendar, timezone_name
from quantharbor.domain.primitives import ContractError, identifier, utc_instant


@dataclass(frozen=True, slots=True)
class ExplicitTimezone:
    timezone_id: str
    rules_version: str
    content_sha256: str
    coverage_start: str
    coverage_end: str
    known_at: str
    tzif_bytes: bytes = field(repr=False)
    _zone: object = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        timezone_name(self.timezone_id)
        identifier(self.rules_version)
        if (type(self.tzif_bytes) is not bytes or not 0 < len(self.tzif_bytes) <= 1048576
                or type(self.content_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256)
                or sha256(self.tzif_bytes).hexdigest() != self.content_sha256):
            raise ContractError()
        start, end = utc_instant(self.coverage_start), utc_instant(self.coverage_end)
        if start >= end:
            raise ContractError()
        object.__setattr__(self, "coverage_start", start)
        object.__setattr__(self, "coverage_end", end)
        object.__setattr__(self, "known_at", utc_instant(self.known_at))
        try:
            zone = ZoneInfo.from_file(BytesIO(self.tzif_bytes), key=self.timezone_id)
        except Exception:
            raise ContractError() from None
        object.__setattr__(self, "_zone", zone)

    def _available(self, cutoff):
        if self.known_at > utc_instant(cutoff):
            raise ContractError()

    def _covered(self, instant):
        if not self.coverage_start <= instant < self.coverage_end:
            raise ContractError()

    def to_local(self, instant, *, knowledge_cutoff):
        self._available(knowledge_cutoff)
        normalized = utc_instant(instant)
        self._covered(normalized)
        return datetime.fromisoformat(normalized).astimezone(self._zone)

    def _candidates(self, wall):
        candidates = {}
        for fold in (0, 1):
            instant = wall.replace(tzinfo=self._zone, fold=fold).astimezone(UTC)
            returned = instant.astimezone(self._zone)
            if returned.replace(tzinfo=None) == wall and returned.fold == fold:
                candidates[fold] = utc_instant(instant)
        return candidates

    def resolve_local(self, wall_time, *, knowledge_cutoff, fold=None):
        """zone 문맥의 offset 없는 명시 wall 문자열. gap은 거부, fold는 선택 명시."""
        self._available(knowledge_cutoff)
        if (type(wall_time) is not str or not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?", wall_time)
                or (fold is not None and (type(fold) is not int or fold not in (0, 1)))):
            raise ContractError()
        try:
            candidates = self._candidates(datetime.fromisoformat(wall_time))
        except (ValueError, OverflowError):
            raise ContractError() from None
        if not candidates or (fold is None and len(candidates) != 1) or (fold is not None and fold not in candidates):
            raise ContractError()
        instant = candidates[next(iter(candidates)) if fold is None else fold]
        self._covered(instant)
        return instant

    def validate_calendar(self, calendar):
        """명시 day 구간이 이 규칙의 현지 자정 경계인지 metadata와 함께 확인한다."""
        if (type(calendar) is not MarketCalendar or
                (calendar.timezone_id, calendar.rules_version, calendar.rules_sha256) !=
                (self.timezone_id, self.rules_version, self.content_sha256)
                or calendar.known_at < self.known_at):
            raise ContractError()
        try:
            for day in calendar.days:
                if day.starts_at < self.coverage_start or day.ends_at > self.coverage_end:
                    raise ContractError()
                local_date = date.fromisoformat(day.trading_date)
                # 일반 자정은 한 값, 반복 자정은 명시 UTC의 첫 경계만 허용한다.
                for instant, boundary_date in ((day.starts_at, local_date),
                                               (day.ends_at, local_date + timedelta(days=1))):
                    choices = self._candidates(datetime.combine(boundary_date, time()))
                    if not choices or instant != min(choices.values()):
                        raise ContractError()
        except (ValueError, OverflowError):
            raise ContractError() from None

    def lookup_calendar(self, calendar, instant, *, knowledge_cutoff):
        """주 조회 진입점: rule binding/현지 날짜를 검증한 뒤 UTC 사실을 조회한다."""
        self.validate_calendar(calendar)
        return calendar.lookup(instant, knowledge_cutoff=knowledge_cutoff)
