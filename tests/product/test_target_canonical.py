from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from functools import lru_cache
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
from quantharbor.application.target import build_target
from quantharbor.domain.ledger import hash_record
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.target import (CandidateBody, OrderCandidate, TargetBuildResult, TargetPlan,
    TargetRef, TargetScope, TargetValue, ref)
from quantharbor.ports.target import TargetArtifacts
from synthetic_target import build, fixture
from test_target import base


@lru_cache(maxsize=1)
def artifacts():
    r,i=base(targets=('3',None))
    return build(r,i)


def encode(obj):
    return canonical_bytes(CanonicalPayload(type(obj).__name__,1,obj.body.environment,obj))


class TargetCanonicalTests(unittest.TestCase):
    def test_all_top_level_roundtrip_hash_prefix_and_size(self):
        a=artifacts()
        for obj in (a.plan,*a.candidates,a.result):
            raw=encode(obj)
            self.assertLessEqual(len(raw),65536)
            self.assertEqual(parse_payload(raw).payload,obj)
            self.assertEqual(hash_record(obj),sha256(b'QuantHarbor/qh-canonical-json-v1\n'+raw).hexdigest())
        self.assertEqual(a.plan.plan_id,'target-plan:'+hash_record(a.plan.body))
        self.assertEqual(a.candidates[0].candidate_id,'candidate:'+hash_record(a.candidates[0].body))

    def test_json_unknown_schema_field_enum_float_bool_duplicate_rejected(self):
        raw=json.loads(encode(artifacts().candidates[0]))
        variants=[]
        for path,value in ((('schema_name',),'TargetUnknown'),(('schema_version',),True),
            (('payload','body','order_index'),False),(('payload','body','terms','quantity'),3.0),
            (('payload','body','terms','side'),'short'),(('payload','body','terms','quantity'),'1e3'),
            (('payload','body','terms','quantity'),' 3'),(('payload','body','extra'),'field')):
            altered=deepcopy(raw)
            cursor=altered
            for p in path[:-1]:
                cursor=cursor[p]
            cursor[path[-1]]=value
            variants.append(json.dumps(altered))
        variants.extend([encode(artifacts().candidates[0]).decode().replace('"schema_version":1','"schema_version":1,"schema_version":1',1),
                         b'x'*65537])
        for value in variants:
            with self.subTest(value=str(value)[:50]),self.assertRaises(ContractError):
                parse_payload(value)

    def test_direct_constructor_and_forged_hash_financial_totals_rejected(self):
        c=artifacts().candidates[0]
        with self.assertRaises(FrozenInstanceError):
            c.candidate_id='bad'
        with self.assertRaises(ContractError):
            replace(c,candidate_id='candidate:'+'a'*64)
        for name,value in (('quantity','4'),('cost_bound','0'),('maximum_burden','1'),('fee_bound','0')):
            with self.subTest(field=name),self.assertRaises(ContractError):
                replace(c.body.terms,**{name:value})
        forged=deepcopy(c)
        object.__setattr__(forged.body.terms,'cost_bound','0')
        with self.assertRaises(ContractError):
            encode(forged)
        a=artifacts()
        with self.assertRaises(ContractError):
            replace(a.plan.body,cash_calculation=(replace(a.plan.body.cash_calculation[0],planned_burden='0',remaining='1000'),))

    def test_restored_plan_cannot_change_request_target_or_weight_math(self):
        a=artifacts()
        with self.assertRaises(ContractError):
            replace(a.plan.body,request=replace(a.plan.body.request,
                targets=(replace(a.plan.body.request.targets[0],value='4'),)))
        r,i=fixture(basis='weight',targets=('0.25',None),prices=('60','60'),lot='2',fee='0')
        a=build(r,i)
        with self.assertRaises(ContractError):
            replace(a.plan.body,request=replace(r,targets=(replace(r.targets[0],value='0.5'),)))

    def test_display_cost_expiry_generation_financial_changes_new_hash(self):
        c=artifacts().candidates[0]
        changes=(replace(c.body,authority_generation='new'),
            replace(c.body,display_terms=replace(c.body.display_terms,risks=('새 위험',))),
            replace(c.body,display_terms=replace(c.body.display_terms,cost_explanation='새 비용 설명')),
            replace(c.body,display_terms=replace(c.body.display_terms,expiry_explanation='새 만료 설명')),
            replace(c.body,terms=replace(c.body.terms,valid_to='2024-03-08T14:31:20Z')))
        ids=[]
        for body in changes:
            new=OrderCandidate('candidate:'+hash_record(body),body)
            self.assertNotEqual(new.candidate_id,c.candidate_id)
            ids.append(new.candidate_id)
        self.assertEqual(len(set(ids)),len(ids))

    def test_decimal_and_utc_equivalence_and_order_duplicate_rejection(self):
        r,i=base(targets=('3',None))
        altered=replace(r,targets=(replace(r.targets[0],value='3.000'),),evaluated_at='2024-03-08T09:31:03-05:00')
        self.assertEqual(altered,r)
        self.assertEqual(ref('request',r.request_id,altered),ref('request',r.request_id,r))
        for targets in ((r.targets[0],r.targets[0]),tuple(reversed(base()[0].targets))):
            with self.assertRaises(ContractError):
                replace(r,targets=targets)
        with self.assertRaises(ContractError):
            replace(r,scope=replace(r.scope,positions=r.scope.positions*65))

    def test_input_byte_and_collection_limits_before_source_replay(self):
        from quantharbor.application import target
        r,i=base()
        with patch.object(target,'_resolved_bytes',return_value=8*1024*1024),self.assertRaises(ContractError):
            build(r,i)
        with self.assertRaises(ContractError):
            replace(i,risk_points=i.risk_points*65)
        with self.assertRaises(ContractError):
            replace(i.facts,obligations=i.facts.obligations+(None,)*129)
        with self.assertRaises(ContractError):
            replace(r,targets=(replace(r.targets[0],value='9'*21),))

    def test_memory_atomic_capacity_idempotence_and_defensive_reads(self):
        a=artifacts()
        repo=SyntheticTargetRepository(capacity=3)
        stored=repo.append(a)
        self.assertEqual(repo.append(a),stored)
        reference=ref('candidate',a.candidates[0].candidate_id,a.candidates[0])
        retrieved=repo.get(reference,environment='synthetic',account_ref=a.plan.body.account_ref)
        object.__setattr__(retrieved.body.display_terms,'rationale','변조')
        self.assertEqual(repo.get(reference,environment='synthetic',account_ref=a.plan.body.account_ref),a.candidates[0])
        with self.assertRaises(ContractError):
            repo.get(reference,environment='synthetic',account_ref='synthetic-account:other')
        with self.assertRaises(ContractError):
            repo.get(replace(reference,sha256='a'*64),environment='synthetic',account_ref=a.plan.body.account_ref)
        small=SyntheticTargetRepository(capacity=2)
        with self.assertRaises(ContractError):
            small.append(a)
        self.assertIsNone(small.get(ref('plan',a.plan.plan_id,a.plan),environment='synthetic',account_ref=a.plan.body.account_ref))

    def test_repository_rejects_cross_plan_candidate_and_result_binding(self):
        a=artifacts()
        changed_body=replace(a.candidates[0].body,order_index=1)
        c=OrderCandidate('candidate:'+hash_record(changed_body),changed_body)
        rb=replace(a.result.body,candidate_refs=(ref('candidate',c.candidate_id,c),))
        result=TargetBuildResult('target-result:'+hash_record(rb),rb)
        with self.assertRaises(ContractError):
            SyntheticTargetRepository().append(TargetArtifacts(a.plan,(c,),result))
        with self.assertRaises(ContractError):
            SyntheticTargetRepository().append(TargetArtifacts(a.plan,(),a.result))

    def test_predecessor_actual_resolution_scope_account_and_history(self):
        r,i=base(targets=('3',None))
        repo=SyntheticTargetRepository()
        prior=build_target(r,i,repo)
        predecessor=ref('plan',prior.plan.plan_id,prior.plan)
        new_request=replace(r,request_id='revision-2',predecessor_plan_ref=predecessor,
            targets=(replace(r.targets[0],value='4'),))
        next_artifact=build_target(new_request,i,repo)
        self.assertNotEqual(prior.plan.plan_id,next_artifact.plan.plan_id)
        self.assertEqual(repo.get(predecessor,environment='synthetic',account_ref=r.account_ref),prior.plan)
        with self.assertRaises(ContractError):
            build_target(new_request,i,SyntheticTargetRepository())
        with self.assertRaises(ContractError):
            build_target(replace(new_request,scope=replace(r.scope,positions=(r.scope.positions[0],))),i,repo)


if __name__=='__main__':
    unittest.main()
