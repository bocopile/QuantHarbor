from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta
from hashlib import sha256
import unittest
from unittest.mock import patch

from quantharbor.domain.calendar import MarketCalendar, TradingDay, TradingSession
from quantharbor.domain.primitives import ContractError
from synthetic_timezones import CUTOFF, KNOWN, synthetic_timezone


def session(zone, day, start="09:30:00", end="16:00:00", kind="regular", early_close=False, known=KNOWN):
    return TradingSession("syn.session." + day + "." + start.replace(":", ""), day, kind,
                          zone.resolve_local(day + "T" + start, knowledge_cutoff=CUTOFF),
                          zone.resolve_local(day + "T" + end, knowledge_cutoff=CUTOFF),
                          known, "syn.session.evidence", early_close)


def trading_day(zone, day, *, status="open", sessions=None, known=KNOWN):
    tomorrow = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    if sessions is None:
        sessions = (session(zone, day, known=known),) if status == "open" else ()
    return TradingDay(day, zone.resolve_local(day + "T00:00:00", knowledge_cutoff=CUTOFF),
                      zone.resolve_local(tomorrow + "T00:00:00", knowledge_cutoff=CUTOFF),
                      status, known, "syn.day.evidence", sessions)


def calendar(zone, *days, **changes):
    values = dict(calendar_version="calendar-v1", venue_id="syn.venue", timezone_id=zone.timezone_id,
                  rules_version=zone.rules_version, rules_sha256=zone.content_sha256,
                  coverage_start="2024-01-01", coverage_end="2025-01-01", known_at=KNOWN,
                  source_ref="syn.calendar.source", days=tuple(days))
    return MarketCalendar(**(values | changes))


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.zone = synthetic_timezone("US")

    def lookup(self, calendar, instant, cutoff=CUTOFF):
        return self.zone.lookup_calendar(calendar, instant, knowledge_cutoff=cutoff)

    def test_holiday_missing_date_and_outside_coverage_are_distinct(self):
        closed = trading_day(self.zone, "2024-07-04", status="closed")
        unknown = trading_day(self.zone, "2024-07-05", status="unknown")
        value = calendar(self.zone, closed, unknown)
        self.assertEqual(self.lookup(value, "2024-07-04T16:00:00Z").status, "closed")
        self.assertEqual(self.lookup(value, "2024-07-05T16:00:00Z").status, "unknown")
        self.assertEqual(self.lookup(value, "2024-07-06T16:00:00Z").status, "unknown")
        self.assertEqual(self.lookup(value, "2023-07-04T16:00:00Z").status, "unknown")
        self.assertFalse(self.lookup(value, "2024-07-04T16:00:00Z").regular_session_eligible)

    def test_regular_extended_early_close_and_half_open_boundaries(self):
        regular = session(self.zone, "2024-11-29", end="13:00:00", early_close=True)
        extended = session(self.zone, "2024-11-29", start="13:00:00", end="14:00:00", kind="extended")
        value = calendar(self.zone, trading_day(self.zone, "2024-11-29", sessions=(regular, extended)))
        start = self.lookup(value, regular.starts_at)
        self.assertTrue(start.regular_session_eligible)
        self.assertTrue(start.session.early_close)
        end = self.lookup(value, regular.ends_at)
        self.assertEqual(end.session.kind, "extended")
        self.assertFalse(end.regular_session_eligible)
        self.assertEqual(self.lookup(value, extended.ends_at).status, "outside_session")
        self.assertEqual(start.session.session_id, regular.session_id)

    def test_us_dst_regular_session_utc_offsets_and_23_25_hour_days(self):
        before = session(self.zone, "2024-03-08")
        after = session(self.zone, "2024-03-11")
        self.assertEqual(before.starts_at, "2024-03-08T14:30:00.000000Z")
        self.assertEqual(after.starts_at, "2024-03-11T13:30:00.000000Z")
        value = calendar(self.zone, trading_day(self.zone, "2024-03-08"), trading_day(self.zone, "2024-03-11"))
        self.assertTrue(self.lookup(value, before.starts_at).regular_session_eligible)
        self.assertTrue(self.lookup(value, after.starts_at).regular_session_eligible)
        for day, hours in (("2024-03-10", 23), ("2024-11-03", 25)):
            record = trading_day(self.zone, day, status="closed")
            self.zone.validate_calendar(calendar(self.zone, record))
            self.assertEqual(datetime.fromisoformat(record.ends_at) - datetime.fromisoformat(record.starts_at),
                             timedelta(hours=hours))

    def test_korean_trading_date_is_not_the_utc_date(self):
        zone = synthetic_timezone("KR")
        regular = session(zone, "2024-01-02", start="09:00:00", end="15:30:00")
        value = calendar(zone, trading_day(zone, "2024-01-02", sessions=(regular,)))
        result = zone.lookup_calendar(value, "2024-01-01T16:00:00Z", knowledge_cutoff=CUTOFF)
        self.assertEqual(result.trading_date, "2024-01-02")
        self.assertEqual(result.status, "outside_session")
        self.assertEqual(regular.starts_at, "2024-01-02T00:00:00.000000Z")

    def test_calendar_and_day_knowledge_cutoffs_hide_unpublished_facts(self):
        day = trading_day(self.zone, "2024-03-08", known="2024-03-07T00:00:00Z")
        value = calendar(self.zone, day, known_at="2024-03-01T00:00:00Z")
        result = self.lookup(value, day.sessions[0].starts_at, "2024-03-06T23:59:59Z")
        self.assertEqual(result.status, "unknown")
        self.assertIsNone(result.trading_date)
        self.assertIsNone(result.session)
        self.assertTrue(self.lookup(value, day.sessions[0].starts_at, "2024-03-07T00:00:00Z").regular_session_eligible)
        self.assertEqual(self.lookup(value, day.starts_at, "2024-02-29T00:00:00Z").status, "unknown")

    def test_duplicate_overlapping_sessions_days_and_wrong_membership_are_rejected(self):
        first = trading_day(self.zone, "2024-03-08")
        with self.assertRaises(ContractError):
            calendar(self.zone, first, first)
        overlapping = replace(first.sessions[0], session_id="syn.other", kind="extended")
        with self.assertRaises(ContractError):
            replace(first, sessions=(first.sessions[0], overlapping))
        second = trading_day(self.zone, "2024-03-11")
        duplicate_id = replace(second.sessions[0], session_id=first.sessions[0].session_id)
        with self.assertRaises(ContractError):
            calendar(self.zone, first, replace(second, sessions=(duplicate_id,)))
        with self.assertRaises(ContractError):
            replace(first, sessions=(replace(first.sessions[0], trading_date="2024-03-09"),))
        with self.assertRaises(ContractError):
            calendar(self.zone, first, replace(second, starts_at=first.ends_at.replace("09", "08")))

    def test_main_entrypoint_rejects_rules_hash_timezone_or_local_day_mismatch(self):
        day = trading_day(self.zone, "2024-03-08")
        value = calendar(self.zone, day)
        shifted_start = (datetime.fromisoformat(day.starts_at) + timedelta(hours=1)).isoformat()
        invalid = (replace(value, rules_sha256="0" * 64), replace(value, timezone_id="Asia/Seoul"),
                   replace(value, rules_version="other-v1"),
                   replace(value, days=(replace(day, starts_at=shifted_start),)))
        for changed in invalid:
            with self.subTest(version=changed.calendar_version), self.assertRaises(ContractError):
                self.lookup(changed, day.sessions[0].starts_at)

    def test_immutability_types_enums_coverage_and_naive_inputs(self):
        day = trading_day(self.zone, "2024-03-08")
        value = calendar(self.zone, day)
        with self.assertRaises(FrozenInstanceError):
            value.calendar_version = "changed"
        for changes in (dict(days=[day]), dict(schema_version=True), dict(environment="live"),
                        dict(coverage_end="2024-03-08"), dict(rules_sha256=True)):
            with self.subTest(changes=list(changes)), self.assertRaises(ContractError):
                replace(value, **changes)
        for changes in (dict(status=True), dict(sessions=list(day.sessions)), dict(status="closed"),
                        dict(known_at="2023-11-01T00:00:00Z")):
            with self.subTest(changes=list(changes)), self.assertRaises(ContractError):
                replace(day, **changes)
        for changes in (dict(early_close=1), dict(kind=True), dict(kind="extended", early_close=True)):
            with self.subTest(changes=list(changes)), self.assertRaises(ContractError):
                replace(day.sessions[0], **changes)
        with self.assertRaises(ContractError):
            self.lookup(value, datetime(2024, 3, 8))
        with self.assertRaises(ContractError):
            self.lookup(value, day.starts_at, datetime(2024, 3, 8))


