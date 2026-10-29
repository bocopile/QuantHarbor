"""실제 합성 issuer journal·요청 결속. HTTP나 DB/Docker를 실행하지 않는다."""
from dataclasses import replace
import pickle
import unittest

from quantharbor.adapters.synthetic_execution_broker import BrokerFact
from quantharbor.domain import execution as d
from quantharbor.domain import approval as a
from quantharbor.domain.ledger import hash_record
from quantharbor.domain.primitives import ContractError
from synthetic_execution import composition,approval_record,AT


def request(source,approval,broker):
    r=d.ExecutionRef('risk','risk-1',1,d.CANONICAL,'1'*64)
    intent=d.OrderIntent('intent-1',approval.account_ref,'synthetic',approval.candidate_ref,
        a.ref('approval',approval.approval_id,approval),approval.terms,hash_record(approval.terms),r,
        'synthetic-generation-1',1,'dispatching',1,None,'0','0',None,None,'complete')
    attempt=d.DispatchAttempt('attempt-1','intent-1','submit',intent.request_hash,'synthetic-generation-1',1,
        broker._instance,'armed',AT,None)
    return attempt,intent


class ExecutionBrokerTests(unittest.TestCase):
    def setup_request(self,**kwargs):
        source,inputs,broker=composition(**kwargs)
        approval=approval_record(source)
        attempt,intent=request(source,approval,broker)
        return source,inputs,broker,attempt,intent

    def test_EX19_real_journal_rejects_resealed_and_foreign_receipt(self):
        source,inputs,broker,attempt,intent=self.setup_request(response='final_reject')
        receipt=broker.handoff(attempt,intent)
        self.assertEqual(receipt.kind,'final_reject')
        self.assertEqual(broker.verify(receipt,'receipt',receipt.receipt_id),receipt)
        forged=replace(receipt,request_hash='2'*64)
        with self.assertRaises(d.ExecutionDenied): broker.verify(forged,'receipt',forged.receipt_id)
        _,_,foreign=composition()
        with self.assertRaises(d.ExecutionDenied): foreign.verify(receipt,'receipt',receipt.receipt_id)
        with self.assertRaises(d.ExecutionDenied): broker.issue_event(receipt,0)

    def test_EX15_EX16_actual_handoff_once_and_unsent_proof_request_bound(self):
        source,inputs,broker,attempt,intent=self.setup_request()
        receipt=broker.handoff(attempt,intent)
        self.assertEqual(broker.received_count,1)
        with self.assertRaises(d.ExecutionDenied): broker.handoff(attempt,intent)
        with self.assertRaises(d.ExecutionDenied): broker.prove_unsent(attempt,intent)
        other=replace(attempt,attempt_id='attempt-2')
        proof=broker.prove_unsent(other,intent)
        self.assertEqual(proof.kind,'proven_unsent')
        with self.assertRaises(d.ExecutionDenied): broker.handoff(other,intent)
        self.assertEqual(broker.received_count,1)

    def test_EX18_complete_empty_query_is_fact_not_finality(self):
        _,inputs,broker,attempt,intent=self.setup_request(response='timeout')
        self.assertIsNone(broker.handoff(attempt,intent))
        q=broker.query()
        self.assertEqual(q.status,'complete')
        self.assertEqual((q.receipts,q.events),((),()))
        self.assertEqual(broker.received_count,1)
        with self.assertRaises(d.ExecutionDenied): broker.prove_unsent(attempt,intent)

    def test_EX20_issued_fill_identity_replays_same_object(self):
        _,_,broker,attempt,intent=self.setup_request()
        receipt=broker.handoff(attempt,intent)
        event=broker.issue_event(receipt,0)
        self.assertIs(broker.issue_event(receipt,0),event)
        self.assertEqual((event.quantity,event.fee,event.tax),('1','0','0'))
        self.assertEqual(event.receipt_ref,d.ref('receipt',receipt.receipt_id,receipt))
        with self.assertRaises(d.ExecutionDenied): broker.verify(replace(event,quantity='2'),'event',event.event_id)

    def test_EX21_EX22_issuer_preserves_cumulative_and_revision_semantics(self):
        facts=(BrokerFact('cum-1','fill','cumulative','stream',1,None,1,'1','100','0','0',AT),
               BrokerFact('cum-2','fill','cumulative','stream',1,None,2,'3','100','0','0',AT))
        _,_,broker,attempt,intent=self.setup_request(facts=facts)
        receipt=broker.handoff(attempt,intent)
        first,second=(broker.issue_event(receipt,i) for i in (0,1))
        self.assertEqual((first.quantity,second.quantity),('1','3'))
        self.assertEqual((first.stream_sequence,second.stream_sequence),(1,2))

    def test_EX26_unknown_cost_is_not_normalized_to_zero(self):
        facts=(BrokerFact('unknown-cost','fill','delta','execution-1',1,None,1,'1','100',None,None,AT),)
        _,_,broker,attempt,intent=self.setup_request(facts=facts)
        event=broker.issue_event(broker.handoff(attempt,intent),0)
        self.assertIsNone(event.fee)
        self.assertIsNone(event.tax)

    def test_EX27_cancel_receipt_has_separate_attempt_and_no_terminal_claim(self):
        _,_,broker,attempt,intent=self.setup_request()
        original=broker.handoff(attempt,intent)
        cancel=replace(attempt,attempt_id='cancel-attempt',action='cancel')
        receipt=broker.handoff(cancel,replace(intent,broker_order_id=original.broker_order_id))
        self.assertEqual(receipt.kind,'cancel_ack')
        self.assertNotEqual(receipt.attempt_id,original.attempt_id)
        self.assertEqual(receipt.broker_order_id,original.broker_order_id)

    def test_EX32_EX37_bounded_issuance_and_no_network_parameters(self):
        _,_,broker,attempt,intent=self.setup_request()
        for _ in range(19): broker.query()
        with self.assertRaises(d.ExecutionDenied): broker.query()
        from quantharbor.adapters.synthetic_execution_broker import SyntheticExecutionBroker
        for kwargs in ({'url':'https://invalid'},{'client':object()},{'credential':'unused'}):
            with self.assertRaises(TypeError): SyntheticExecutionBroker('synthetic-account:a',(),**kwargs)
