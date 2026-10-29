"""Q21 합성 평가 API. Q17 증빙 재생/조회와 Q20 projection을 소비한다."""
from dataclasses import replace
from datetime import datetime, timedelta

from quantharbor.application.market_ingest import replay_storage, select_view, context_refs
from quantharbor.domain.ledger import exact, hash_record
from quantharbor.domain.market_data import (FXObservation, PriceBar, RecordRefSet, RightsGrant, item_ref,
                                          record_hash)
from quantharbor.domain.market_storage import StorageBundle, evidence_index, summary_for
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.valuation import (
    MAX_INPUTS, ECONOMIC_CASH, BrokerBatchInspection, CashValuation, CurrencyValuation,
    HoldingValuation, MarketProof, PortfolioSnapshot, ReconciliationPolicy, ValuationPolicy,
    ValuationResult, bind_projection, compare_statement, finite, number, quantize,
    snapshot_manifest, snapshot_refs, ledger_reasons, validate_snapshot_storage,
)
from quantharbor.ports.valuation import MarketDatasetInput


def _market_inputs(inputs, request, policy):
    if type(inputs) is not tuple or len(inputs) > MAX_INPUTS:
        raise ContractError()
    datasets = {}
    for supplied in inputs:
        exact(supplied, MarketDatasetInput)
        supplied = replace(supplied)
        bundle = supplied.bundle
        # Canonical reconstruction validates every nested registered field/hash before replay.
        exact(bundle, StorageBundle)
        record_hash(bundle.descriptor)
        for receipt in bundle.receipts:
            record_hash(receipt)
        for item in bundle.evidence:
            record_hash(item.revision)
            record_hash(item.observation)
        state, envelope = replay_storage(bundle.descriptor, bundle.receipts, bundle.evidence,
            catalog=supplied.catalog, calendar=supplied.calendar, timezone=supplied.timezone)
        summary = summary_for(state, envelope)
        if state != bundle.state or envelope != bundle.envelope or summary != bundle.summary:
            raise ContractError()
        req = bundle.descriptor.request
        key = req.source_id, req.dataset_id, req.dataset_version
        if key in datasets:
            raise ContractError()
        rights = supplied.current_rights
        exact(rights, RightsGrant)
        if key != (rights.source_id, rights.dataset_id, rights.dataset_version):
            raise ContractError()
        # Rights are checked at consumption, including store permission for the new snapshot.
        view = select_view(state.revisions, as_of=request.as_of, knowledge_cutoff=request.knowledge_cutoff,
            rights=rights, at=request.evaluated_at, dataset_version=req.dataset_version,
            catalog=supplied.catalog, calendar=supplied.calendar, timezone=supplied.timezone,
            mode=request.projection_mode, original_cutoff=request.original_cutoff, purpose=request.purpose)
        held = set(view.held_reasons)
        if not rights.allows(at=request.evaluated_at, purpose='store', source_id=req.source_id,
                             dataset_id=req.dataset_id, dataset_version=req.dataset_version):
            held.add('store_rights_blocked')
        if bundle.descriptor.evaluated_at > request.knowledge_cutoff or req.knowledge_cutoff > request.knowledge_cutoff:
            held.add('market_evidence_after_cutoff')
        datasets[key] = supplied, state, envelope, summary, view, tuple(sorted(held))
    selections = {x.series for x in policy.prices} | {x.series for x in policy.fx}
    proofs, usable = [], {}
    for selection in sorted(selections, key=lambda x: (*x.dataset_key, x.series_id)):
        found = datasets.get(selection.dataset_key)
        if found is None:
            continue
        supplied, state, envelope, summary, view, held = found
        req = supplied.bundle.descriptor.request
        if selection.series_id not in req.scope.series_ids:
            # No arbitrary series selection outside the fetched scope.
            continue
        proof = MarketProof(selection, record_hash(supplied.bundle.descriptor),
            tuple(record_hash(x) for x in supplied.bundle.receipts), record_hash(evidence_index(supplied.bundle.evidence)),
            record_hash(envelope), record_hash(summary),
            RecordRefSet(1, 'synthetic', tuple(item_ref(x) for x in state.revisions.items)).records,
            view.selected,
            context_refs(supplied.catalog, supplied.calendar, supplied.timezone), supplied.current_rights,
            envelope.quality, req.scope, held)
        proofs.append(proof)
        usable[selection] = supplied, view, proof
    # All supplied datasets must be chosen explicitly; unused inputs cannot silently alter IDs.
    if set(datasets) - {x.dataset_key for x in selections}:
        raise ContractError()
    if sum(len(x.bundle.evidence) for x in inputs) > MAX_INPUTS:
        raise ContractError()
    return tuple(proofs), usable