class ExplicitTimezoneTests(unittest.TestCase):
    def test_no_host_timezone_lookup_or_tzdata_fallback(self):
        with patch("zoneinfo._tzpath.find_tzfile", side_effect=AssertionError("host_tzpath_forbidden")), \
                patch("zoneinfo._common.load_tzdata", side_effect=AssertionError("tzdata_fallback_forbidden")):
            zone = synthetic_timezone("US")
            result = zone.to_local("2024-03-11T13:30:00Z", knowledge_cutoff=CUTOFF)
            self.assertEqual(result.hour, 9)
            self.assertEqual(result.minute, 30)

    def test_gap_ambiguous_fold_and_excess_precision_are_explicit(self):
        zone = synthetic_timezone("US")
        for wall, fold in (("2024-03-10T02:30:00", None), ("2024-11-03T01:30:00", None),
                           ("2024-03-11T09:30:00.1234567", None), ("2024-03-11T09:30:00", True),
                           ("2024-03-11T09:30:00", 1), (datetime(2024, 3, 11), None)):
            with self.subTest(fold=fold), self.assertRaises(ContractError):
                zone.resolve_local(wall, fold=fold, knowledge_cutoff=CUTOFF)
        self.assertEqual(zone.resolve_local("2024-11-03T01:30:00", fold=0, knowledge_cutoff=CUTOFF),
                         "2024-11-03T05:30:00.000000Z")
        self.assertEqual(zone.resolve_local("2024-11-03T01:30:00", fold=1, knowledge_cutoff=CUTOFF),
                         "2024-11-03T06:30:00.000000Z")

    def test_invalid_tzif_hash_coverage_and_unknown_rules_fail_closed(self):
        zone = synthetic_timezone("US")
        for changes in (dict(content_sha256="0" * 64), dict(tzif_bytes=bytearray(zone.tzif_bytes)),
                        dict(tzif_bytes=b"invalid", content_sha256=sha256(b"invalid").hexdigest()),
                        dict(coverage_end=zone.coverage_start)):
            with self.subTest(changes=list(changes)), self.assertRaises(ContractError):
                replace(zone, **changes)
        for instant, cutoff in ((zone.coverage_end, CUTOFF), ("2024-03-08T14:30:00Z", "2023-11-01T00:00:00Z"),
                                 (datetime(2024, 3, 8), CUTOFF)):
            with self.subTest(instant_type=type(instant).__name__), self.assertRaises(ContractError):
                zone.to_local(instant, knowledge_cutoff=cutoff)
        with self.assertRaises(FrozenInstanceError):
            zone.rules_version = "changed"


if __name__ == "__main__":
    unittest.main()
