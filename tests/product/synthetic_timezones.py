"""TZPATH/실제 tzdb 파일을 읽지 않고 만드는 작은 TZif v1 합성 fixture."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import struct

from quantharbor.market_data.timezones import ExplicitTimezone


KNOWN = "2023-12-01T00:00:00Z"
CUTOFF = "2025-01-01T00:00:00Z"


def tzif_bytes(offsets, transitions=(), abbreviations=b"SYN\0"):
    # transitions: (UTC datetime, new type index). 권리/완전성 있는 배포 자료가 아니다.
    header = b"TZif\0" + b"\0" * 15 + struct.pack(
        ">6l", 0, 0, 0, len(transitions), len(offsets), len(abbreviations))
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    stamps = b"".join(struct.pack(
        ">l", (instant - epoch) // timedelta(seconds=1)) for instant, _ in transitions)
    indices = bytes(index for _, index in transitions)
    types = b"".join(struct.pack(
        ">lBB", offset, is_dst, abbreviation) for offset, is_dst, abbreviation in offsets)
    return header + stamps + indices + types + abbreviations


def synthetic_timezone(kind):
    if kind == "KR":
        raw = tzif_bytes(((9 * 3600, 0, 0),), abbreviations=b"KST\0")
        name = "Asia/Seoul"
    elif kind == "US":
        raw = tzif_bytes(((-5 * 3600, 0, 0), (-4 * 3600, 1, 4)),
                         ((datetime(2024, 3, 10, 7, tzinfo=UTC), 1),
                          (datetime(2024, 11, 3, 6, tzinfo=UTC), 0)), b"EST\0EDT\0")
        name = "America/New_York"
    else:
        raise ValueError("synthetic_fixture_kind")
    return ExplicitTimezone(name, "synthetic-rules-2024-v1", sha256(raw).hexdigest(),
                            "2023-12-31T00:00:00Z", "2025-01-02T00:00:00Z", KNOWN, raw)