def _latest(selection, available, request, payload_type, max_age):
    found = available.get(selection)
    if found is None:
        return None, ('market_evidence_missing',)
    supplied, view, proof = found
    why = set(proof.held_reasons) | set(proof.quality.reasons)
    if not proof.usable:
        why.add('market_quality_incomplete')
        return None, tuple(sorted(why))
    candidates = [x for x in view.selected if x.revision.series_id == selection.series_id]
    if not candidates:
        return None, ('price_missing' if payload_type is PriceBar else 'fx_missing',)
    latest = max(x.revision.effective_at for x in candidates)
    matches = [x for x in candidates if x.revision.effective_at == latest]
    if len(matches) != 1:
        return None, ('latest_record_ambiguous',)
    item = matches[0]
    if type(item.revision.payload) is not payload_type:
        return None, ('market_payload_type_mismatch',)
    if datetime.fromisoformat(request.as_of) - datetime.fromisoformat(latest) > timedelta(seconds=max_age):
        return None, ('price_stale' if payload_type is PriceBar else 'fx_stale',)
    return item, ()


def value_projection(projection, request, market_inputs, policy):
    bind_projection(projection, request)
    exact(policy, ValuationPolicy)
    if policy.version != request.valuation_policy_version:
        raise ContractError()
    policy.quantum(request.base_currency)
    proofs, available = _market_inputs(market_inputs, request, policy)
    holdings = []
    for position in projection.holdings:
        selection = next((x.series for x in policy.prices if x.position.key == position.key), None)
        code, price, ref, value = None, None, None, None
        why = set()
        if selection is None:
            why.add('price_selection_missing')
        else:
            found = available.get(selection)
            if found is not None:
                supplied = found[0]
                mappings = [x for x in supplied.catalog.mappings if
                    (x.instrument_id, x.execution_venue_id, x.mapping_version, x.source_id) ==
                    (position.instrument_id, position.venue_id, position.mapping_version, selection.source_id)]
                resolutions = [supplied.catalog.resolve(x.source_id, x.source_code, x.listing_venue_id,
                    x.execution_venue_id, as_of=request.as_of, knowledge_cutoff=request.knowledge_cutoff) for x in mappings]
                resolutions = [x for x in resolutions if x is not None and x.eligible_for_initial_scope]
                if len(resolutions) == 1:
                    code = resolutions[0].instrument.currency
                else:
                    why.add('holding_identity_unknown')
            else:
                why.add('holding_identity_unknown')
            item, held = _latest(selection, available, request, PriceBar, policy.max_price_age_seconds)
            why.update(held)
            if item is not None:
                bar = item.revision.payload
                resolution = available[selection][0].catalog.resolve(selection.source_id, bar.source_code,
                    bar.listing_venue_id, bar.execution_venue_id, as_of=bar.ends_at, knowledge_cutoff=request.knowledge_cutoff)
                if bar.adjustment != 'raw':
                    why.add('adjusted_price_rejected')
                if (bar.instrument_id, bar.execution_venue_id, bar.close.quantity_unit, bar.close.currency) != (
                        position.instrument_id, position.venue_id, position.unit, code) or resolution is None or resolution.mapping.mapping_version != position.mapping_version:
                    why.add('price_identity_mismatch')
                if bar.ends_at > request.as_of or number(bar.close.amount) <= 0:
                    why.add('price_time_or_value_invalid')
                if not why:
                    price, ref = bar.close, item_ref(item)
                    value = quantize(number(position.amount) * number(price.amount), policy.quantum(code))
        holdings.append(HoldingValuation(position, code, price, ref, value, tuple(sorted(why))))
    codes = sorted({x.currency for x in projection.cash_balances if x.account in ECONOMIC_CASH} |
                   {x.currency for x in holdings if x.currency is not None})
    balances = {(x.account, x.currency): x.amount for x in projection.cash_balances}
    cash, native = [], []
    all_reasons = ledger_reasons(projection) | {reason for x in holdings for reason in x.reason_codes}
    for code in codes:
        settled, payable, receivable = (balances.get((a, code), '0') for a in ECONOMIC_CASH)
        cash_reasons = ledger_reasons(projection)
        if number(settled) < 0 or number(payable) > 0 or number(receivable) < 0:
            cash_reasons.add('economic_balance_invalid')
        economic = finite(number(settled) + number(payable) + number(receivable))
        cash_row = CashValuation(code, settled, receivable, payable, economic, not cash_reasons, tuple(sorted(cash_reasons)))
        cash.append(cash_row)
        rows = [x for x in holdings if x.currency == code]
        subtotal = finite(number(economic) + sum((number(x.native_value) for x in rows if x.native_value is not None), number('0')))
        complete = cash_row.complete and all(x.native_value is not None for x in rows)
        why = cash_reasons | {reason for x in rows for reason in x.reason_codes}
        fx, fx_ref, direction, base = None, None, 'unknown', None
        if code == request.base_currency:
            direction, base = 'identity', quantize(number(subtotal), policy.quantum(request.base_currency))
        else:
            selection = next((x.series for x in policy.fx if x.native_currency == code), None)
            if selection is None:
                why.add('fx_selection_missing')
            else:
                item, held = _latest(selection, available, request, FXObservation, policy.max_fx_age_seconds)
                why.update(held)
                if item is not None:
                    observed_fx = item.revision.payload.fx
                    pair = observed_fx.base_currency, observed_fx.quote_currency
                    if pair == (code, request.base_currency):
                        direction = 'multiply'
                    elif pair == (request.base_currency, code):
                        direction = 'divide'
                    else:
                        why.add('fx_pair_mismatch')
                    if direction != 'unknown':
                        fx, fx_ref = observed_fx, item_ref(item)
                        converted = number(subtotal) * number(fx.rate) if direction == 'multiply' else number(subtotal) / number(fx.rate)
                        base = quantize(converted, policy.quantum(request.base_currency))
        all_reasons.update(why)
        native.append(CurrencyValuation(code, subtotal, complete, fx, fx_ref, direction, base, tuple(sorted(why))))
    known = finite(sum((number(x.base_value) for x in native if x.base_value is not None), number('0')))
    complete = projection.complete and not all_reasons and all(x.native_value is not None for x in holdings) and all(x.complete and x.base_value is not None for x in native)
    return ValuationResult(1, 'synthetic', projection, request, policy, hash_record(projection), hash_record(request),
        hash_record(policy), proofs, tuple(holdings), tuple(cash), tuple(native), known, known if complete else None,
        complete, tuple(sorted(all_reasons)))


