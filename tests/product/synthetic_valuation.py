"""Q21 독립 합성 fixture. 실제 자료·계좌·원장 결과 복사로 기대값을 만들지 않는다."""
from dataclasses import asdict, replace
from hashlib import sha256
import json

from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.adapters.synthetic_market import SyntheticPageAdapter
from quantharbor.application.market_ingest import ingest
from quantharbor.domain.ledger import CashBalance, PositionDelta, hash_record
from quantharbor.domain.market_data import ExpectedEvent, FXObservation, IngestLimits
from quantharbor.domain.primitives import FX, utc_instant
from quantharbor.domain.valuation import (
    BalanceScope, CashTolerance, CurrencyQuantum, DOMAINS, FXSelection, PositionKey,
    PriceSelection, QuantityTolerance, ReconciliationPolicy, SeriesSelection,
    StatementSourceSnapshot, SyntheticAccountStatement, ValuationPolicy, ValuationRequest,
)
from quantharbor.ports.valuation import MarketDatasetInput
from synthetic_ledger import baseline as ledger_baseline, submission, cash_pair
from synthetic_market import (START, END, NOW, LATER, bar, context, item, page, price,
                              request as market_request, revision, rights, scope)

ACCOUNT = 'synthetic-account:valuation'
KEY = PositionKey('syn.instrument', 'syn.venue', 'mapping-v1', 'share')
HOLDING = PositionDelta(*KEY.key, '2')
SERIES = SeriesSelection('syn.source', 'syn.dataset', 'dataset-v1', 'syn.raw')
FX_SERIES = replace(SERIES, series_id='syn.fx')
WHOLE = BalanceScope('entire_account', (), ('KRW', 'USD'), tuple(sorted(DOMAINS)))


def request(**changes):
    values = dict(schema_version=1, environment='synthetic', account_ref=ACCOUNT, request_id='valuation-request',
        ledger_cursor=1,
        as_of=END, knowledge_cutoff=NOW, evaluated_at=NOW, projection_mode='as_known', base_currency='USD',
        purpose='research', valuation_policy_version='synthetic-valuation-v1',
        reconciliation_policy_version='synthetic-reconciliation-v1', scope=WHOLE)
    return ValuationRequest(**(values | changes))


def policy(*, fx=False, **changes):
    values = dict(schema_version=1, environment='synthetic', version='synthetic-valuation-v1',
        prices=(PriceSelection(KEY, SERIES),), fx=(FXSelection('USD', FX_SERIES),) if fx else (),
        quantums=(CurrencyQuantum('KRW', '1'), CurrencyQuantum('USD', '0.01')),
        max_price_age_seconds=3600, max_fx_age_seconds=3600)
    return ValuationPolicy(**(values | changes))


def reconciliation_policy(**changes):
    values = dict(schema_version=1, environment='synthetic', version='synthetic-reconciliation-v1',
        quantities=(QuantityTolerance('share', '0'),), cash=(CashTolerance('KRW', '0'), CashTolerance('USD', '0')))
    return ReconciliationPolicy(**(values | changes))


def price_item(amount='11', **revision_changes):
    p = price(amount)
    return item(revision(payload=bar(open=p, high=p, low=p, close=p), **revision_changes))


def fx_item(*, inverse=False, rate='1300'):
    fx = FX('KRW' if inverse else 'USD', 'USD' if inverse else 'KRW', rate, END, 'syn.source')
    r = revision(series_id='syn.fx', event_id='fx.event', payload=FXObservation(fx))
    return item(r, observation_id='obs.fx')


