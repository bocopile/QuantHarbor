from dataclasses import FrozenInstanceError
import json
import unittest

from quantharbor.domain.primitives import ContractError, Money
from quantharbor.domain.serialization import (
    CANONICALIZATION_VERSION, CanonicalPayload, _encode, canonical_bytes, canonical_hash, parse_payload,
)


def wrapper(name="Money", **payload):
    return {"schema_name": name, "schema_version": 1, "environment": "synthetic",
            "payload": payload or {"amount": "1.2300", "currency": "USD"}}


def parsed(value):
    return parse_payload(json.dumps(value))


class CanonicalTests(unittest.TestCase):
    def test_fixed_golden_bytes_and_hash(self):
        value = parsed(wrapper())
        expected = (b'{"environment":"synthetic","payload":{"amount":"1.23","currency":"USD"},'
                    b'"schema_name":"Money","schema_version":1}')
        self.assertEqual(CANONICALIZATION_VERSION, "qh-canonical-json-v1")
        self.assertEqual(canonical_bytes(value), expected)
        # 고정 입력을 별도로 SHA-256 계산한 golden. 실행 시 기대값을 생성하지 않는다.
        self.assertEqual(canonical_hash(value), "b9edef941f3fcd6d5229ce2bf47128a5fb22268d52a042dd587c79b3b0fc15cd")

    def test_key_order_decimal_and_time_equivalence(self):
        first = wrapper()
        second = dict(reversed(list(first.items())))
        second["payload"] = {"currency": "USD", "amount": "1.23"}
        self.assertEqual(canonical_hash(parsed(first)), canonical_hash(parsed(second)))
        fx = wrapper("FX", base_currency="USD", quote_currency="KRW", rate="1.00",
                     as_of="2026-10-23T09:00:00.100+09:00", source_id="syn.source")
        other = json.loads(json.dumps(fx))
        other["payload"].update(rate="1", as_of="2026-10-23T00:00:00.100000Z")
        self.assertEqual(canonical_bytes(parsed(fx)), canonical_bytes(parsed(other)))
        self.assertEqual(canonical_hash(parsed(fx)), canonical_hash(parsed(other)))

    def test_environment_amount_currency_and_schema_changes_differ(self):
        baseline = canonical_hash(parsed(wrapper()))
        for environment in ("paper", "live"):
            value = wrapper()
            value["environment"] = environment
            self.assertNotEqual(canonical_hash(parsed(value)), baseline)
        for payload in ({"amount": "1.24", "currency": "USD"},
                        {"amount": "1.2300", "currency": "KRW"}):
            self.assertNotEqual(canonical_hash(parsed(wrapper(**payload))), baseline)
        self.assertNotEqual(canonical_hash(parsed(wrapper("Quantity", amount="1.23",
                                                        instrument_id="syn.001", unit="share"))), baseline)

    def test_fixed_string_escaping_unicode_and_array_order(self):
        raw = {"text": '\"\\\b\f\n\r\t\x00\x01\x0b\x1f/한é', "array": [1, True, None]}
        expected = (b'{"array":[1,true,null],"text":"\\\"\\\\\\b\\f\\n\\r\\t'
                    b'\\u0000\\u0001\\u000b\\u001f/' + "한é".encode() + b'"}')
        self.assertEqual(_encode(raw), expected)
        self.assertNotEqual(_encode([1, 2]), _encode([2, 1]))
        self.assertNotEqual(_encode("é"), _encode("e\u0301"))

    def test_duplicate_keys_at_both_levels_are_rejected(self):
        raw = json.dumps(wrapper())
        for bad in (raw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'),
                    raw.replace('"amount": "1.2300"', '"amount": "1", "amount": "1"'),
                    raw.replace('"amount": "1.2300"', '"amount": "1", "\\u0061mount": "1"')):
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                parse_payload(bad)

    def test_exact_schema_and_field_presence(self):
        for key, changed in (("schema_name", "OrderCandidate"), ("schema_name", "Unknown"),
                             ("schema_name", []), ("schema_version", 2), ("schema_version", True),
                             ("schema_version", "1"), ("environment", "invalid"),
                             ("environment", None), ("payload", None), ("payload", [])):
            value = wrapper()
            value[key] = changed
            with self.subTest(key=key, changed=changed), self.assertRaises(ContractError):
                parsed(value)
        for key in wrapper():
            value = wrapper()
            del value[key]
            with self.subTest(missing=key), self.assertRaises(ContractError):
                parsed(value)
        for level in ("wrapper", "payload"):
            value = wrapper()
            target = value if level == "wrapper" else value["payload"]
            target["unknown"] = "not-ignored"
            with self.subTest(level=level), self.assertRaises(ContractError):
                parsed(value)
        with self.assertRaises(ContractError):
            parsed(wrapper(currency="USD"))

    def test_float_nonfinite_bool_null_surrogate_and_oversize_fail(self):
        for amount in (1.0, True, False, None, 1, float("nan"), float("inf"),
                       -float("inf"), "NaN", "Infinity", "\ud800", "\udfff"):
            value = wrapper(amount=amount, currency="USD")
            with self.subTest(amount=repr(amount)), self.assertRaises(ContractError):
                parsed(value)
        for raw in (b"\xff", "\ufeff{}", "[]", "null", "1", "{" * 2000,
                    " " * 65537, b" " * 65537, None, True):
            with self.subTest(raw=repr(raw)[:80]), self.assertRaises(ContractError):
                parse_payload(raw)

    def test_hash_does_not_accept_dict_or_mutable_or_unregistered_payload(self):
        value = parsed(wrapper())
        with self.assertRaises(FrozenInstanceError):
            value.environment = "live"
        for invalid in (wrapper(), value.payload, b"{}", None):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ContractError):
                canonical_hash(invalid)
        with self.assertRaises(ContractError):
            CanonicalPayload("OrderCandidate", 1, "synthetic", Money("1", "USD"))
        with self.assertRaises(ContractError):
            CanonicalPayload("Money", 1, "synthetic", {"amount": "1", "currency": "USD"})
        forged = Money("1", "USD")
        object.__setattr__(forged, "amount", float("nan"))
        with self.assertRaises(ContractError):
            canonical_hash(CanonicalPayload("Money", 1, "synthetic", forged))


if __name__ == "__main__":
    unittest.main()
