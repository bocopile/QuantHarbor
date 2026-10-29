"""Q16 명시 UTC 구간의 합성 시장 달력. timezone 변환·I/O는 adapter 책임이다."""

from dataclasses import dataclass
import re

from .catalog import _contains, _no_overlap, _tuple_of, _window
from .primitives import ContractError, calendar_date, identifier, utc_instant


def timezone_name(value):
    if type(value) is not str or len(value) > 128 or not re.fullmatch(
            r"(?:UTC|[A-Za-z][A-Za-z0-9_+.-]*(?:/[A-Za-z0-9_+.-]+)+)", value, re.ASCII):
        raise ContractError()
    if any(part in (".", "..") for part in value.split("/")):
        raise ContractError()
    return value


@dataclass(frozen=True, slots=True)
class TradingSession:
    session_id: str
    trading_date: str
    kind: str
    starts_at: str
    ends_at: str
    known_at: str
    evidence_ref: str
    early_close: bool = False

    def __post_init__(self):
        identifier(self.session_id)
        identifier(self.evidence_ref)
        calendar_date(self.trading_date)
        if (type(self.kind) is not str or self.kind not in ("regular", "extended")
                or type(self.early_close) is not bool or (self.early_close and self.kind != "regular")):
            raise ContractError()
        start, end = _window(self.starts_at, self.ends_at)
        if end is None:
            raise ContractError()
        object.__setattr__(self, "starts_at", start)
        object.__setattr__(self, "ends_at", end)
        object.__setattr__(self, "known_at", utc_instant(self.known_at))


@dataclass(frozen=True, slots=True)
class TradingDay:
    trading_date: str
    starts_at: str
    ends_at: str
    status: str
    known_at: str
    evidence_ref: str
    sessions: tuple[TradingSession, ...]

    def __post_init__(self):
        calendar_date(self.trading_date)
        identifier(self.evidence_ref)
        start, end = _window(self.starts_at, self.ends_at)
        if end is None:
            raise ContractError()
        object.__setattr__(self, "starts_at", start)
        object.__setattr__(self, "ends_at", end)
        object.__setattr__(self, "known_at", utc_instant(self.known_at))
        _tuple_of(self.sessions, TradingSession)
        if (type(self.status) is not str or self.status not in ("open", "closed", "unknown")
                or (self.status == "open" and not any(item.kind == "regular" for item in self.sessions))
                or (self.status != "open" and self.sessions)
                or len({item.session_id for item in self.sessions}) != len(self.sessions)):
            raise ContractError()
        for session in self.sessions:
            if (session.trading_date != self.trading_date or session.starts_at < start or session.ends_at > end
                    or session.known_at > self.known_at):
                raise ContractError()
        _no_overlap(self.sessions, lambda item: 0, lambda item: item.starts_at, lambda item: item.ends_at)


@dataclass(frozen=True, slots=True)
class CalendarLookup:
    calendar_version: str
    status: str
    reason: str
    trading_date: str | None = None
    session: TradingSession | None = None

    def __post_init__(self):
        identifier(self.calendar_version)
        if (type(self.status) is not str or self.status not in ("session", "closed", "outside_session", "unknown")
                or type(self.reason) is not str or self.reason not in
                ("missing_or_unpublished", "explicit_day_status", "explicit_session", "no_active_session")):
            raise ContractError()
        if self.trading_date is not None:
            calendar_date(self.trading_date)
        if self.status == "session":
            if type(self.session) is not TradingSession or self.session.trading_date != self.trading_date:
                raise ContractError()
        elif self.session is not None or (self.status != "unknown" and self.trading_date is None):
            raise ContractError()

    @property
    def regular_session_eligible(self):
        """정규 세션 조건만. 금융 실행 권한·정책 관문을 대신하지 않는다."""
        return self.status == "session" and self.session is not None and self.session.kind == "regular"


@dataclass(frozen=True, slots=True)
class MarketCalendar:
    calendar_version: str
    venue_id: str
    timezone_id: str
    rules_version: str
    rules_sha256: str
    coverage_start: str
    coverage_end: str
    known_at: str
    source_ref: str
    days: tuple[TradingDay, ...]
    environment: str = "synthetic"
    schema_version: int = 1

    def __post_init__(self):
        for value in (self.calendar_version, self.venue_id, self.rules_version, self.source_ref):
            identifier(value)
        timezone_name(self.timezone_id)
        if type(self.rules_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", self.rules_sha256):
            raise ContractError()
        calendar_date(self.coverage_start)
        calendar_date(self.coverage_end)
        if (self.coverage_start >= self.coverage_end or type(self.environment) is not str
                or self.environment != "synthetic" or type(self.schema_version) is not int or self.schema_version != 1):
            raise ContractError()
        object.__setattr__(self, "known_at", utc_instant(self.known_at))
        _tuple_of(self.days, TradingDay)
        if len({item.trading_date for item in self.days}) != len(self.days):
            raise ContractError()
        session_ids = [session.session_id for day in self.days for session in day.sessions]
        if len(set(session_ids)) != len(session_ids):
            raise ContractError()
        for day in self.days:
            if not self.coverage_start <= day.trading_date < self.coverage_end:
                raise ContractError()
        _no_overlap(self.days, lambda item: 0, lambda item: item.starts_at, lambda item: item.ends_at)

    def lookup(self, instant, *, knowledge_cutoff):
        moment, cutoff = utc_instant(instant), utc_instant(knowledge_cutoff)
        unknown = CalendarLookup(self.calendar_version, "unknown", "missing_or_unpublished")
        if self.known_at > cutoff:
            return unknown
        matches = [item for item in self.days if _contains(item.starts_at, item.ends_at, moment)]
        if not matches or matches[0].known_at > cutoff:
            return unknown
        if len(matches) != 1:
            raise ContractError()
        day = matches[0]
        if day.status in ("closed", "unknown"):
            return CalendarLookup(self.calendar_version, day.status, "explicit_day_status", day.trading_date)
        for session in day.sessions:
            if _contains(session.starts_at, session.ends_at, moment):
                if session.known_at > cutoff:
                    return unknown
                return CalendarLookup(self.calendar_version, "session", "explicit_session", day.trading_date, session)
        return CalendarLookup(self.calendar_version, "outside_session", "no_active_session", day.trading_date)
