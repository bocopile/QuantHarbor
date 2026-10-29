"""현재 Q20/Q21/Q23 typed 계산과 실제 원 후보 재현. DB 시험은 root runner에 둔다."""
from dataclasses import replace
import unittest

from quantharbor.application.approval import validate_source
from quantharbor.application.execution import current_risk,ExecutionApplication
from quantharbor.application.target import _Blocked
from quantharbor.domain import execution as d
from quantharbor.domain import approval as a
from quantharbor.domain.ledger import hash_record
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload,canonical_bytes,parse_payload
from quantharbor.domain.target import ref as target_ref
from synthetic_execution import composition,approval_record,AT
from synthetic_approval import rights_changed


class ExecutionTypedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source,cls.inputs,cls.broker=composition()
        cls.approval=approval_record(cls.source)

    def risk(self,*,source=None,inputs=None,broker=None,intents=(),reservations=(),at=AT,exclude=None):
        inputs=inputs or self.inputs
        return current_risk(source or self.source,inputs,broker or self.broker,self.approval,
            at=at,generation='synthetic-generation-1',fence=1,account_version=0,
            projection=inputs.current.current.snapshot.valuation.projection,
            intents=intents,reservations=reservations,exclude_intent=exclude)

    def test_DEC005_request_TTL_excluded_only_for_current_account_and_absolute_window(self):
        from quantharbor.application.execution import _validate_account_current,validate_current
        current=replace(self.inputs,policy=replace(self.inputs.policy,valid_to=a.plus(AT,6000)))
        def check(at):
            return _validate_account_current(self.source,current,self.broker,at=at,
                generation=self.source.request.authority_generation,
                projection=current.current.current.snapshot.valuation.projection,intents=())
        first=check(self.source.request.expires_at)
        later=check(a.plus(self.source.request.expires_at,1))
        self.assertEqual(first[:2],later[:2])
        self.assertGreater(first[1],self.source.request.expires_at)
        self.assertLess(first[1],current.policy.valid_to)
        with self.assertRaises((a.ApprovalDenied,d.ExecutionDenied)):
            validate_current(self.source,current,self.broker,self.approval,at=self.source.request.expires_at,
                generation=self.source.request.authority_generation,
                projection=current.current.current.snapshot.valuation.projection,intents=())
        with self.assertRaises((d.ExecutionDenied,_Blocked,ContractError)):check(first[1])

    def test_DEC005_full_account_current_rights_and_policy_deadline(self):
        from quantharbor.application.execution import _validate_account_current
        def check(inputs,at=AT,source=None):
            return _validate_account_current(source or self.source,inputs,self.broker,at=at,
                generation=self.source.request.authority_generation,
                projection=inputs.current.current.snapshot.valuation.projection,intents=())
        with self.assertRaises(d.ExecutionDenied):check(self.inputs,at=self.inputs.policy.valid_to)
        with self.assertRaises((d.ExecutionDenied,_Blocked,ContractError)):
            check(replace(self.inputs,current=rights_changed(self.source).inputs))
        with self.assertRaises((d.ExecutionDenied,_Blocked,ContractError)):
            check(self.inputs,source=rights_changed(self.source))
        missing=replace(self.inputs.current.facts,covered_scope=replace(self.inputs.current.facts.covered_scope,positions=self.inputs.current.facts.covered_scope.positions[:1]))
        with self.assertRaises((d.ExecutionDenied,_Blocked,ContractError)):
            check(replace(self.inputs,current=replace(self.inputs.current,facts=missing)))

    def test_EX01_real_source_positive302_and_current_typed_risk(self):
        candidate,evidence,text,end=validate_source(self.source,self.approval.candidate_ref,at=AT,generation='synthetic-generation-1')
        self.assertEqual((candidate.body.terms.quantity,candidate.body.terms.limit_price,candidate.body.terms.cost_bound,candidate.body.terms.maximum_burden),('3','100','2','302'))
        self.assertIn('3주 매수',text)
        source,risk=self.risk()
        self.assertEqual(risk.outcome,'allow')
        self.assertEqual(risk.cash[0].available,'1000') # actual helper default has NO obligations
        self.assertEqual(source.ledger_cursor,1)
        self.assertEqual(source.query_ref,d.ref('query',self.inputs.query.query_id,self.inputs.query))

    def test_EX03_current_available600_is_independent_from_original_candidate(self):
        source,inputs,broker=composition(available='600')
        self.assertEqual(source.request,self.source.request)
        self.assertEqual(source.artifacts,self.source.artifacts)
        _,risk=self.risk(inputs=inputs,broker=broker)
        self.assertEqual(risk.cash[0].available,'600')
        self.assertEqual(self.approval.terms.maximum_burden,'302')

    def test_EX14_own_reservation_excluded_and_exact_expiry_denied(self):
        source,risk=self.risk()
        intent=d.OrderIntent('intent-1',self.approval.account_ref,'synthetic',self.approval.candidate_ref,
            a.ref('approval',self.approval.approval_id,self.approval),self.approval.terms,hash_record(self.approval.terms),
            d.ref('risk',risk.risk_id,risk),'synthetic-generation-1',1,'prepared',1,None,'0','0',None,None,'complete')
        r=d.ReservationSlice('reservation-1','intent-1','obligation-1','principal','cash','USD',AT,
            '2024-03-09T00:00:00Z','302','302','0','0','0','0',AT,())
        _,other=self.risk(intents=(intent,),reservations=(r,))
        _,own=self.risk(intents=(intent,),reservations=(r,),exclude='intent-1')
        self.assertEqual((other.cash[0].available,own.cash[0].available),('698','1000'))
        with self.assertRaises((a.ApprovalDenied,d.ExecutionDenied,ContractError)):
            self.risk(at=self.approval.expires_at)

    def test_EX18_EX26_unknown_intent_or_accounting_incomplete_blocks_new(self):
        _,risk=self.risk()
        intent=d.OrderIntent('intent-1',self.approval.account_ref,'synthetic',self.approval.candidate_ref,
            a.ref('approval',self.approval.approval_id,self.approval),self.approval.terms,hash_record(self.approval.terms),
            d.ref('risk',risk.risk_id,risk),'synthetic-generation-1',1,'unknown',1,None,'0','1',None,None,'incomplete')
        with self.assertRaises(d.ExecutionDenied): self.risk(intents=(intent,))

    def test_EX33_current_rights_and_original_rights_both_rechecked(self):
        with self.assertRaises(a.ApprovalDenied): self.risk(source=rights_changed(self.source))
        current=replace(self.inputs,current=rights_changed(self.source).inputs)
        with self.assertRaises((ContractError,d.ExecutionDenied,_Blocked)):
            self.risk(inputs=current)

    def test_EX33_forged_query_and_missing_current_scope_denied(self):
        q=replace(self.inputs.query,cash=(replace(self.inputs.query.cash[0],amount='999999'),))
        with self.assertRaises(d.ExecutionDenied): self.risk(inputs=replace(self.inputs,query=q))
        other=replace(self.inputs.current,facts=replace(self.inputs.current.facts,status='unknown'))
        with self.assertRaises((ContractError,d.ExecutionDenied)):
            self.risk(inputs=replace(self.inputs,current=other))

    def test_EX36_execution_adapter_closed_type_rejects_duck_and_memory(self):
        with self.assertRaises(d.ExecutionDenied): ExecutionApplication(object())
        class Duck:
            def dispatch(self,*args): return True
        with self.assertRaises(d.ExecutionDenied): ExecutionApplication(Duck())

    def test_EX37_execution_serialization_closed_and_environment_bound(self):
        source,risk=self.risk()
        for obj in (source,risk,self.inputs.query,self.inputs.policy,*risk.cash):
            raw=d.encoded(obj)
            self.assertEqual(parse_payload(raw).payload,obj)
            with self.assertRaises(ContractError):
                canonical_bytes(CanonicalPayload(type(obj).__name__,1,'live',obj))
        raw=d.encoded(risk).decode().replace('"payload":{','"payload":{"foreign":1,')
        with self.assertRaises(ContractError): parse_payload(raw)