def reconcile(projection, synthetic_statement, request, policy):
    return compare_statement(projection, synthetic_statement, request, policy)


def inspect_broker_batch(batch, request):
    from quantharbor.domain.broker_read import BrokerReadBatch
    from quantharbor.domain.valuation import ValuationRequest
    exact(batch, BrokerReadBatch)
    exact(request, ValuationRequest)
    batch_hash = record_hash(batch)  # Deep reconstruction; never accepts a forged complete flag.
    result = batch.result
    if result.account_ref != request.account_ref or result.finished_at > request.knowledge_cutoff:
        raise ContractError()
    why = {'mapping_unknown', 'source_number_semantics_unverified', 'settlement_inclusion_unknown',
           'reservation_inclusion_unknown', 'source_as_of_unknown', 'temporal_consistency_insufficient',
           'scope_not_entire_account'} | set(batch.reason_codes)
    if not result.complete or result.status != 'success':
        why.add('source_incomplete')
    return BrokerBatchInspection(1, 'synthetic', hash_record(request), batch_hash, batch.request_hash,
        result.query_id, result.account_ref, result.status, result.complete, result.source_error,
        result.queried_scope, batch.missing_scope, batch.reason_codes, result.started_at,
        result.finished_at, 'incomplete', tuple(sorted(why)))


