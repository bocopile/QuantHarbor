"""Q24 최대128개 불변 레코드의 메모리 저장. 운영 내구성/예약 아님."""
from threading import RLock

from quantharbor.application.target import validate_predecessor
from quantharbor.domain.ledger import integer
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.target import (OrderCandidate, TargetBuildResult, TargetPlan, TargetRef, ref)
from quantharbor.ports.target import TargetArtifacts


def _encode(obj):
    return canonical_bytes(CanonicalPayload(type(obj).__name__, 1, obj.body.environment, obj))


def _check_artifacts(artifacts):
    if type(artifacts) is not TargetArtifacts or type(artifacts.candidates) is not tuple or len(artifacts.candidates) > 128:
        raise ContractError()
    originals = (artifacts.plan, *artifacts.candidates, artifacts.result)
    if type(artifacts.plan) is not TargetPlan or type(artifacts.result) is not TargetBuildResult or any(type(c) is not OrderCandidate for c in artifacts.candidates):
        raise ContractError()
    encoded = tuple(_encode(obj) for obj in originals)
    objects = tuple(parse_payload(raw).payload for raw in encoded)
    plan, candidates, result = objects[0], objects[1:-1], objects[-1]
    b, rb = plan.body, result.body
    pr = ref('plan', plan.plan_id, plan)
    if (rb.plan_ref, rb.account_ref, rb.environment, rb.request_ref, rb.outcome, rb.failures) != (
            pr, b.account_ref, b.environment, ref('request', b.request.request_id, b.request), b.status, b.failures):
        raise ContractError()
    if rb.candidate_refs != tuple(ref('candidate', c.candidate_id, c) for c in candidates) or len(candidates) != len(b.orders):
        raise ContractError()
    for index, c in enumerate(candidates):
        cb = c.body
        if (cb.plan_ref, cb.order_index, cb.account_ref, cb.environment, cb.authority_generation,
                cb.policy_ref, cb.input_refs, cb.terms) != (pr, index, b.account_ref, b.environment,
                b.request.authority_generation, b.request.policy_ref, b.input_refs, b.orders[index]):
            raise ContractError()
    keys = (('plan', plan.plan_id), *(('candidate', c.candidate_id) for c in candidates), ('result', result.result_id))
    if len(set(keys)) != len(keys):
        raise ContractError()
    return keys, encoded, plan, candidates, result


class SyntheticTargetRepository:
    def __init__(self, *, capacity=128):
        integer(capacity, 1, 128)
        self._capacity = capacity
        self._records = {}
        self._lock = RLock()

    @classmethod
    def product_synthetic(cls, database, *, capacity=128):
        """명시 제품 연결. 같은 정확 repository 타입과 검증 경로를 유지한다."""
        from .product_artifacts import ProductArtifacts
        repository = SyntheticTargetRepository(capacity=capacity)
        repository._records = ProductArtifacts.product_synthetic(database, 'target', capacity=capacity)
        repository._lock = database._product_gate
        return repository

    def list_records(self, *, environment, account_ref):
        from .product_artifacts import list_records
        with self._lock:
            return list_records(self._records, 'target', environment, account_ref)

    def get(self, reference, *, environment, account_ref):
        if type(reference) is not TargetRef:
            raise ContractError()
        TargetRef(**{name: getattr(reference, name) for name in reference.__dataclass_fields__})
        with self._lock:
            raw = self._records.get((reference.kind, reference.id))
            if raw is None:
                return None
            obj = parse_payload(raw).payload
            if ref(reference.kind, reference.id, obj) != reference or (obj.body.environment, obj.body.account_ref) != (environment, account_ref):
                raise ContractError()
            return obj

    def append(self, artifacts):
        keys, encoded, plan, candidates, result = _check_artifacts(artifacts)
        b = plan.body
        with self._lock:
            prior = b.request.predecessor_plan_ref
            if prior is not None:
                validate_predecessor(self.get(prior, environment=b.environment, account_ref=b.account_ref), b.request)
            for key, raw in zip(keys, encoded):
                if key in self._records and self._records[key] != raw:
                    raise ContractError()
            if len(set(self._records) | set(keys)) > self._capacity:
                raise ContractError()
            # 전체 묶음이 유효한 뒤 한 번에 추가한다. 부분 저장 없음.
            self._records.update(zip(keys, encoded))
        return TargetArtifacts(plan, candidates, result)
