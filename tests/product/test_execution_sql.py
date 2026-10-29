"""SQL bridge의 local I/O/권한 경계. 실제 DB 양/음성은 별도 root 실행."""
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from quantharbor.adapters.execution_uow import (ExecutionUnitOfWork,MAX_FRAME,MAX_CHUNK,
    MAX_CHUNK_FRAME,MAX_HEADER,MAX_TRANSACTION_BYTES,_json)
from quantharbor.adapters.postgres_ledger import PostgresLedger
from quantharbor.domain import execution as d


class ExecutionSQLTests(unittest.TestCase):
    def uow(self):
        db=PostgresLedger();db._ready=True
        return ExecutionUnitOfWork(db,'synthetic-account:sql-test')

    def test_DEC005_SQL_closed_validity_readset_resume_policy_and_append_only_archive(self):
        # Structural regression only. Genuine context/CAS/SQL effects are root DB scenarios.
        sql=(Path(__file__).resolve().parents[2]/'migrations/0003_synthetic_execution.sql').read_text()
        apply=sql.split('CREATE FUNCTION qh.execution_apply(',1)[1].split('END $$;',1)[0]
        for field in ('current_identity','validator_version','valid_from','valid_to','query_ref','ledger_cursor','generation','fence'):
            self.assertIn("validity->'"+field+"'" if field in ('query_ref','ledger_cursor','generation','fence') else "validity->>'"+field+"'",apply)
        self.assertIn("rec->'account_version' IS DISTINCT FROM qh.execution_map_get(old.state",apply)
        self.assertIn("c.header->>'action' IS DISTINCT FROM 'policy'",apply)
        self.assertIn('new_archive->((x.n-1)::integer) IS DISTINCT FROM x.value',apply)
        self.assertIn('SELECT cursor FROM qh.ledger_stream',apply)
        self.assertIn("rec->>'validator_version'='q27-account-current-v1'",sql)

    def test_SEC1_terminal_reserve_covers_measured_red_and_fits_unused_slot(self):
        # Static reservation arithmetic against actual public PostgreSQL red
        # measurements. This does NOT execute SQL or prove the repaired DB path.
        root=Path(__file__).resolve().parents[2]
        sql=(root/'migrations/0003_synthetic_execution.sql').read_text()
        common=sql.split('CREATE FUNCTION qh.execution_common_remaining(a text)',1)[1].split('END $$;',1)[0]
        constants={name:int(value) for name,value in re.findall(r'(\w+) constant (?:integer|bigint):=(\d+);',common)}
        terminal=common.split("ELSIF plan->>'resume'='1' THEN",1)[1].split('END IF;',1)[0]
        self.assertIn('credit:=credit+repair_records;credit_bytes:=credit_bytes+repair_bytes;',terminal)
        repair=(constants['repair_records'],constants['repair_bytes'])
        controller=(5+2+2*constants['stop_records'],7*65536+2*constants['stop_bytes'])
        noncontroller=(5+2+repair[0],7*65536+repair[1])
        self.assertEqual(controller,(constants['session_records'],constants['session_bytes']))
        self.assertEqual((2*controller[0]+repair[0]+1,2*controller[1]+repair[1]+65536),(29,3211264))
        self.assertLessEqual(noncontroller[0],controller[0])
        self.assertLessEqual(noncontroller[1],controller[1])
        red=json.loads((root/'docs/evidence/execution-completion-security-red-2026-10-27.json').read_text())['result']
        detail=next(x.removeprefix('DETAIL:  ') for x in red['diagnostic_sql_errors'] if x.startswith('DETAIL:  '))
        observed=json.loads(detail)
        # Before: the still-live approver owns the missing repair credit.
        # After: it is paused; only the already-calculated shared repair remains.
        self.assertLessEqual(observed['after']['records'],observed['before']['records']+repair[0])
        self.assertLessEqual(observed['after']['bytes'],observed['before']['bytes']+repair[1])

    def test_lifecycle_running_has_no_noncontroller_repair_recovery_slot_still_pays(self):
        # Source-level SQL regression only; root must execute the unchanged
        # actual active3 fixture and every recovery stage against PostgreSQL.
        sql=(Path(__file__).resolve().parents[2]/'migrations/0003_synthetic_execution.sql').read_text()
        common=sql.split('CREATE FUNCTION qh.execution_common_remaining(a text)',1)[1].split('END $$;',1)[0]
        session=common.split("IF h.kind='session'",1)[1].split("ELSIF h.kind='approval'",1)[0]
        self.assertIn("ELSIF plan->>'resume'='1' THEN",session)
        self.assertEqual(session.count('credit:=credit+repair_records;'),1)
        # Original running boundary was 130 solely from the extra repair pair.
        self.assertEqual(130-2,128)
        for resume in (0,1):
            terminal=(2+2*resume,131072+393216*resume)
            slot=(5+terminal[0],5*65536+terminal[1])
            self.assertLessEqual(slot[0],13)
            self.assertLessEqual(slot[1],1376256)

    def test_approval_terminal_budget_covers_hold_retention_atomic_and_rejected_paths(self):
        sql=(Path(__file__).resolve().parents[2]/'migrations/0003_synthetic_execution.sql').read_text()
        common=sql.split('CREATE FUNCTION qh.execution_common_remaining(a text)',1)[1].split('END $$;',1)[0]
        self.assertIn("WHEN plan->>'resume'='1' THEN 8+pending::integer ELSE 7 END",common)
        self.assertIn("WHEN plan->>'resume'='1' THEN 6",common)
        self.assertIn("WHEN command_body->>'action' IN ('withdraw','revoke') THEN 5 ELSE 4 END",common)
        self.assertIn("c.wire->'payload'->>'authority_generation'=ac.generation",common)
        self.assertIn("IF EXISTS(SELECT 1 FROM qh.execution_intent",common)
        # (new actual rows, repair rows, released reserve). Challenge+indexes=3;
        # closure=runtime+approval+receipt+receipt lookup, minus hold iff last.
        paths={'issued_last':(3,2,6),'issued_hold_retained':(4,2,6),
               'rejected_receipt':(2,2,6),'expired_retained_hold':(4,2,6),
               'atomic_last':(3+3,2,8),'atomic_retained_hold':(3+4,2,9)}
        for path,(actual,repair,reserve) in paths.items():
            with self.subTest(path=path):self.assertLessEqual(actual+repair,reserve)
        # A rejected last protective command leaves approved live. Its own
        # approval reserve must remain; the former protection_pending=0 branch
        # would recreate 8 rows after releasing only 6 command rows.
        self.assertNotIn('WHEN protection_pending THEN 0',common)
        for label,before,after in (
                ('rejected_live',9+6,2+2+8),
                ('issued_with_other_pending',9+6+6,4+2+6),
                ('atomic_with_other_pending',9+6,7+2+6)):
            with self.subTest(path=label):self.assertLessEqual(after,before)
        # Small-row copies/index bounds and new query+reconciliation are both
        # charged. Approval's separate large-copy allowance is released only
        # on terminal transition; terminal-target rejection cannot borrow it.
        self.assertIn("IF plan->>'resume'='1' THEN z:=z+repair_bytes; END IF",common)
        self.assertIn("IF body->>'state'='approved' AND plan->>'resume'='1'",common)
        # Bounded row+state-copy/index groups: receipt 1 quantum, runtime 1,
        # approval 5 (two <=147456 copies plus keys), challenge+indexes 1.
        self.assertLessEqual(65536+393216,6*32768+262144+393216)
        self.assertLessEqual(7*65536+393216,6*32768+262144+393216)
        self.assertLessEqual(8*65536+393216,8*32768+262144+393216)

    def test_completion_guard_scopes_unconsumed_funded_protection_and_invalidation(self):
        sql=(Path(__file__).resolve().parents[2]/'migrations/0003_synthetic_execution.sql').read_text()
        save=sql.split('CREATE FUNCTION qh.execution_save(',1)[1].split('END $$;',1)[0]
        guard=save.split('AS terminal_item(value)',1)[1].split('IF old.account_ref IS NULL',1)[0]
        self.assertIn("NOT EXISTS(SELECT 1 FROM qh.execution_intent",guard)
        self.assertIn("IN ('revoke','withdraw')",guard)
        self.assertIn("IN ('expired','invalidated')",guard)
        self.assertIn("NOT EXISTS(SELECT 1 FROM qh.execution_evidence",guard)
        self.assertNotIn("IN ('approve','admit')",guard)
        self.assertIn("THEN RAISE EXCEPTION 'execution_completion'",save)
        # Guard selection grants no authority: the exact existing command
        # validator still runs before save for old or same-TX challenges.
        apply=sql.split('CREATE FUNCTION qh.execution_apply(',1)[1].split('END $$;',1)[0]
        self.assertLess(apply.index('PERFORM qh.execution_check_command(c,old,session_body)'),
            apply.index('result:=qh.execution_save'))

    def test_product_cannot_invoke_generic_write_without_trusted_identity(self):
        u=self.uow()
        with patch.object(u,'_exchange') as exchange:
            for function,values in [('execution_save',({},'0')),('execution_event',({},)),
                ('execution_ledger',('append',{},'2024-03-08T15:00:00Z')),
                ('execution_consume',('message','0'*64))]:
                with self.assertRaises(d.ExecutionDenied): u.call(function,u.account_ref,*values)
        exchange.assert_not_called()

    def test_duplicate_json_keys_nested_and_extra_output_rejected_before_conversion(self):
        for raw in ('{"a":1,"a":2}','{"a":{"n":1,"n":2}}','{}\ntrue'):
            with self.assertRaises(ValueError): _json(raw)
        self.assertEqual(_json('{"a":null}'),{'a':None})

    def test_hex_frame_measured_after_serialization_at_raw_chunk_limit(self):
        u=self.uow(); frames=[]
        with patch.object(u,'_exchange',side_effect=lambda sql,**kw:frames.append((sql,kw)) or 1):
            u._select('execution_stage_chunk','context:abc',0,(b'\xff'*MAX_CHUNK).hex())
        sql,kw=frames[0]
        self.assertLessEqual(len((sql+'\n\\echo '+'q27frame'+'0'*32+'\n').encode()),MAX_CHUNK_FRAME)
        self.assertEqual(kw['frame_limit'],135168)
        with self.assertRaises(d.ExecutionDenied): u._select('execution_stage_chunk','context:abc',0,'00'*(MAX_CHUNK+1))
        self.assertEqual((MAX_FRAME,MAX_HEADER,MAX_TRANSACTION_BYTES),(8388608,4096,268435456))

    def test_pages_validate_missing_conflicting_sequence_size_and_utf8(self):
        for response in ({'page':1,'total':2,'hex':'7b7d'}, {'page':0,'total':3,'hex':'7b7d'},
                         {'page':0,'total':2,'hex':'ff7d'}, {'page':0,'total':2,'hex':'7b7d','extra':1}):
            u=self.uow()
            with patch.object(u,'_select',return_value=response),self.assertRaises((d.ExecutionDenied,ValueError,UnicodeError)):
                u._read('load')
        u=self.uow()
        text=json.dumps({'unicode':'한'*30000},ensure_ascii=False).encode()
        pages=[{'page':n,'total':len(text),'hex':text[n*MAX_CHUNK:(n+1)*MAX_CHUNK].hex()} for n in range((len(text)+MAX_CHUNK-1)//MAX_CHUNK)]
        with patch.object(u,'_select',side_effect=pages): self.assertEqual(u._read('load'),{'unicode':'한'*30000})

    def test_partial_pipe_writes_eof_extra_output_timeout_and_cleanup(self):
        # Local Python pipe peer, no SQL/server/Docker/network or credentials.
        peer="import sys\nfor line in sys.stdin.buffer:\n if line.startswith(b'\\\\echo '):\n  sys.stdout.buffer.write(b'{}\\n'+line.split(b' ',1)[1]);sys.stdout.buffer.flush()\n"
        u=self.uow();u._deadline=time.monotonic()+5
        u._process=subprocess.Popen([sys.executable,'-I','-S','-B','-c',peer],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        from os import write as real_write
        with patch('quantharbor.adapters.execution_uow.os.write',side_effect=lambda fd,data:real_write(fd,data[:7])):
            self.assertEqual(u._exchange('x'*10000),{})
        p=u._process;u.close();self.assertIsNotNone(p.poll())
        for body in ("import sys;sys.exit(0)","import time;time.sleep(2)"):
            u=self.uow();u._deadline=time.monotonic()+0.05
            u._process=subprocess.Popen([sys.executable,'-I','-S','-B','-c',body],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
            p=u._process
            try:
                with self.assertRaises(d.ExecutionDenied):u._exchange('SELECT 1;')
            finally:u.close()
            self.assertIsNotNone(p.poll())

    def test_caught_frame_failure_poison_prevents_commit_and_closes_pipe(self):
        peer="import sys\nfor line in sys.stdin.buffer:\n if line.startswith(b'\\\\echo '):\n  sys.stdout.buffer.write(b'{}\\n'+line.split(b' ',1)[1]);sys.stdout.buffer.flush()\n"
        u=self.uow();u._deadline=time.monotonic()+5
        u._process=subprocess.Popen([sys.executable,'-I','-S','-B','-c',peer],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        process=u._process
        self.assertEqual(u._exchange('SELECT 1;'),{})
        with self.assertRaises(d.ExecutionDenied):u._exchange('x'*(MAX_FRAME+1))
        self.assertIsNone(u._process)
        self.assertIsNotNone(process.poll())
        with self.assertRaises(d.ExecutionDenied):u.commit()

    def test_real_local_gt8MiB_chunked_utf8_roundtrip_each_serialized_frame_bounded(self):
        # A local pipe peer, not PostgreSQL or a financial/authority substitute.
        peer=r'''
import json,re,sys
raw=bytearray();response=None
for line in sys.stdin.buffer:
 text=line.decode().strip()
 if text.startswith('SELECT qh.execution_stage_chunk('):
  m=re.search(r",([0-9]+),'([0-9a-f]*)'\);$",text)
  if m is None:sys.exit(3)
  raw.extend(bytes.fromhex(m[2]));response='1'
 elif text.startswith('SELECT qh.execution_read_page('):
  page=int(text.rsplit(',',1)[1].split(')')[0]);start=page*65536
  response=json.dumps({'page':page,'total':len(raw),'hex':raw[start:start+65536].hex()})
 elif text.startswith('\\echo '):
  sys.stdout.write(response+'\n'+text.split(' ',1)[1]+'\n');sys.stdout.flush()
'''
        u=self.uow();u._deadline=time.monotonic()+30
        u._process=subprocess.Popen([sys.executable,'-I','-S','-B','-c',peer],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        process=u._process
        value={'text':'한'*3145729}
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
        self.assertGreater(len(raw),MAX_FRAME)
        try:
            for part,offset in enumerate(range(0,len(raw),MAX_CHUNK)):
                self.assertEqual(u._select('execution_stage_chunk','context:local',part,raw[offset:offset+MAX_CHUNK].hex()),1)
            self.assertEqual(u._read('load'),value)
            self.assertLess(u._transferred,MAX_TRANSACTION_BYTES)
        finally:u.close()
        self.assertIsNotNone(process.poll())

    def test_protocol_exact_numbers_and_hex_fail_closed(self):
        for raw in ('{"x":NaN}','{"x":Infinity}','{"x":1.5}'):
            with self.assertRaises(ValueError):_json(raw)
        for response in ({'page':False,'total':2,'hex':'7b7d'},
                         {'page':0,'total':2,'hex':'7b 7d'},
                         {'page':0,'total':2,'hex':'7B7D'}):
            u=self.uow()
            with patch.object(u,'_select',return_value=response),self.assertRaises(d.ExecutionDenied):u._read('load')
            self.assertTrue(u._failed)

    def test_cumulative_io_and_expired_transaction_deadline_close_peer(self):
        for mode in ('bytes','deadline'):
            u=self.uow();u._deadline=time.monotonic()+1
            u._process=subprocess.Popen([sys.executable,'-I','-S','-B','-c','import sys;sys.stdin.buffer.read()'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
            process=u._process
            if mode=='bytes':u._transferred=MAX_TRANSACTION_BYTES-1
            else:u._deadline=time.monotonic()-1
            with self.assertRaises(d.ExecutionDenied):u._exchange('SELECT true;')
            self.assertIsNotNone(process.poll())
            with self.assertRaises(d.ExecutionDenied):u.commit()