def build_snapshot(projection, request, market_inputs, policy, reconciliation_policy, repository, *,
                   statement=None, valuation=None, reconciliation=None, broker_batch=None, broker_inspection=None):
    """입력에서 다시 산출해 supplied 결과를 검증하고 predecessor 조회 후 append한다."""
    calculated = value_projection(projection, request, market_inputs, policy)
    validate_snapshot_storage(calculated)
    compared = reconcile(projection, statement, request, reconciliation_policy)
    inspected = inspect_broker_batch(broker_batch, request) if broker_batch is not None else None
    for supplied, expected in ((valuation, calculated), (reconciliation, compared), (broker_inspection, inspected)):
        if supplied is not None:
            if expected is None or type(supplied) is not type(expected) or hash_record(supplied) != hash_record(expected):
                raise ContractError()
    if ((valuation is not None and valuation != calculated) or
            (reconciliation is not None and reconciliation != compared) or
            (broker_inspection is not None and broker_inspection != inspected)):
        raise ContractError()
    if request.supersedes_snapshot_id is not None:
        predecessor = repository.get(request.supersedes_snapshot_id, environment=request.environment, account_ref=request.account_ref)
        validate_predecessor(predecessor, request)
    manifest = snapshot_manifest(calculated, compared, reconciliation_policy, inspected)
    snapshot = PortfolioSnapshot(1, 'synthetic', 'snapshot:' + hash_record(manifest), request.account_ref,
        projection.ledger_cursor, 1, policy.version, snapshot_refs(calculated, compared, reconciliation_policy, inspected),
        request.as_of, request.knowledge_cutoff, request.projection_mode, request.supersedes_snapshot_id,
        calculated.holdings, calculated.cash_by_currency, (),
        compared.status if compared.full_account_balances_matched or compared.status != 'matched' else 'incomplete',
        'complete' if calculated.complete else 'incomplete', request.evaluated_at, request.base_currency,
        calculated.projection_hash, calculated.policy_hash, hash_record(reconciliation_policy), calculated,
        compared, reconciliation_policy, inspected, manifest)
    return repository.append(snapshot)


def validate_predecessor(predecessor, request):
    if predecessor is None:
        raise ContractError()
    exact(predecessor, PortfolioSnapshot)
    prior = predecessor.valuation.request
    if (prior.environment, prior.account_ref, prior.as_of, prior.scope, prior.base_currency) != (
            request.environment, request.account_ref, request.as_of, request.scope, request.base_currency):
        raise ContractError()
    if (request.knowledge_cutoff < prior.knowledge_cutoff or request.evaluated_at < prior.evaluated_at
            or request.ledger_cursor < prior.ledger_cursor):
        raise ContractError()
    if request.projection_mode == 'restated' and (request.original_cutoff != prior.knowledge_cutoff or request.knowledge_cutoff <= prior.knowledge_cutoff):
        raise ContractError()