def market(*, records=None, current_rights=None, historical_rights=None, request_changes=None,
           scope_changes=None, page_changes=None, contexts=None):
    records = (price_item(),) if records is None else records
    series = tuple(sorted({x.revision.series_id for x in records} or {'syn.raw'}))
    expected = tuple(ExpectedEvent(x.revision.series_id, x.revision.event_id, x.revision.effective_at) for x in records)
    # Revisions of one event still have only one expected event.
    expected = tuple(dict.fromkeys(expected))
    qs = scope(**(dict(series_ids=series, expected=expected,
        coverage_kind='expected_records' if records else 'confirmed_empty') | (scope_changes or {})))
    req = market_request(**(dict(scope=qs) | (request_changes or {})))
    ctx = context() if contexts is None else contexts
    grant = rights() if historical_rights is None else historical_rights
    p = page(req, **(dict(items=records) | (page_changes or {})))
    result = ingest(req, SyntheticPageAdapter((p,)), limits=IngestLimits(max_age_seconds=3600),
                    rights=grant, evaluated_at=NOW, **ctx)
    return MarketDatasetInput(result.bundle, **ctx, current_rights=grant if current_rights is None else current_rights)


def ledger(*, holdings=(HOLDING,), cash='1000', seed=True):
    store = SyntheticLedger()
    if seed:
        opening = replace(ledger_baseline(), account_ref=ACCOUNT, effective_at=START,
            cash_legs=cash_pair('settled_cash', cash, 'opening_equity'), position_deltas=holdings)
        store.append(opening, recorded_at=START)
    return store


def projection(**changes):
    return ledger().replay(ACCOUNT, **(dict(as_of=END, knowledge_cutoff=NOW) | changes))


def statement(*, holdings=(HOLDING,), cash=None, source_changes=None, **changes):
    # 2 shares and USD1000 are independently declared source facts.
    if cash is None:
        cash = (CashBalance('settled_cash', 'USD', '1000'),)
    facts = dict(schema_version=1, environment='synthetic', account_ref=ACCOUNT, source_id='synthetic-statement',
        statement_id='statement-1', source_revision='revision-1', source_snapshot_id='source-snapshot-1',
        mapping_version='mapping-v1', semantics_version='economic-components-v1', scope=WHOLE,
        source_as_of=END, observed_at=NOW, ingested_at=NOW, holdings=holdings, cash=cash,
        evidence_refs=('synthetic-statement-evidence',))
    source = StatementSourceSnapshot(**(facts | (source_changes or {})))
    values = dict(schema_version=1, environment='synthetic', snapshot=source, source_snapshot_hash=hash_record(source),
        requested_scope=WHOLE, status='success', complete=True, temporal_consistency='source_snapshot',
        mapping_status='verified', omitted_means_zero=True, reason_codes=())
    return SyntheticAccountStatement(**(values | changes))


def unchecked_bytes(value):
    """복원 경계 공격용 bytes. 의도적으로 제품 검증기를 호출하지 않는다."""
    envelope = dict(schema_name=type(value).__name__, schema_version=1,
                    environment='synthetic', payload=asdict(value))
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def unchecked_hash(value):
    return sha256(b'QuantHarbor/qh-canonical-json-v1\n' + unchecked_bytes(value)).hexdigest()


def reseal_snapshot(snapshot):
    """변조 금액뿐 아니라 manifest/ID/refs까지 재계산하는 회귀 fixture."""
    v = snapshot.valuation
    object.__setattr__(snapshot, 'holdings', v.holdings)
    object.__setattr__(snapshot, 'cash_by_currency', v.cash_by_currency)
    object.__setattr__(snapshot, 'valuation_status', 'complete' if v.complete else 'incomplete')
    manifest = replace(snapshot.input_manifest, valuation_hash=unchecked_hash(v))
    object.__setattr__(snapshot, 'input_manifest', manifest)
    object.__setattr__(snapshot, 'snapshot_id', 'snapshot:' + unchecked_hash(manifest))
    refs = tuple(replace(ref, sha256=unchecked_hash(v.market_proofs[int(ref.ref.split(':')[1])]))
                 if ref.kind == 'market' else ref for ref in snapshot.data_refs)
    object.__setattr__(snapshot, 'data_refs', refs)
    return snapshot
