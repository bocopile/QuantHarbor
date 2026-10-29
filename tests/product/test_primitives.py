from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Inexact, localcontext
import unittest

from quantharbor.domain.primitives import (
    ContractError, FX, Money, Price, Quantity, calendar_date, decimal_string, utc_instant,
)


class DecimalTests(unittest.TestCase):
    def test_canonical_equivalence_and_negative_zero(self):
        for raw, expected in (("1.23000", "1.23"), ("-0.0000", "0"),
                              ("0.00100", "0.001"), ("-12.0", "-12")):
            with self.subTest(raw=raw):
                self.assertEqual(decimal_string(raw), expected)

    def test_storage_boundaries_are_exact_and_context_independent(self):
        boundary = "99999999999999999999.999999999999999999"
        with localcontext() as context:
            context.prec = 2
            context.traps[Inexact] = True
            self.assertEqual(decimal_string(boundary), boundary)
            self.assertEqual(Money(boundary, "USD").amount, boundary)
            self.assertEqual(decimal_string("1." + "0" * 78), "1")
        for invalid in ("1" * 21, "0." + "0" * 18 + "1", "1." + "0" * 79):
            with self.subTest(invalid=invalid), self.assertRaises(ContractError):
                decimal_string(invalid)

    def test_rejects_numeric_and_noncanonical_grammars(self):
        invalid = (1, 1.0, True, False, None, float("nan"), float("inf"),
                   "", " 1", "1 ", "+1", "01", "-01", "1.", ".1", "1e2",
                   "NaN", "Infinity", "１", "١", "0\n", "\ud800")
        for value in invalid:
            with self.subTest(value=repr(value)), self.assertRaises(ContractError):
                decimal_string(value)

    def test_immutable_units_and_positive_fx(self):
        money = Money("1.00", "USD")
        self.assertEqual(money.amount, "1")
        with self.assertRaises(FrozenInstanceError):
            money.amount = "2"
        self.assertEqual(Quantity("-2.50", "syn.instrument.001", "share").amount, "-2.5")
        self.assertEqual(Price("1.230", "KRW", "syn.instrument.001", "share").amount, "1.23")
        for value in ("0", "-0.0", "-1"):
            with self.subTest(rate=value), self.assertRaises(ContractError):
                FX("USD", "KRW", value, "2026-01-01T00:00:00Z", "synthetic")
        for currency in ("EUR", "usd", None, True):
            with self.subTest(currency=currency), self.assertRaises(ContractError):
                Money("1", currency)
        for instrument in ("", "a/b", "a b", "a" * 129, "가", "\ud800"):
            with self.subTest(instrument=repr(instrument)), self.assertRaises(ContractError):
                Quantity("1", instrument, "share")
        self.assertEqual(Quantity("1", "001", "share").instrument_id, "001")


class InstantTests(unittest.TestCase):
    def test_offsets_datetime_and_microseconds(self):
        expected = "2026-10-23T00:00:00.123400Z"
        self.assertEqual(utc_instant("2026-10-23T09:00:00.1234+09:00"), expected)
        self.assertEqual(utc_instant("2026-10-23T00:00:00.123400Z"), expected)
        self.assertEqual(utc_instant(datetime(2026, 10, 23, 9, 0, 0, 123400,
                                              tzinfo=timezone(timedelta(hours=9)))), expected)
        self.assertEqual(utc_instant(datetime(1, 1, 1, tzinfo=UTC)), "0001-01-01T00:00:00.000000Z")

    def test_invalid_precision_naive_leap_and_dates(self):
        invalid = ("2026-10-23T00:00:00.1234560Z", "2026-10-23T00:00:00",
                   "2026-10-23T00:00:60Z", "2026-02-30T00:00:00Z", "2026-10-23",
                   "2026-10-23T00:00:00+24:00", "0001-01-01T00:00:00+01:00",
                   datetime(2026, 10, 23), 0, True, None)
        for value in invalid:
            with self.subTest(value=repr(value)), self.assertRaises(ContractError):
                utc_instant(value)
        self.assertEqual(calendar_date("2024-02-29"), "2024-02-29")
        for value in ("2026-02-29", "2026-1-01", "2026-01-01Z", None):
            with self.subTest(value=value), self.assertRaises(ContractError):
                calendar_date(value)


if __name__ == "__main__":
    unittest.main()
