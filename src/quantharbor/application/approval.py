"""Q26 application 경계와 Q24 재현. 실제 사용자 인증/주문은 제공하지 않는다."""
from dataclasses import asdict, fields, is_dataclass, replace
from hashlib import sha256
import json

from quantharbor.domain import approval as d
from quantharbor.domain.primitives import ContractError, utc_instant
from quantharbor.domain.target import TargetRef, ref as target_ref
from quantharbor.ports.approval import ApprovalSource
from quantharbor.runtime.boundary import authorize, synthetic_binding


def source_bytes(source):
    """실체를 포함한 입력 상한. timezone cache/lock/repository는 입력 계약에서 제외한다."""
    def plain(x):
        if is_dataclass(x):
            return {f.name: plain(getattr(x, f.name)) for f in fields(x) if f.init}
        if type(x) in (tuple, list):
            return [plain(v) for v in x]
        if type(x) is bytes:
            return {'bytes': x.hex()}
        if type(x) in (str, int, bool) or x is None:
            return x
        raise d.ApprovalDenied('invalid_contract')
    raw = json.dumps(plain((source.request, source.inputs, source.artifacts)),
                     sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    if len(raw) > 8388608:
        raise d.ApprovalDenied('capacity_exceeded')
    return raw


def validate_source(source, candidate_ref, *, at, generation, require_live=True):
    """캐시 없이 매번 과거 Q24 재현과 모든 현재 소비 권리를 따로 확인한다."""
    from quantharbor.application.target import build_target, render_candidate
    from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
    if type(source) is not ApprovalSource or type(candidate_ref) is not TargetRef:
        raise d.ApprovalDenied('source_unresolved')
    authorize(synthetic_binding('research'), 'synthetic.compute')
    at = utc_instant(at)
    raw = source_bytes(source)
    i, req, a = source.inputs, source.request, source.artifacts
    if req.environment != 'synthetic':
        raise d.ApprovalDenied('unsupported_environment')
    if req.authority_generation != generation:
        raise d.ApprovalDenied('generation_mismatch')
    if at < req.evaluated_at or require_live and at >= req.expires_at:
        raise d.ApprovalDenied('expired')
    points = (i.current, *i.risk_points, *i.boundary_inputs, *i.daily_usage_inputs)
    refs, grants = [], []
    resolved_refs = set(candidate_ref for candidate_ref in a.plan.body.input_refs)
    resolved_refs.update(('event', x.body.event_id) for x in i.events)
    resolved_refs.update(('cost', x.trade.ref) for x in i.costs)
    resolved_refs.update(('obligation', x.source_id) for x in i.obligation_sources)
    for p in points:
        resolved_refs.add(('snapshot', p.snapshot.snapshot_id))
        for data in p.market_inputs:
            desc, g = data.bundle.descriptor, data.current_rights
            rq = desc.request
            for item in data.bundle.evidence:
                resolved_refs.add(('revision', item.revision.source_id, item.revision.dataset_id,
                    item.revision.event_id, item.revision.revision_id))
                resolved_refs.add(('observation', item.observation.observation_id))
            if g.rights_ref != desc.historical_rights_snapshot.rights_ref:
                raise d.ApprovalDenied('rights_denied')
            if any(x.observation.rights_ref != g.rights_ref for x in data.bundle.evidence):
                raise d.ApprovalDenied('rights_denied')
            for purpose in ('research', 'store', 'report'):
                if not g.allows(at=at, purpose=purpose, source_id=rq.source_id,
                                dataset_id=rq.dataset_id, dataset_version=rq.dataset_version):
                    raise d.ApprovalDenied('rights_denied')
            for proof in p.snapshot.valuation.market_proofs:
                if proof.selection.dataset_key == (rq.source_id, rq.dataset_id, rq.dataset_version) and proof.rights.rights_ref != g.rights_ref:
                    raise d.ApprovalDenied('rights_denied')
            grants.append(g)
            refs.append(target_ref('rights', g.rights_ref, g))
    if len(resolved_refs) > 128:
        raise d.ApprovalDenied('capacity_exceeded')
    # Current grants remain fresh above. Q24 receives exactly the original generation input;
    # historical rights are independently reconstructed from the stored snapshot proofs.
    def historical(p):
        data = []
        for x in p.market_inputs:
            rq = x.bundle.descriptor.request
            matches = {v.rights for v in p.snapshot.valuation.market_proofs
                       if v.selection.dataset_key == (rq.source_id, rq.dataset_id, rq.dataset_version)}
            if len(matches) != 1:
                raise d.ApprovalDenied('source_unresolved')
            data.append(replace(x, current_rights=next(iter(matches))))
        return replace(p, market_inputs=tuple(data))
    original = replace(i, current=historical(i.current), risk_points=tuple(map(historical, i.risk_points)),
        boundary_inputs=tuple(map(historical, i.boundary_inputs)),
        daily_usage_inputs=tuple(map(historical, i.daily_usage_inputs)))
    replay_repo = SyntheticTargetRepository()
    if req.predecessor_plan_ref is not None:
        # No fabricated predecessor insertion: a previous plan must really resolve.
        prior = source.repository.get(req.predecessor_plan_ref, environment='synthetic', account_ref=req.account_ref)
        if prior is None:
            raise d.ApprovalDenied('source_unresolved')
        # get-only bridge allows Q24 validate_predecessor to resolve the exact original.
        class Replay:
            def get(self, r, **kwargs):
                return source.repository.get(r, **kwargs)
            def append(self, artifacts):
                # Canonical contracts and Q24 validate_predecessor already ran in builder.
                return artifacts
        replay_repo = Replay()
    rebuilt = build_target(req, original, replay_repo)
    if rebuilt != a or a.plan.body.status != 'eligible':
        raise d.ApprovalDenied('candidate_mismatch')
    objects = (('plan', a.plan.plan_id, a.plan), ('result', a.result.result_id, a.result),
               *(('candidate', c.candidate_id, c) for c in a.candidates))
    candidate = None
    for kind, identity, obj in objects:
        r = target_ref(kind, identity, obj)
        if source.repository.get(r, environment='synthetic', account_ref=req.account_ref) != obj:
            raise d.ApprovalDenied('source_unresolved')
        if r == candidate_ref:
            candidate = obj
    if candidate is None or require_live and not candidate.body.terms.valid_from <= at < candidate.body.terms.valid_to:
        raise d.ApprovalDenied('candidate_mismatch')
    authorize(synthetic_binding('reporting'), 'synthetic.report')
    text = render_candidate(candidate, source.repository, i.current.market_inputs, at=at)
    evidence = d.CandidateEvidence(candidate_ref, target_ref('plan', a.plan.plan_id, a.plan),
        target_ref('result', a.result.result_id, a.result), target_ref('request', req.request_id, req),
        candidate.body.input_refs, tuple(dict.fromkeys(refs)),
        tuple(r for r in candidate.body.input_refs if r.kind != 'rights'), at,
        'q26-source-v1:' + sha256(raw).hexdigest(), d.FIXTURE_REF)
    rights_end = min(min(g.valid_to, g.revoked_at or g.valid_to) for g in grants)
    return candidate, evidence, text, min(rights_end, i.policy.valid_to)


class ApprovalApplication:
    """작업별 고정 오류만 공개한다. repository 자체도 동일 검사를 강제한다."""
    def __init__(self, repository):
        from quantharbor.adapters.synthetic_approval import SyntheticApprovalRepository
        from quantharbor.adapters.postgres_execution import PostgresExecutionRepository
        if type(repository) not in (SyntheticApprovalRepository, PostgresExecutionRepository):
            raise d.ApprovalDenied()
        self._repository = repository

    def _call(self, name, *args, **kwargs):
        try:
            return getattr(self._repository, name)(*args, **kwargs)
        except d.ApprovalDenied:
            raise
        except Exception:
            raise d.ApprovalDenied('invalid_contract') from None

    def present(self, handle, candidate_ref):
        return self._call('present', handle, candidate_ref)

    def challenge(self, handle, approval_ref, *, action, command_id):
        return self._call('challenge', handle, approval_ref, action=action, command_id=command_id)

    def execute(self, handle, challenge):
        return self._call('execute', handle, challenge)

    def withdraw(self, handle, approval_ref, *, command_id):
        return self._call('withdraw', handle, approval_ref, command_id=command_id)

    def control(self, handle, action):
        return self._call('control', handle, action)

    def query(self, handle, *, account_ref, purpose, limit=10, cursor=0):
        return self._call('query', handle, account_ref=account_ref, purpose=purpose, limit=limit, cursor=cursor)
