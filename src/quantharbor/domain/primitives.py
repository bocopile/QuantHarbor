"""data-v1/serialization-v1의 정확한 저장 기본형.

연산·상품별 tick/lot·반올림 정책은 구현하지 않는다. 저장 정규화는
Decimal 연산을 사용하지 않아 호출자의 Decimal context에 의존하지 않는다.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
import re


class ContractError(ValueError):
    """입력 원문을 포함하지 않는 계약 오류."""

    def __init__(self) -> None:
        super().__init__("Invalid contract value.")


_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", re.ASCII)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", re.ASCII)
_INSTANT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
    re.ASCII,
)


def decimal_string(value: str) -> str:
    """80자 입력·정규형 정수20/소수18자 한도를 정확히 검사한다."""
    if type(value) is not str or len(value) > 80 or not _DECIMAL.fullmatch(value):
        raise ContractError()
    negative = value.startswith("-")
    whole, _, fraction = value.removeprefix("-").partition(".")
    fraction = fraction.rstrip("0")
    if len(whole) > 20 or len(fraction) > 18:
        raise ContractError()
    if whole == "0" and not fraction:
        return "0"
    return ("-" if negative else "") + whole + ("." + fraction if fraction else "")


def identifier(value: str) -> str:
    """Q13 내부 참조: ASCII 문자/숫자 및 _ . : -, 최대128자."""
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise ContractError()
    return value


def currency(value: str) -> str:
    if type(value) is not str or value not in ("KRW", "USD"):
        raise ContractError()
    return value


def utc_instant(value: str | datetime) -> str:
    """aware instant를 고정된 UTC microsecond 표현으로 변환한다."""
    try:
        if type(value) is str:
            if not _INSTANT.fullmatch(value):
                raise ContractError()
            instant = datetime.fromisoformat(value)
        elif type(value) is datetime:
            instant = value
        else:
            raise ContractError()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ContractError()
        normalized = instant.astimezone(UTC)
        return (
            f"{normalized.year:04d}-{normalized.month:02d}-{normalized.day:02d}T"
            f"{normalized.hour:02d}:{normalized.minute:02d}:{normalized.second:02d}."
            f"{normalized.microsecond:06d}Z"
        )
    except (ValueError, OverflowError, TypeError):
        raise ContractError() from None


def calendar_date(value: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ContractError()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ContractError() from None


@dataclass(frozen=True, slots=True)
class Money:
    amount: str
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", decimal_string(self.amount))
        currency(self.currency)


@dataclass(frozen=True, slots=True)
class Quantity:
    amount: str
    instrument_id: str
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", decimal_string(self.amount))
        identifier(self.instrument_id)
        identifier(self.unit)


@dataclass(frozen=True, slots=True)
class Price:
    amount: str
    currency: str
    instrument_id: str
    quantity_unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", decimal_string(self.amount))
        currency(self.currency)
        identifier(self.instrument_id)
        identifier(self.quantity_unit)


@dataclass(frozen=True, slots=True)
class FX:
    """rate는 base 1단위당 quote 금액. 실제 환산/반올림은 제공하지 않는다."""

    base_currency: str
    quote_currency: str
    rate: str
    as_of: str
    source_id: str

    def __post_init__(self) -> None:
        currency(self.base_currency)
        currency(self.quote_currency)
        rate = decimal_string(self.rate)
        if rate == "0" or rate.startswith("-"):
            raise ContractError()
        object.__setattr__(self, "rate", rate)
        object.__setattr__(self, "as_of", utc_instant(self.as_of))
        identifier(self.source_id)
