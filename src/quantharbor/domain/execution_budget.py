"""Q27 논리 canonical/index 예산. PostgreSQL disk/WAL/RSS 추정이 아니다."""
from dataclasses import dataclass
import json

from .execution import ExecutionDenied
from .valuation import number

MIB = 1048576
TOTAL_RECORDS, TOTAL_BYTES = 1024, 64 * MIB
OWNER_RECORDS, OWNER_BYTES = 384, 24 * MIB
COMMON_RECORDS, COMMON_BYTES = 128, 8 * MIB
SOURCE_BYTES = 8 * MIB
CATEGORY_RECORDS = {'base': 32, 'broker': 64, 'ledger': 192, 'control': 64, 'late': 32}
# Enforced by the SQL row/index meter, never assumed from an event multiplier.
LARGE_ROW_BYTES, SMALL_ROW_BYTES, INDEX_KEY_BYTES = 67584, 1024, 512


@dataclass(frozen=True, slots=True)
class Cost:
    records: int = 0
    bytes: int = 0

    def __post_init__(self):
        if type(self.records) is not int or type(self.bytes) is not int or min(self.records,self.bytes)<0:
            raise ExecutionDenied('invalid_contract')

    def __add__(self, other):
        return Cost(self.records+other.records,self.bytes+other.bytes)


def canonical_size(value):
    return len(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8'))


def row_cost(row, index_keys=()):
    """Count each logical row once and every persisted index's participating key."""
    if type(index_keys) is not tuple:
        raise ExecutionDenied()
    return Cost(1,canonical_size(row)+sum(canonical_size(key) for key in index_keys))


def remaining(actual, completion):
    """A completion ceiling is per owner/category; another owner cannot consume it."""
    if actual.records>completion.records or actual.bytes>completion.bytes:
        raise ExecutionDenied('capacity_exceeded')
    return Cost(completion.records-actual.records,completion.bytes-actual.bytes)


def owner_charge(actual, reserve):
    if set(actual)!=set(CATEGORY_RECORDS) or set(reserve)!=set(CATEGORY_RECORDS):
        raise ExecutionDenied()
    total=Cost()
    for category,limit in CATEGORY_RECORDS.items():
        charge=actual[category]+reserve[category]
        if charge.records>limit:
            raise ExecutionDenied('capacity_exceeded')
        total+=charge
    if total.records>OWNER_RECORDS or total.bytes>OWNER_BYTES:
        raise ExecutionDenied('capacity_exceeded')
    return total


def manifest_ledger_cost(facts):
    """Upper bound every fixed slot including reversal/journal and future inbox.

    Each first Q20 append: event1+journal2+decision1+projection1+outbox1+
    delivery1+inbox1=8. Replacement append adds reversal1+journal2=11.
    Fee/tax branches can each append independently. Unknown-cost slots reserve
    no fabricated append; a later complete revision reserves its own append.
    Sorting revision dependencies also covers reverse arrival/quarantine/replay.
    """
    if type(facts) is not tuple or len(facts)>8:
        raise ExecutionDenied('capacity_exceeded')
    streams={}
    total=Cost()
    for f in sorted(facts,key=lambda x:(x.execution_id,x.stream_sequence,x.revision)):
        if f.kind not in ('fill','settlement'):
            continue
        key=(f.execution_id,f.stream_sequence if f.semantics=='cumulative' else 0)
        if f.kind=='settlement':
            components=(False,)
        elif f.fee is None or f.tax is None:
            continue
        else:
            prior=streams.get(key,{})
            components=tuple(prior.get(k,False) for k in ('trade','fee','tax')
                if k=='trade' or number(getattr(f,k))>0)
            streams[key]={k:True for k in ('trade','fee','tax')
                if k=='trade' or number(getattr(f,k))>0 or prior.get(k,False)}
        for correction in components:
            # event/decision/projection large rows; other rows <=1024;
            # 13 index entries first append, 19 with reversal, each <=512.
            large,small,indexes=(4,7,19) if correction else (3,5,13)
            total+=Cost(large+small,large*LARGE_ROW_BYTES+small*SMALL_ROW_BYTES+indexes*INDEX_KEY_BYTES)
    return total


def admit_manifest(facts):
    cost=manifest_ledger_cost(facts)
    if cost.records>CATEGORY_RECORDS['ledger'] or cost.bytes>OWNER_BYTES:
        raise ExecutionDenied('capacity_exceeded')
    return cost
