-- Q27 synthetic-only. 0001/0002는 변경하지 않는다. 관리 연결만 migration을 수행한다.
CREATE ROLE qh_execution_product NOLOGIN;
GRANT USAGE ON SCHEMA qh TO qh_execution_product;
CREATE TABLE qh.execution_account (
 account_ref text PRIMARY KEY REFERENCES qh.ledger_stream(account_ref),
 environment text NOT NULL DEFAULT 'synthetic' CHECK(environment='synthetic'),
 version integer NOT NULL DEFAULT 0 CHECK(version>=0),
 generation text NOT NULL, fence integer NOT NULL DEFAULT 1 CHECK(fence>0),
 mode text NOT NULL CHECK(mode IN ('running','stopped','reconciling','faulted')),
 state jsonb NOT NULL, source_hash text NOT NULL CHECK(source_hash ~ '^[0-9a-f]{64}$'),
 record_bytes bigint NOT NULL DEFAULT 0 CHECK(record_bytes BETWEEN 0 AND 67108864),
 -- SQL derives these finite recovery slots; product JSON cannot release them.
 common_plan jsonb NOT NULL DEFAULT '{"next":1,"sessions":2,"rebind":1,"resume":1}'
 CHECK(coalesce(jsonb_typeof(common_plan)='object' AND common_plan-ARRAY['next','sessions','rebind','resume']='{}'::jsonb
  AND common_plan->'next' IN ('0'::jsonb,'1'::jsonb) AND common_plan->'sessions' IN ('0'::jsonb,'1'::jsonb,'2'::jsonb)
  AND common_plan->'rebind' IN ('0'::jsonb,'1'::jsonb) AND common_plan->'resume' IN ('0'::jsonb,'1'::jsonb),false))
);
CREATE TABLE qh.execution_evidence (
 account_ref text NOT NULL REFERENCES qh.execution_account,
 kind text NOT NULL, id text NOT NULL, version integer NOT NULL CHECK(version>0),
 hash text NOT NULL CHECK(hash ~ '^[0-9a-f]{64}$'), wire jsonb NOT NULL,
 PRIMARY KEY(account_ref,kind,id,version), UNIQUE(account_ref,kind,id,version,hash),
 CHECK(octet_length(qh.ledger_canonical(wire))<=65536),
 CHECK(wire->>'environment'='synthetic'),
 CHECK(hash=qh.ledger_hash(wire->>'schema_name',wire->'payload'))
);
CREATE TABLE qh.execution_head (
 account_ref text NOT NULL REFERENCES qh.execution_account, kind text NOT NULL,
 id text NOT NULL, version integer NOT NULL, hash text NOT NULL,
 PRIMARY KEY(account_ref,kind,id),
 FOREIGN KEY(account_ref,kind,id,version,hash) REFERENCES qh.execution_evidence(account_ref,kind,id,version,hash)
);
CREATE TABLE qh.execution_claim (
 account_ref text NOT NULL REFERENCES qh.execution_account,
 environment text NOT NULL DEFAULT 'synthetic' CHECK(environment='synthetic'),
 candidate_id text NOT NULL, candidate_version integer NOT NULL CHECK(candidate_version>0),
 candidate_hash text NOT NULL CHECK(candidate_hash ~ '^[0-9a-f]{64}$'),
 intent_id text NOT NULL, PRIMARY KEY(environment,account_ref,candidate_id,candidate_version),
 UNIQUE(account_ref,intent_id)
);
CREATE TABLE qh.execution_intent (
 account_ref text NOT NULL REFERENCES qh.execution_account, intent_id text NOT NULL,
 candidate_id text NOT NULL, candidate_version integer NOT NULL, approval_id text NOT NULL,
 state text NOT NULL CHECK(state IN ('prepared','dispatching','unknown','acknowledged','partially_filled','filled','rejected','aborted_unsent','cancelled_remaining','expired_remaining')),
 version integer NOT NULL CHECK(version>0), body jsonb NOT NULL, hash text NOT NULL,
 PRIMARY KEY(account_ref,intent_id), UNIQUE(account_ref,approval_id),
 FOREIGN KEY(account_ref,intent_id) REFERENCES qh.execution_claim(account_ref,intent_id) DEFERRABLE INITIALLY DEFERRED,
 CHECK(body->>'environment'='synthetic' AND body->>'account_ref'=account_ref AND body->>'intent_id'=intent_id),
 CHECK(hash=qh.ledger_hash('OrderIntent',body)),
 CHECK(qh.ledger_decimal(body->'confirmed_quantity')::numeric>=0 AND qh.ledger_decimal(body->'confirmed_quantity')::numeric<=qh.ledger_decimal(body->'terms'->'quantity')::numeric)
);
ALTER TABLE qh.execution_claim ADD FOREIGN KEY(account_ref,intent_id) REFERENCES qh.execution_intent DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE qh.execution_reservation (
 account_ref text NOT NULL, intent_id text NOT NULL, id text NOT NULL,
 body jsonb NOT NULL, PRIMARY KEY(account_ref,id),
 FOREIGN KEY(account_ref,intent_id) REFERENCES qh.execution_intent,
 CHECK(body->>'intent_id'=intent_id),
 CHECK(body->>'component' IN ('principal','cost','quantity','risk')),
 CHECK(body->>'dimension' IN ('cash','quantity','risk')),
 CHECK(qh.ledger_decimal(body->'bound')::numeric>=0 AND qh.ledger_decimal(body->'held')::numeric>=0 AND
       qh.ledger_decimal(body->'used')::numeric>=0 AND qh.ledger_decimal(body->'released')::numeric>=0),
 CHECK((body->>'bound')::numeric=(body->>'held')::numeric+(body->>'used')::numeric+(body->>'released')::numeric),
 CHECK((body->>'settled')::numeric BETWEEN 0 AND (body->>'used')::numeric),
 CHECK((body->>'broker_reflected')::numeric BETWEEN 0 AND (body->>'used')::numeric)
);
CREATE UNIQUE INDEX execution_reservation_component ON qh.execution_reservation(account_ref,intent_id,(body->>'component'));
CREATE TABLE qh.execution_attempt (
 account_ref text NOT NULL, intent_id text NOT NULL, id text NOT NULL,
 action text NOT NULL CHECK(action IN ('submit','cancel')), body jsonb NOT NULL,
 PRIMARY KEY(account_ref,id), FOREIGN KEY(account_ref,intent_id) REFERENCES qh.execution_intent
);
CREATE UNIQUE INDEX execution_single_submit ON qh.execution_attempt(account_ref,intent_id) WHERE action='submit';
CREATE TABLE qh.execution_outbox (
 account_ref text NOT NULL, intent_id text NOT NULL, state text NOT NULL,
 PRIMARY KEY(account_ref,intent_id), FOREIGN KEY(account_ref,intent_id) REFERENCES qh.execution_intent DEFERRABLE INITIALLY DEFERRED,
 CHECK(state IN ('prepared','dispatching','unknown','acknowledged','partially_filled','filled','rejected','aborted_unsent','cancelled_remaining','expired_remaining'))
);
CREATE TABLE qh.execution_broker_inbox (
 account_ref text NOT NULL, issuer text NOT NULL, event_id text NOT NULL, revision integer NOT NULL CHECK(revision>0),
 payload_hash text NOT NULL CHECK(payload_hash ~ '^[0-9a-f]{64}$'), body jsonb NOT NULL, disposition text NOT NULL,
 PRIMARY KEY(account_ref,issuer,event_id,revision,payload_hash),
 FOREIGN KEY(account_ref) REFERENCES qh.execution_account
);
-- Immutable processing outcomes retain the original quarantine and explicit replay.
CREATE TABLE qh.execution_event_resolution (
 account_ref text NOT NULL, issuer text NOT NULL, event_id text NOT NULL, revision integer NOT NULL,
 payload_hash text NOT NULL, disposition text NOT NULL,
 PRIMARY KEY(account_ref,issuer,event_id,revision,payload_hash,disposition),
 FOREIGN KEY(account_ref,issuer,event_id,revision,payload_hash)
 REFERENCES qh.execution_broker_inbox(account_ref,issuer,event_id,revision,payload_hash)
);
CREATE TRIGGER execution_resolution_immutable BEFORE UPDATE OR DELETE ON qh.execution_event_resolution
 FOR EACH ROW EXECUTE FUNCTION qh.ledger_immutable();
CREATE TABLE qh.execution_budget (
 account_ref text NOT NULL REFERENCES qh.execution_account, owner text NOT NULL,
 reserved_records integer NOT NULL CHECK(reserved_records BETWEEN 0 AND 384),
 reserved_bytes bigint NOT NULL CHECK(reserved_bytes BETWEEN 0 AND 25165824),
 PRIMARY KEY(account_ref,owner)
);
CREATE TABLE qh.execution_cursor (
 account_ref text PRIMARY KEY REFERENCES qh.execution_account, cursor integer NOT NULL CHECK(cursor>=0)
);
CREATE TRIGGER execution_evidence_immutable BEFORE UPDATE OR DELETE ON qh.execution_evidence FOR EACH ROW EXECUTE FUNCTION qh.ledger_immutable();
CREATE TRIGGER execution_claim_immutable BEFORE UPDATE OR DELETE ON qh.execution_claim FOR EACH ROW EXECUTE FUNCTION qh.ledger_immutable();
CREATE TRIGGER execution_inbox_immutable BEFORE UPDATE OR DELETE ON qh.execution_broker_inbox FOR EACH ROW EXECUTE FUNCTION qh.ledger_immutable();

-- Execution transport can contain an initial version -1 and bounded aggregate deltas.
-- Each domain record still passes its own closed schema and 64KiB constraint.
CREATE FUNCTION qh.execution_wire_check(j json) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,qh AS $$
DECLARE x json;
BEGIN
 IF json_typeof(j)='object' THEN
   IF (SELECT count(*)<>count(DISTINCT key) FROM json_each(j)) THEN RAISE EXCEPTION 'execution_contract'; END IF;
   FOR x IN SELECT value FROM json_each(j) LOOP PERFORM qh.execution_wire_check(x); END LOOP;
 ELSIF json_typeof(j)='array' THEN
   FOR x IN SELECT value FROM json_array_elements(j) LOOP PERFORM qh.execution_wire_check(x); END LOOP;
 ELSIF json_typeof(j)='number' THEN
   IF j::text !~ '^-?(0|[1-9][0-9]*)$' OR length(j::text)>11 THEN RAISE EXCEPTION 'execution_contract'; END IF;
 END IF;
END $$;
CREATE FUNCTION qh.execution_wire(raw text) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,qh AS $$
DECLARE j json;
BEGIN
 IF raw IS NULL OR octet_length(raw)>67108864 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
 j:=raw::json; PERFORM qh.execution_wire_check(j); RETURN j::jsonb;
EXCEPTION WHEN invalid_text_representation OR character_not_in_repertoire OR invalid_parameter_value
 THEN RAISE EXCEPTION 'execution_contract';
END $$;
CREATE FUNCTION qh.execution_lock(a text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
BEGIN
 IF a NOT LIKE 'synthetic-account:%' THEN RAISE EXCEPTION 'execution_contract'; END IF;
 PERFORM 1 FROM qh.ledger_stream WHERE account_ref=a FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'execution_source'; END IF;
 PERFORM 1 FROM qh.execution_account WHERE account_ref=a FOR UPDATE;
 PERFORM 1 FROM qh.execution_head WHERE account_ref=a ORDER BY kind,id FOR UPDATE;
 RETURN 'true'::jsonb;
END $$;
CREATE FUNCTION qh.execution_load(a text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE r qh.execution_account; p jsonb; at_text text;
BEGIN
 PERFORM qh.execution_lock(a);
 SELECT * INTO r FROM qh.execution_account WHERE account_ref=a;
 RETURN CASE WHEN r.account_ref IS NULL THEN 'null'::jsonb ELSE jsonb_build_object('version',r.version,'state',r.state,'source_hash',r.source_hash) END;
END $$;
CREATE FUNCTION qh.execution_ledger(a text, operation text, payload text, at_text text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE j jsonb;
BEGIN
 PERFORM qh.execution_lock(a);
 IF operation='replay' THEN
   RETURN qh.ledger_replay(a,CASE WHEN payload='' THEN at_text ELSE payload END,at_text);
 ELSIF operation='events' THEN
   RETURN (SELECT coalesce(jsonb_agg(jsonb_build_object('body',body,'payload_hash',payload_hash,
     'canonicalization_version',canonicalization_version) ORDER BY sequence),'[]') FROM qh.ledger_event WHERE account_ref=a);
 ELSIF operation='append' THEN
   j:=qh.ledger_wire(payload);
   IF j->>'account_ref'<>a OR j->>'source_kind'<>'synthetic-execution' THEN RAISE EXCEPTION 'execution_contract'; END IF;
   RETURN qh.ledger_append(payload,at_text);
 END IF;
 RAISE EXCEPTION 'execution_contract';
END $$;
CREATE FUNCTION qh.execution_consume(a text,m text,h text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE n integer; result text;
BEGIN
 PERFORM qh.execution_lock(a);
 SELECT cursor INTO STRICT n FROM qh.ledger_outbox WHERE account_ref=a AND message_id=m AND payload_hash=h;
 result:=qh.ledger_consume('synthetic-execution',m,h);
 INSERT INTO qh.execution_cursor VALUES(a,n) ON CONFLICT(account_ref) DO UPDATE SET cursor=greatest(qh.execution_cursor.cursor,excluded.cursor);
 PERFORM qh.execution_check_budget(a);
 RETURN jsonb_build_object('result',result,'cursor',(SELECT cursor FROM qh.execution_cursor WHERE account_ref=a));
END $$;
CREATE FUNCTION qh.execution_event(a text,raw text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE j jsonb;
BEGIN
 PERFORM qh.execution_lock(a); j:=qh.execution_wire(raw);
 IF j->'body'->>'account_ref'<>a THEN RAISE EXCEPTION 'execution_contract'; END IF;
 INSERT INTO qh.execution_broker_inbox VALUES(a,j->'body'->>'issuer_instance',j->'body'->>'event_id',
 (j->'body'->>'revision')::integer,j->>'hash',j->'body',j->>'disposition') ON CONFLICT DO NOTHING;
 INSERT INTO qh.execution_event_resolution VALUES(a,j->'body'->>'issuer_instance',j->'body'->>'event_id',
 (j->'body'->>'revision')::integer,j->>'hash',j->>'disposition') ON CONFLICT DO NOTHING;
 RETURN 'true'::jsonb;
END $$;
CREATE FUNCTION qh.execution_patch(old jsonb,delta jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,qh AS $$
DECLARE entries jsonb:=coalesce(old->'map','[]'); change jsonb; prior jsonb; replacement jsonb; item jsonb;
BEGIN
 IF jsonb_typeof(delta) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'execution_contract'; END IF;
 FOR change IN SELECT value FROM jsonb_array_elements(delta) LOOP
   PERFORM qh.ledger_keys(change,ARRAY['key','mode','value']);
   IF jsonb_typeof(change->'key') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'execution_contract'; END IF;
   SELECT value->1 INTO prior FROM jsonb_array_elements(entries) WHERE value->0=change->'key';
   SELECT coalesce(jsonb_agg(value),'[]') INTO entries FROM jsonb_array_elements(entries) WHERE value->0 IS DISTINCT FROM change->'key';
   IF change->>'mode'='map' THEN
     PERFORM qh.ledger_keys(change->'value',ARRAY['upsert','remove']);
     replacement:=coalesce(prior->'map','[]');
     FOR item IN SELECT value FROM jsonb_array_elements(change->'value'->'remove') LOOP
       SELECT coalesce(jsonb_agg(value),'[]') INTO replacement FROM jsonb_array_elements(replacement) WHERE value->0 IS DISTINCT FROM item;
     END LOOP;
     FOR item IN SELECT value FROM jsonb_array_elements(change->'value'->'upsert') LOOP
       IF jsonb_array_length(item) IS DISTINCT FROM 2 THEN RAISE EXCEPTION 'execution_contract'; END IF;
       SELECT coalesce(jsonb_agg(value),'[]') INTO replacement FROM jsonb_array_elements(replacement) WHERE value->0 IS DISTINCT FROM item->0;
       replacement:=replacement||jsonb_build_array(item);
     END LOOP;
     replacement:=jsonb_build_object('map',replacement);
   ELSIF change->>'mode'='value' THEN replacement:=change->'value';
   ELSIF change->>'mode'='remove' THEN CONTINUE;
   ELSE RAISE EXCEPTION 'execution_contract'; END IF;
   entries:=entries||jsonb_build_array(jsonb_build_array(change->'key',replacement));
 END LOOP;
 RETURN jsonb_build_object('map',entries);
END $$;
CREATE FUNCTION qh.execution_lookup_business(new_state jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,qh AS $$
 SELECT jsonb_object_agg(value->>0,value->1) FROM jsonb_array_elements(new_state->'map')
 WHERE value->>0 NOT IN ('commands','nonces','receipts','version')
$$;
CREATE FUNCTION qh.execution_save(a text,raw text,expected_text text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE j jsonb; old qh.execution_account; x jsonb; r jsonb; w jsonb; prev qh.execution_evidence;
 prior qh.execution_intent; n integer; b bigint; allocated integer; allocated_bytes bigint; plan jsonb; new_intent boolean:=false; rec jsonb; before_charge jsonb; after_charge jsonb; completion_step boolean:=false;
BEGIN
 IF raw IS NULL OR octet_length(raw)>67108864 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
 j:=qh.execution_wire(raw);
 PERFORM qh.ledger_keys(j,ARRAY['state_delta','generation','mode','fence','source_hash','evidence','heads','intents','reservations','attempts','closed_owners']);
 PERFORM qh.execution_lock(a);
 SELECT * INTO old FROM qh.execution_account WHERE account_ref=a;
 IF j ? 'state_delta' THEN j:=(j-'state_delta')||jsonb_build_object('state',qh.execution_patch(old.state,j->'state_delta')); END IF;
 IF coalesce(old.version,-1)<>expected_text::integer THEN RAISE EXCEPTION 'execution_version'; END IF;
 IF old.account_ref IS NOT NULL AND old.generation=j->>'generation' AND EXISTS(
   SELECT 1 FROM jsonb_array_elements(qh.execution_map_get(old.state,'"commands"')->'map') p
    WHERE qh.execution_map_get(qh.execution_map_get(j->'state','"commands"'),p->0) IS NULL)
 THEN
   IF j->'evidence'<>'[]'::jsonb OR j->'heads'<>'[]'::jsonb OR j->'intents'<>'[]'::jsonb
    OR j->>'mode' IS DISTINCT FROM old.mode OR (j->>'fence')::integer IS DISTINCT FROM old.fence
    OR j->>'source_hash' IS DISTINCT FROM old.source_hash
    OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(j->'closed_owners') x(owner)
      WHERE NOT EXISTS(SELECT 1 FROM qh.execution_budget b WHERE b.account_ref=a AND b.owner=x.owner AND b.closed))
    OR j->'reservations'<>'[]'::jsonb OR j->'attempts'<>'[]'::jsonb
    OR (qh.execution_lookup_business(old.state) IS DISTINCT FROM qh.execution_lookup_business(j->'state'))
   THEN RAISE EXCEPTION 'execution_atomicity'; END IF;
 END IF;
 IF NOT coalesce(j->>'mode' IN ('running','stopped','reconciling','faulted'),false) OR j->>'generation' IS NULL THEN RAISE EXCEPTION 'execution_contract'; END IF;
 IF old.account_ref IS NOT NULL THEN
   before_charge:=qh.execution_common_charge(a);
   -- Only already-funded stages carry the monotonic completion promise.
   -- New sessions invalidating a preparation are elective and must fit again.
   completion_step:=(old.generation IS DISTINCT FROM j->>'generation' AND old.common_plan->>'next'='1') OR
    (old.common_plan->>'rebind'='1' AND NOT (old.mode='stopped' AND j->>'mode'='reconciling' AND EXISTS(
      SELECT 1 FROM qh.execution_evidence e WHERE e.account_ref=a AND e.kind='runtime'
       AND e.wire->'payload'->>'authority_generation'=old.generation AND e.wire->'payload'->>'kind'='explicit_synthetic_stop'))
      AND EXISTS(SELECT 1 FROM jsonb_array_elements(j->'evidence') AS stage_item(value)
      WHERE stage_item.value->'wire'->>'schema_name'='ExecutionReconciliation' AND stage_item.value->'wire'->'payload'->>'result'='matched')) OR
    (old.common_plan->>'resume'='1' AND old.common_plan->>'rebind'='0' AND j->>'mode'='running') OR
    (old.common_plan->>'sessions' IN ('1','2') AND old.common_plan->>'rebind'='1' AND EXISTS(
      SELECT 1 FROM jsonb_array_elements(j->'evidence') AS stage_item(value) WHERE stage_item.value->'wire'->>'schema_name'='SessionRecord'
       AND stage_item.value->'wire'->'payload'->'state_version'='1'::jsonb)) OR
    EXISTS(SELECT 1 FROM jsonb_array_elements(j->'evidence') AS stage_item(value) WHERE stage_item.value->'wire'->>'schema_name'='SyntheticRuntimeEvidence'
      AND stage_item.value->'wire'->'payload'->>'kind' IN ('explicit_synthetic_stop','explicit_synthetic_disconnect')) OR
    -- Unconsumed protective closure (including atomic challenge+withdraw),
    -- authenticated rejection, and expiry/invalidation must spend their own
    -- funded terminal/repair credits. Consumed commands belong to their owner;
    -- successful approve/admit remain elective. Existing command authentication
    -- still binds actor/action/nonce/hash; this only selects the budget guard.
    EXISTS(SELECT 1 FROM jsonb_array_elements(j->'evidence') AS terminal_item(value)
      WHERE terminal_item.value->'wire'->>'schema_name'='ActionReceipt'
       AND NOT EXISTS(SELECT 1 FROM qh.execution_evidence e WHERE e.account_ref=a AND e.kind='receipt'
        AND e.wire->'payload'->>'command_id'=terminal_item.value->'wire'->'payload'->>'command_id')
       AND NOT EXISTS(SELECT 1 FROM qh.execution_intent i WHERE i.account_ref=a
        AND i.approval_id=terminal_item.value->'wire'->'payload'->'target_ref'->>'id')
       AND (terminal_item.value->'wire'->'payload'->>'action' IN ('revoke','withdraw') OR
        EXISTS(SELECT 1 FROM jsonb_array_elements(j->'evidence') AS invalidation_item(value)
         WHERE invalidation_item.value->'wire'->>'schema_name'='ApprovalRecord'
          AND invalidation_item.value->'wire'->'payload'->>'approval_id'=terminal_item.value->'wire'->'payload'->'target_ref'->>'id'
          AND invalidation_item.value->'wire'->'payload'->>'state' IN ('expired','invalidated'))));
 END IF;
 IF old.account_ref IS NULL THEN
   INSERT INTO qh.execution_account(account_ref,generation,mode,state,source_hash) VALUES(a,j->>'generation',j->>'mode',j->'state',j->>'source_hash');
 END IF;
 FOR x IN SELECT value FROM jsonb_array_elements(j->'evidence') LOOP
   r:=x->'ref'; w:=x->'wire';
   IF (w->'payload' ? 'account_ref') AND w->'payload'->>'account_ref'<>a THEN RAISE EXCEPTION 'execution_contract'; END IF;
   SELECT * INTO prev FROM qh.execution_evidence WHERE account_ref=a AND kind=r->>'kind' AND id=r->>'id' AND version=(r->>'version')::integer;
   IF FOUND THEN
     IF prev.hash<>r->>'sha256' OR prev.wire<>w THEN RAISE EXCEPTION 'execution_collision'; END IF;
   ELSE
     IF r->>'kind' IN ('approval','session','withdrawal') AND (r->>'version')::integer>1 THEN
       IF NOT EXISTS(SELECT 1 FROM qh.execution_evidence WHERE account_ref=a AND kind=r->>'kind' AND id=r->>'id' AND version=(r->>'version')::integer-1 AND hash=w->'payload'->'previous_ref'->>'sha256') THEN RAISE EXCEPTION 'execution_version'; END IF;
     END IF;
     INSERT INTO qh.execution_evidence VALUES(a,r->>'kind',r->>'id',(r->>'version')::integer,r->>'sha256',w);
   END IF;
 END LOOP;
 FOR x IN SELECT value FROM jsonb_array_elements(j->'heads') LOOP
   INSERT INTO qh.execution_head VALUES(a,x->>'kind',x->>'id',(x->>'version')::integer,x->>'sha256')
   ON CONFLICT(account_ref,kind,id) DO UPDATE SET version=excluded.version,hash=excluded.hash WHERE excluded.version>=qh.execution_head.version;
 END LOOP;
 FOR x IN SELECT value FROM jsonb_array_elements(j->'intents') LOOP
   SELECT * INTO prior FROM qh.execution_intent WHERE account_ref=a AND intent_id=x->>'intent_id';
   IF FOUND THEN
     IF (prior.body-ARRAY['state','state_version','previous_ref','confirmed_quantity','observed_quantity','attempt_ref','broker_order_id','accounting']) IS DISTINCT FROM
        (x-ARRAY['state','state_version','previous_ref','confirmed_quantity','observed_quantity','attempt_ref','broker_order_id','accounting']) OR
        (x->>'state_version')::integer NOT BETWEEN prior.version AND prior.version+1 OR
        ((x->>'state_version')::integer=prior.version AND prior.body<>x) OR
        ((x->>'state_version')::integer=prior.version+1 AND x->'previous_ref' IS DISTINCT FROM jsonb_build_object('kind','intent','id',prior.intent_id,'version',prior.version,'canonicalization_version','qh-canonical-json-v1','sha256',prior.hash))
     THEN RAISE EXCEPTION 'execution_version'; END IF;
   ELSE
     IF x->>'state' IS DISTINCT FROM 'prepared' OR (x->>'state_version')::integer IS DISTINCT FROM 1 OR x->'previous_ref' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'execution_contract'; END IF;
     new_intent:=true;
     INSERT INTO qh.execution_claim VALUES(a,'synthetic',x->'candidate_ref'->>'id',(x->'candidate_ref'->>'version')::integer,x->'candidate_ref'->>'sha256',x->>'intent_id');
     INSERT INTO qh.execution_budget(account_ref,owner,reserved_records,reserved_bytes) VALUES(a,x->>'intent_id',384,25165824);
   END IF;
   IF prior.intent_id IS NOT NULL AND prior.state<>x->>'state' AND NOT (
       (prior.state='prepared' AND x->>'state' IN ('dispatching','aborted_unsent')) OR
       (prior.state='dispatching' AND x->>'state' IN ('aborted_unsent','unknown','acknowledged','partially_filled','filled','rejected')) OR
       (prior.state='unknown' AND x->>'state' IN ('aborted_unsent','acknowledged','partially_filled','filled','rejected','cancelled_remaining','expired_remaining')) OR
       (prior.state='acknowledged' AND x->>'state' IN ('unknown','partially_filled','filled','cancelled_remaining','expired_remaining')) OR
       (prior.state='partially_filled' AND x->>'state' IN ('unknown','filled','cancelled_remaining','expired_remaining')) OR
       (prior.state='filled' AND x->>'state' IN ('unknown','partially_filled')))
     THEN RAISE EXCEPTION 'execution_transition'; END IF;
   INSERT INTO qh.execution_intent VALUES(a,x->>'intent_id',x->'candidate_ref'->>'id',(x->'candidate_ref'->>'version')::integer,
     x->'approval_ref'->>'id',x->>'state',(x->>'state_version')::integer,x,qh.ledger_hash('OrderIntent',x))
   ON CONFLICT(account_ref,intent_id) DO UPDATE SET state=excluded.state,version=excluded.version,body=excluded.body,hash=excluded.hash;
   INSERT INTO qh.execution_outbox VALUES(a,x->>'intent_id',x->>'state') ON CONFLICT(account_ref,intent_id) DO UPDATE SET state=excluded.state;
 END LOOP;
 FOR x IN SELECT value FROM jsonb_array_elements(j->'reservations') LOOP
   INSERT INTO qh.execution_reservation VALUES(a,x->>'intent_id',x->>'reservation_id',x)
   ON CONFLICT(account_ref,id) DO UPDATE SET body=excluded.body;
 END LOOP;
 FOR x IN SELECT value FROM jsonb_array_elements(j->'attempts') LOOP
   INSERT INTO qh.execution_attempt VALUES(a,x->>'intent_id',x->>'attempt_id',x->>'action',x)
   ON CONFLICT(account_ref,id) DO UPDATE SET body=excluded.body;
 END LOOP;
 -- consumed ↔ candidate claim/intent/outbox; no standalone consume is possible at save.
 IF EXISTS(SELECT 1 FROM qh.execution_head h JOIN qh.execution_evidence e USING(account_ref,kind,id,version,hash)
   WHERE h.account_ref=a AND h.kind='approval' AND e.wire->'payload'->>'state'='consumed'
   AND NOT EXISTS(SELECT 1 FROM qh.execution_intent i JOIN qh.execution_outbox o USING(account_ref,intent_id)
     WHERE i.account_ref=a AND i.approval_id=h.id AND i.intent_id=e.wire->'payload'->>'consumed_intent_id'))
 OR EXISTS(SELECT 1 FROM qh.execution_intent i WHERE i.account_ref=a AND NOT EXISTS(
   SELECT 1 FROM qh.execution_head h JOIN qh.execution_evidence e USING(account_ref,kind,id,version,hash)
   WHERE h.account_ref=a AND h.kind='approval' AND h.id=i.approval_id AND e.wire->'payload'->>'state'='consumed'))
 THEN RAISE EXCEPTION 'execution_atomicity'; END IF;
 SELECT count(*) INTO n FROM qh.execution_intent WHERE account_ref=a AND state NOT IN ('filled','rejected','aborted_unsent','cancelled_remaining','expired_remaining');
 IF n>2 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
 UPDATE qh.execution_budget SET closed=true WHERE account_ref=a AND j->'closed_owners' ? owner;
 -- Bootstrap slots move into actual session rows + their live holds. One
 -- reserved restart moves into the next bootstrap, rather than being renewed
 -- during recovery. A further elective generation must fit a new capsule.
 SELECT common_plan INTO plan FROM qh.execution_account WHERE account_ref=a;
 IF old.account_ref IS NOT NULL AND old.generation IS DISTINCT FROM j->>'generation' THEN
   plan:='{"next":0,"sessions":2,"rebind":1,"resume":1}';
 END IF;
 SELECT count(*) INTO n FROM jsonb_array_elements(j->'evidence') AS item(value)
  WHERE item.value->'wire'->>'schema_name'='SessionRecord' AND item.value->'wire'->'payload'->'state_version'='1'::jsonb
   AND item.value->'wire'->'payload'->>'authority_generation'=j->>'generation';
 plan:=jsonb_set(plan,'{sessions}',to_jsonb(greatest(0,(plan->>'sessions')::integer-n)));
 -- A recovery preparation belongs to the exact current read-set. An elective
 -- session/source/protection change must fund its replacement before committing.
 IF j->>'mode'='reconciling' THEN plan:=jsonb_set(plan,'{resume}','1'); END IF;
 IF j->>'mode'='running' THEN plan:=jsonb_set(plan,'{resume}','0'); END IF;
 rec:=qh.execution_map_get(j->'state','"reconciliation"')->'wire'->'payload';
 plan:=jsonb_set(plan,'{rebind}',to_jsonb(CASE WHEN plan->>'resume'='1' AND NOT coalesce(
   rec->>'result'='matched' AND rec->>'generation'=j->>'generation' AND rec->'fence'=j->'fence'
   AND rec->'account_version'=qh.execution_map_get(j->'state','"version"')
   AND rec->>'source_hash'=j->>'source_hash'
   AND rec->>'validator_version'='q27-account-current-v1' AND rec->>'current_identity' ~ '^[0-9a-f]{64}$'
   AND rec->>'valid_from' IS NOT NULL AND rec->>'valid_to' IS NOT NULL
   AND (rec->>'valid_from')::timestamptz<=(rec->>'checked_at')::timestamptz
   AND (rec->>'checked_at')::timestamptz<(rec->>'valid_to')::timestamptz AND EXISTS(
    SELECT 1 FROM qh.execution_head h JOIN qh.execution_evidence e USING(account_ref,kind,id,version,hash)
    WHERE h.account_ref=a AND h.kind='session' AND h.id=rec->>'session_id'
     AND e.wire->'payload'->>'authority_generation'=j->>'generation' AND e.wire->'payload'->>'state'='running'),false)
   THEN 1 ELSE 0 END));
 IF new_intent THEN plan:=jsonb_set(plan,'{next}','1'); END IF;
 UPDATE qh.execution_account SET common_plan=plan WHERE account_ref=a;
 b:=octet_length(qh.ledger_canonical(j->'state'));
 UPDATE qh.execution_account SET version=coalesce(old.version,0)+1,state=j->'state',mode=j->>'mode',generation=j->>'generation',
   fence=(j->>'fence')::integer,source_hash=j->>'source_hash',record_bytes=b WHERE account_ref=a;
 PERFORM qh.execution_check_budget(a);
 IF completion_step THEN
   after_charge:=qh.execution_common_charge(a);
   IF (after_charge->>'records')::bigint>(before_charge->>'records')::bigint OR
      (after_charge->>'bytes')::bigint>(before_charge->>'bytes')::bigint
   THEN RAISE EXCEPTION 'execution_completion'; END IF;
 END IF;
 RETURN to_jsonb(coalesce(old.version,0)+1);
END $$;
CREATE FUNCTION qh.execution_fingerprint(a text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE result jsonb:='{}'; rows jsonb; relation_name text;
BEGIN
 PERFORM qh.execution_lock(a);
 -- 고정 테이블 allowlist. 모든 승인/경제/전달/예산 행을 비교한다.
 FOREACH relation_name IN ARRAY ARRAY['execution_account','execution_evidence','execution_head',
  'execution_claim','execution_intent','execution_reservation','execution_attempt','execution_outbox',
  'execution_broker_inbox','execution_event_resolution','execution_budget','execution_cursor','ledger_stream','ledger_event',
  'ledger_journal','ledger_decision','ledger_projection','ledger_outbox','ledger_workstate'] LOOP
   EXECUTE format('SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),''[]'') FROM qh.%I t WHERE account_ref=$1',relation_name) INTO rows USING a;
   result:=result||jsonb_build_object(relation_name,rows);
 END LOOP;
 SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') INTO rows FROM qh.ledger_inbox t JOIN qh.ledger_outbox o USING(message_id) WHERE o.account_ref=a;
 result:=result||jsonb_build_object('ledger_inbox',rows);
 SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') INTO rows FROM qh.ledger_delivery t JOIN qh.ledger_outbox o USING(message_id) WHERE o.account_ref=a;
 result:=result||jsonb_build_object('ledger_delivery',rows);
 SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') INTO rows FROM qh.ledger_inbox_collision t JOIN qh.ledger_outbox o USING(message_id) WHERE o.account_ref=a;
 RETURN result||jsonb_build_object('ledger_inbox_collision',rows);
END $$;



-- Closed Python/SQL shapes are literal migration data, not caller supplied rules.
CREATE FUNCTION qh.execution_shape(schema_name text,j jsonb) RETURNS void
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,qh AS $$
DECLARE shapes jsonb:='{"ExecutionRef":{"kind":["enum",["policy","source","risk","intent","reservation","attempt","event","query","cancel","reconciliation","runtime","receipt","fixture"]],"id":["identifier"],"version":["positive_count"],"canonicalization_version":["enum",["qh-canonical-json-v1"]],"sha256":["hash"]},"SyntheticExecutionPolicy":{"policy_id":["identifier"],"version":["positive_count"],"environment":["enum",["synthetic"]],"account_ref":["identifier"],"target_policy_ref":["shape","TargetRef"],"valid_from":["instant"],"valid_to":["instant"],"max_gross_turnover":["positive"],"fixture_ref":["shape","ExecutionRef"]},"TargetRef":{"kind":["enum",["request","policy","facts","snapshot","projection","statement","event","performance","strategy","plan","candidate","result","capability","cost","rights","catalog","calendar","timezone","market","obligation_source"]],"id":["identifier"],"version":["version"],"canonicalization_version":["enum",["qh-canonical-json-v1","context-source-facts-v1"]],"sha256":["hash"]},"ExecutionAccountState":{"account_ref":["identifier"],"environment":["enum",["synthetic"]],"mode":["enum",["running","stopped","reconciling","faulted"]],"state_version":["count"],"generation":["identifier"],"issuer_instance":["identifier"],"fence":["positive_count"],"owner":["identifier"],"lease_deadline":["instant"],"policy_ref":["shape","ExecutionRef"],"source_ref":["optional",["shape","ExecutionRef"]],"ledger_cursor":["count"],"clock_epoch":["count"],"reconciliation_ref":["optional",["shape","ExecutionRef"]]},"ExecutionSourceSet":{"source_id":["identifier"],"account_ref":["identifier"],"environment":["enum",["synthetic"]],"candidate_ref":["shape","TargetRef"],"plan_ref":["shape","TargetRef"],"result_ref":["shape","TargetRef"],"request_ref":["shape","TargetRef"],"input_refs":["sequence",["shape","TargetRef"]],"scope":["shape","TargetScope"],"query_ref":["shape","ExecutionRef"],"ledger_cursor":["count"],"execution_version":["count"],"generation":["identifier"],"fence":["positive_count"],"checked_at":["instant"],"valid_to":["instant"]},"TargetScope":{"markets":["sequence",["enum",["KR","US"]]],"currencies":["sequence",["enum",["KRW","USD"]]],"positions":["sequence",["shape","PositionKey"]]},"PositionKey":{"instrument_id":["identifier"],"venue_id":["identifier"],"mapping_version":["identifier"],"unit":["identifier"]},"ExecutionCash":{"currency":["enum",["USD","KRW"]],"ledger":["nonnegative"],"outstanding":["nonnegative"],"floor":["nonnegative"],"broker":["nonnegative"],"unreflected":["nonnegative"],"debits":["nonnegative"],"available":["numeric"]},"ExecutionRiskDecision":{"risk_id":["identifier"],"account_ref":["identifier"],"candidate_ref":["shape","TargetRef"],"approval_ref":["shape","ApprovalRef"],"terms_hash":["hash"],"source_ref":["shape","ExecutionRef"],"policy_ref":["shape","ExecutionRef"],"checked_at":["instant"],"valid_to":["instant"],"account_version":["count"],"ledger_cursor":["count"],"generation":["identifier"],"fence":["positive_count"],"cash":["sequence",["shape","ExecutionCash"]],"outcome":["enum",["allow","deny","unknown"]],"reasons":["sequence",["enum",["invalid_contract","authority_denied","storage_failure","source_unresolved","stale_source","risk_blocked","capacity_exceeded","version_conflict","event_conflict","reconciliation_required","commit_failed","handoff_unknown","unsupported_correction"]]]},"ApprovalRef":{"kind":["enum",["fixture","policy","principal","session","evidence","presentation","challenge","approval","receipt","withdrawal","runtime"]],"id":["identifier"],"version":["positive_count"],"canonicalization_version":["enum",["qh-canonical-json-v1"]],"sha256":["hash"]},"OrderIntent":{"intent_id":["identifier"],"account_ref":["identifier"],"environment":["enum",["synthetic"]],"candidate_ref":["shape","TargetRef"],"approval_ref":["shape","ApprovalRef"],"terms":["shape","OrderTerms"],"request_hash":["hash"],"admission_risk_ref":["shape","ExecutionRef"],"generation":["identifier"],"fence":["positive_count"],"state":["enum",["prepared","dispatching","unknown","acknowledged","partially_filled","filled","rejected","aborted_unsent","cancelled_remaining","expired_remaining"]],"state_version":["positive_count"],"previous_ref":["optional",["shape","ExecutionRef"]],"confirmed_quantity":["nonnegative"],"observed_quantity":["nonnegative"],"attempt_ref":["optional",["shape","ExecutionRef"]],"broker_order_id":["optional",["identifier"]],"accounting":["enum",["complete","incomplete"]]},"OrderTerms":{"account_ref":["identifier"],"valid_from":["instant"],"valid_to":["instant"],"position":["shape","PositionKey"],"mapping_ref":["shape","TargetRef"],"market":["enum",["KR","US"]],"currency":["enum",["KRW","USD"]],"side":["enum",["buy","sell"]],"quantity":["positive"],"reference_price":["positive"],"limit_price":["positive"],"capability":["shape","SyntheticOrderCapability"],"cost_rule":["shape","SyntheticCostRule"],"fee_bound":["nonnegative"],"tax_bound":["nonnegative"],"cost_bound":["nonnegative"],"principal_bound":["nonnegative"],"minimum_sale_proceeds":["nonnegative"],"maximum_burden":["nonnegative"],"cumulative_burden":["nonnegative"],"remaining_capacity":["numeric"]},"SyntheticOrderCapability":{"schema_version":["version"],"environment":["enum",["synthetic"]],"account_ref":["identifier"],"valid_from":["instant"],"valid_to":["instant"],"capability_id":["identifier"],"position":["shape","PositionKey"],"market":["enum",["KR","US"]],"currency":["enum",["KRW","USD"]],"known_at":["instant"],"catalog_ref":["shape","TargetRef"],"calendar_ref":["shape","TargetRef"],"order_kind":["enum",["limit"]],"time_in_force":["enum",["day"]],"tick":["positive"],"lot":["positive"],"min_quantity":["positive"],"max_quantity":["positive"],"min_notional":["nonnegative"],"max_notional":["positive"],"session_kind":["enum",["regular"]],"partial_fill_basis":["enum",["whole_order_aggregate"]]},"SyntheticCostRule":{"schema_version":["version"],"environment":["enum",["synthetic"]],"account_ref":["identifier"],"valid_from":["instant"],"valid_to":["instant"],"rule_id":["identifier"],"market":["enum",["KR","US"]],"currency":["enum",["KRW","USD"]],"side":["enum",["buy","sell"]],"fee_fixed":["nonnegative"],"fee_per_share":["nonnegative"],"tax_fixed":["nonnegative"],"tax_per_share":["nonnegative"],"money_quantum":["positive"],"rounding":["enum",["ceiling"]],"charging_basis":["enum",["whole_order_aggregate"]]},"ReservationSlice":{"reservation_id":["identifier"],"intent_id":["identifier"],"obligation_id":["identifier"],"component":["enum",["principal","cost","quantity","risk"]],"dimension":["enum",["cash","quantity","risk"]],"currency_or_unit":["identifier"],"window_start":["instant"],"window_end":["instant"],"bound":["nonnegative"],"held":["nonnegative"],"used":["nonnegative"],"released":["nonnegative"],"broker_reflected":["nonnegative"],"settled":["nonnegative"],"source_cutoff":["instant"],"ledger_refs":["sequence",["identifier"]]},"DispatchAttempt":{"attempt_id":["identifier"],"intent_id":["identifier"],"action":["enum",["submit","cancel"]],"request_hash":["hash"],"generation":["identifier"],"fence":["positive_count"],"egress_instance":["identifier"],"state":["enum",["armed","handed_off","result_stored","unknown","proven_unsent"]],"recorded_at":["instant"],"receipt_ref":["optional",["shape","ExecutionRef"]]},"SyntheticBrokerReceipt":{"receipt_id":["identifier"],"issuer_instance":["identifier"],"account_ref":["identifier"],"intent_id":["identifier"],"attempt_id":["identifier"],"request_hash":["hash"],"broker_order_id":["optional",["identifier"]],"sequence":["positive_count"],"issued_at":["instant"],"kind":["enum",["accepted","final_reject","proven_unsent","cancel_ack"]],"journal_id":["identifier"]},"SyntheticOrderEvent":{"event_id":["identifier"],"issuer_instance":["identifier"],"account_ref":["identifier"],"intent_id":["identifier"],"request_hash":["hash"],"broker_order_id":["identifier"],"revision":["positive_count"],"predecessor_revision":["optional",["positive_count"]],"kind":["enum",["fill","cancelled_remaining","expired_remaining","settlement"]],"semantics":["enum",["delta","cumulative"]],"execution_id":["identifier"],"stream_sequence":["positive_count"],"quantity":["nonnegative"],"price":["positive"],"fee":["optional",["nonnegative"]],"tax":["optional",["nonnegative"]],"effective_at":["instant"],"issued_at":["instant"],"receipt_ref":["shape","ExecutionRef"],"journal_id":["identifier"]},"BrokerCash":{"currency":["enum",["USD","KRW"]],"amount":["nonnegative"],"included_components":["sequence",["identifier"]]},"BrokerHoldReflection":{"obligation_id":["identifier"],"quantity":["positive"]},"BrokerQuantity":{"position":["shape","PositionKey"],"quantity":["nonnegative"],"included_components":["sequence",["identifier"]],"hold_reflections":["sequence",["shape","BrokerHoldReflection"]]},"SyntheticExecutionQuery":{"query_id":["identifier"],"issuer_instance":["identifier"],"account_ref":["identifier"],"environment":["enum",["synthetic"]],"requested_scope":["shape","TargetScope"],"covered_scope":["shape","TargetScope"],"missing_scope":["sequence",["identifier"]],"status":["enum",["complete","partial","unknown"]],"as_of":["instant"],"cutoff_sequence":["count"],"cash":["sequence",["shape","BrokerCash"]],"sellable":["sequence",["shape","BrokerQuantity"]],"receipts":["sequence",["shape","ExecutionRef"]],"events":["sequence",["shape","ExecutionRef"]],"statement_ref":["shape","TargetRef"],"journal_id":["identifier"],"journal_sequence":["count"],"request_attempts":["sequence",["shape","DispatchAttempt"]]},"CancelCommand":{"command_id":["identifier"],"nonce":["identifier"],"account_ref":["identifier"],"session_id":["identifier"],"generation":["identifier"],"intent_ref":["shape","ExecutionRef"],"broker_order_id":["identifier"],"maximum_remaining":["nonnegative"],"expected_version":["positive_count"],"issued_at":["instant"],"expires_at":["instant"],"state":["enum",["issued","armed","acknowledged","unknown","confirmed"]],"attempt_ref":["optional",["shape","ExecutionRef"]],"state_version":["positive_count"]},"ExecutionReconciliation":{"reconciliation_id":["identifier"],"account_ref":["identifier"],"query_ref":["shape","ExecutionRef"],"ledger_cursor":["count"],"account_version":["count"],"generation":["identifier"],"fence":["positive_count"],"checked_at":["instant"],"result":["enum",["matched","unresolved"]],"unresolved":["sequence",["identifier"]],"session_id":["optional",["identifier"]],"source_hash":["optional",["hash"]],"current_identity":["optional",["hash"]],"validator_version":["optional",["identifier"]],"valid_from":["optional",["instant"]],"valid_to":["optional",["instant"]]},"ExecutionCommandReceipt":{"command_id":["identifier"],"payload_hash":["hash"],"session_id":["identifier"],"action":["enum",["cancel","resume","reconcile","withdraw"]],"target_id":["identifier"],"expected_version":["count"],"recorded_at":["instant"],"account_version":["count"],"result_ref":["shape","ExecutionRef"]},"ApprovalLimits":{"canonical_bytes":["positive_count"],"resolved_bytes":["positive_count"],"refs":["positive_count"],"string_utf8_bytes":["positive_count"],"rendered_utf8_bytes":["positive_count"],"total_records":["positive_count"],"total_bytes":["positive_count"]},"SyntheticApprovalPolicy":{"policy_id":["identifier"],"version":["positive_count"],"environment":["enum",["synthetic"]],"account_ref":["identifier"],"valid_from":["instant"],"valid_to":["instant"],"approval_ttl_seconds":["positive_count"],"challenge_ttl_seconds":["positive_count"],"session_ttl_seconds":["positive_count"],"liveness_timeout_seconds":["positive_count"],"allowed_actions":["sequence",["enum",["approve","deny","revoke","withdraw","present","admit","dispatch","query","stop","resume","heartbeat","disconnect","session","runtime","policy"]]],"limits":["shape","ApprovalLimits"],"fixture_manifest_ref":["shape","ApprovalRef"]},"PrincipalEvidence":{"principal_id":["identifier"],"issuer_id":["identifier"],"issuer_instance_id":["identifier"],"authority_generation":["identifier"],"environment":["enum",["synthetic"]],"account_ref":["identifier"],"role":["enum",["approver","controller","reporting","research"]],"allowed_actions":["sequence",["enum",["approve","deny","revoke","withdraw","present","admit","dispatch","query","stop","resume","heartbeat","disconnect","session","runtime","policy"]]],"issued_at":["instant"],"expires_at":["instant"],"provenance":["enum",["synthetic_fixture"]],"fixture_manifest_ref":["shape","ApprovalRef"]},"SessionRecord":{"session_id":["identifier"],"principal_ref":["shape","ApprovalRef"],"authority_generation":["identifier"],"environment":["enum",["synthetic"]],"account_ref":["identifier"],"policy_ref":["shape","ApprovalRef"],"code_version":["identifier"],"state":["enum",["running","paused","faulted","invalidated"]],"state_version":["positive_count"],"started_at":["instant"],"expires_at":["instant"],"last_control_event_ref":["shape","ApprovalRef"],"liveness_deadline":["instant"],"clock_epoch":["identifier"],"previous_ref":["optional",["shape","ApprovalRef"]]},"CandidateEvidence":{"candidate_ref":["shape","TargetRef"],"plan_ref":["shape","TargetRef"],"result_ref":["shape","TargetRef"],"request_ref":["shape","TargetRef"],"input_refs":["sequence",["shape","TargetRef"]],"current_rights_refs":["sequence",["shape","TargetRef"]],"source_revision_refs":["sequence",["shape","TargetRef"]],"checked_at":["instant"],"checker_version":["identifier"],"fixture_manifest_ref":["shape","ApprovalRef"]},"PresentationRecord":{"presentation_id":["identifier"],"candidate_ref":["shape","TargetRef"],"candidate_render_version":["enum",["target-ko-v1"]],"approval_render_version":["enum",["approval-ko-v1"]],"locale":["enum",["ko-KR"]],"principal_ref":["shape","ApprovalRef"],"session_ref":["shape","ApprovalRef"],"authority_generation":["identifier"],"action":["enum",["submit_candidate_once"]],"approval_policy_ref":["shape","ApprovalRef"],"valid_from":["instant"],"expires_at":["instant"],"rendered_text":["string",16384],"candidate_evidence_ref":["shape","ApprovalRef"],"rendered_at":["instant"]},"ActionChallenge":{"challenge_id":["identifier"],"command_id":["identifier"],"nonce":["identifier"],"action":["enum",["approve","deny","revoke","withdraw","present","admit","dispatch","query","stop","resume","heartbeat","disconnect","session","runtime","policy"]],"principal_ref":["shape","ApprovalRef"],"session_id":["identifier"],"authority_generation":["identifier"],"environment":["enum",["synthetic"]],"account_ref":["identifier"],"target_ref":["shape","ApprovalRef"],"presentation_ref":["shape","ApprovalRef"],"expected_state_version":["positive_count"],"issued_at":["instant"],"expires_at":["instant"]},"ApprovalRecord":{"approval_id":["identifier"],"state":["enum",["pending","approved","denied","revoked","expired","invalidated","consumed"]],"state_version":["positive_count"],"previous_ref":["optional",["shape","ApprovalRef"]],"principal_ref":["shape","ApprovalRef"],"session_id":["identifier"],"authority_generation":["identifier"],"environment":["enum",["synthetic"]],"account_ref":["identifier"],"candidate_ref":["shape","TargetRef"],"presentation_ref":["shape","ApprovalRef"],"candidate_evidence_ref":["shape","ApprovalRef"],"target_policy_ref":["shape","TargetRef"],"approval_policy_ref":["shape","ApprovalRef"],"authorized_action":["enum",["submit_candidate_once"]],"terms":["shape","OrderTerms"],"created_at":["instant"],"issued_at":["optional",["instant"]],"valid_from":["instant"],"expires_at":["instant"],"decision_evidence_ref":["optional",["shape","ApprovalRef"]],"consumed_intent_id":["optional",["identifier"]],"reason_code":["optional",["enum",["invalid_contract","unsupported_environment","authority_denied","session_inactive","session_expired","generation_mismatch","clock_invalid","nonce_unknown","replay_conflict","version_conflict","candidate_mismatch","presentation_mismatch","source_unresolved","rights_denied","policy_changed","expired","terminal_state","candidate_already_consumed","capacity_exceeded","commit_failed","reconciliation_required","risk_blocked"]]]},"ActionReceipt":{"command_id":["identifier"],"challenge_ref":["shape","ApprovalRef"],"command_payload_hash":["hash"],"action":["enum",["approve","deny","revoke","withdraw","present","admit","dispatch","query","stop","resume","heartbeat","disconnect","session","runtime","policy"]],"target_ref":["shape","ApprovalRef"],"actor_evidence_ref":["shape","ApprovalRef"],"recorded_at":["instant"],"outcome":["enum",["applied","rejected"]],"reason_code":["optional",["enum",["invalid_contract","unsupported_environment","authority_denied","session_inactive","session_expired","generation_mismatch","clock_invalid","nonce_unknown","replay_conflict","version_conflict","candidate_mismatch","presentation_mismatch","source_unresolved","rights_denied","policy_changed","expired","terminal_state","candidate_already_consumed","capacity_exceeded","commit_failed","reconciliation_required","risk_blocked"]]],"result_ref":["shape","ApprovalRef"],"aggregate_version":["positive_count"]},"SyntheticRuntimeEvidence":{"event_id":["identifier"],"aggregate_id":["identifier"],"aggregate_version":["positive_count"],"authority_generation":["identifier"],"environment":["enum",["synthetic"]],"account_ref":["identifier"],"kind":["identifier"],"target_id":["identifier"],"recorded_at":["instant"],"provenance":["enum",["synthetic_aggregate"]],"fixture_manifest_ref":["shape","ApprovalRef"]},"WithdrawalRequest":{"request_id":["identifier"],"principal_ref":["shape","ApprovalRef"],"session_id":["identifier"],"authority_generation":["identifier"],"approval_ref":["shape","ApprovalRef"],"intent_id":["identifier"],"requested_at":["instant"],"state":["enum",["requested","unsent_confirmed"]],"state_version":["positive_count"],"previous_ref":["optional",["shape","ApprovalRef"]],"runtime_evidence_ref":["shape","ApprovalRef"],"reason_code":["optional",["enum",["invalid_contract","unsupported_environment","authority_denied","session_inactive","session_expired","generation_mismatch","clock_invalid","nonce_unknown","replay_conflict","version_conflict","candidate_mismatch","presentation_mismatch","source_unresolved","rights_denied","policy_changed","expired","terminal_state","candidate_already_consumed","capacity_exceeded","commit_failed","reconciliation_required","risk_blocked"]]]}}'::jsonb; item record;
BEGIN
 IF NOT shapes ? schema_name THEN RAISE EXCEPTION 'execution_contract'; END IF;
 PERFORM qh.ledger_keys(j,ARRAY(SELECT jsonb_object_keys(shapes->schema_name)));
 FOR item IN SELECT * FROM jsonb_each(shapes->schema_name) LOOP
   PERFORM qh.execution_rule(item.value,j->item.key);
 END LOOP;
END $$;
CREATE FUNCTION qh.execution_rule(rule jsonb,v jsonb) RETURNS void
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,qh AS $$
DECLARE kind text:=rule->>0; item jsonb; n numeric; k integer;
BEGIN
 IF kind='optional' AND v='null'::jsonb THEN RETURN; END IF;
 IF v IS NULL OR v='null'::jsonb THEN RAISE EXCEPTION 'execution_contract'; END IF;
 CASE kind
 WHEN 'optional' THEN PERFORM qh.execution_rule(rule->1,v);
 WHEN 'sequence' THEN
   IF jsonb_typeof(v) IS DISTINCT FROM 'array' OR jsonb_array_length(v)>128 THEN RAISE EXCEPTION 'execution_contract'; END IF;
   FOR item IN SELECT value FROM jsonb_array_elements(v) LOOP PERFORM qh.execution_rule(rule->1,item); END LOOP;
 WHEN 'shape' THEN PERFORM qh.execution_shape(rule->>1,v);
 WHEN 'enum' THEN
   IF NOT coalesce(rule->1 @> jsonb_build_array(v),false) THEN RAISE EXCEPTION 'execution_contract'; END IF;
 WHEN 'identifier' THEN PERFORM qh.ledger_identifier(v);
 WHEN 'instant' THEN
   IF right(v#>>'{}',1) IS DISTINCT FROM 'Z' THEN RAISE EXCEPTION 'execution_contract'; END IF;
   PERFORM qh.ledger_instant(v);
 WHEN 'hash' THEN
   IF jsonb_typeof(v) IS DISTINCT FROM 'string' OR (v#>>'{}') !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'execution_contract'; END IF;
 WHEN 'boolean' THEN
   IF jsonb_typeof(v) IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'execution_contract'; END IF;
 WHEN 'string' THEN
   IF jsonb_typeof(v) IS DISTINCT FROM 'string' OR octet_length(v#>>'{}') NOT BETWEEN 1 AND (rule->>1)::integer THEN RAISE EXCEPTION 'execution_contract'; END IF;
 WHEN 'count' THEN PERFORM qh.ledger_int(v,0,2147483647);
 WHEN 'positive_count' THEN PERFORM qh.ledger_int(v,1,2147483647);
 WHEN 'version' THEN PERFORM qh.ledger_int(v,1,1);
 ELSE
   n:=qh.ledger_decimal(v)::numeric;
   IF (kind='nonnegative' AND n<0) OR (kind='positive' AND n<=0) OR (kind='ratio' AND (n<0 OR n>1))
    OR kind NOT IN ('numeric','nonnegative','positive','ratio','decimal_string') THEN RAISE EXCEPTION 'execution_contract'; END IF;
 END CASE;
END $$;
CREATE FUNCTION qh.execution_closed_row() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,qh AS $$
DECLARE j jsonb; schema_name text; prior qh.execution_evidence; fixed text[];
BEGIN
 IF TG_TABLE_NAME='execution_evidence' THEN
   PERFORM qh.ledger_keys(NEW.wire,ARRAY['schema_name','schema_version','environment','payload']);
   IF NEW.wire->>'environment' IS DISTINCT FROM 'synthetic' OR NEW.wire->'schema_version' IS DISTINCT FROM '1'::jsonb
    THEN RAISE EXCEPTION 'execution_contract'; END IF;
   schema_name:=NEW.wire->>'schema_name'; j:=NEW.wire->'payload';
 ELSIF TG_TABLE_NAME='execution_intent' THEN schema_name:='OrderIntent';j:=NEW.body;
 ELSIF TG_TABLE_NAME='execution_reservation' THEN schema_name:='ReservationSlice';j:=NEW.body;
 ELSIF TG_TABLE_NAME='execution_attempt' THEN schema_name:='DispatchAttempt';j:=NEW.body;
 ELSIF TG_TABLE_NAME='execution_broker_inbox' THEN schema_name:='SyntheticOrderEvent';j:=NEW.body;
 ELSE RAISE EXCEPTION 'execution_contract'; END IF;
 PERFORM qh.execution_shape(schema_name,j);
 IF TG_TABLE_NAME='execution_evidence' THEN
   IF NEW.version IS DISTINCT FROM coalesce((j->>'state_version')::integer,(j->>'version')::integer,(j->>'revision')::integer,1)
   THEN RAISE EXCEPTION 'execution_version'; END IF;
   IF NEW.kind IN ('approval','session','withdrawal') THEN
     IF NEW.version=1 THEN
       IF j->'previous_ref' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'execution_version'; END IF;
     ELSE
       SELECT * INTO prior FROM qh.execution_evidence e WHERE e.account_ref=NEW.account_ref AND e.kind=NEW.kind AND e.id=NEW.id AND e.version=NEW.version-1;
       IF prior.hash IS NULL OR j->'previous_ref'->>'sha256' IS DISTINCT FROM prior.hash THEN RAISE EXCEPTION 'execution_version'; END IF;
       IF NEW.kind='approval' THEN
         fixed:=ARRAY['state','state_version','previous_ref','issued_at','decision_evidence_ref','consumed_intent_id','reason_code'];
         IF (j-fixed) IS DISTINCT FROM ((prior.wire->'payload')-fixed) OR NOT (
           (prior.wire->'payload'->>'state'='pending' AND j->>'state' IN ('approved','denied','expired','invalidated')) OR
           (prior.wire->'payload'->>'state'='approved' AND j->>'state' IN ('revoked','expired','invalidated','consumed')))
          THEN RAISE EXCEPTION 'execution_transition'; END IF;
       ELSIF NEW.kind='session' THEN
         fixed:=ARRAY['state','state_version','previous_ref','last_control_event_ref','liveness_deadline'];
         IF (j-fixed) IS DISTINCT FROM ((prior.wire->'payload')-fixed) THEN RAISE EXCEPTION 'execution_contract'; END IF;
       END IF;
     END IF;
   END IF;
 ELSIF TG_TABLE_NAME='execution_attempt' THEN
   IF TG_OP='UPDATE' THEN
     IF (j-ARRAY['state','receipt_ref']) IS DISTINCT FROM (OLD.body-ARRAY['state','receipt_ref']) THEN RAISE EXCEPTION 'execution_contract'; END IF;
   END IF;
   IF j->>'attempt_id' IS DISTINCT FROM NEW.id OR j->>'intent_id' IS DISTINCT FROM NEW.intent_id OR j->>'action' IS DISTINCT FROM NEW.action
   THEN RAISE EXCEPTION 'execution_contract'; END IF;
 ELSIF TG_TABLE_NAME='execution_broker_inbox' THEN
   IF j->>'issuer_instance' IS DISTINCT FROM NEW.issuer OR j->>'event_id' IS DISTINCT FROM NEW.event_id OR
     (j->>'revision')::integer IS DISTINCT FROM NEW.revision OR qh.ledger_hash('SyntheticOrderEvent',j) IS DISTINCT FROM NEW.payload_hash
   THEN RAISE EXCEPTION 'execution_contract'; END IF;
 END IF;
 IF TG_TABLE_NAME='execution_reservation' THEN
   IF TG_OP='UPDATE' THEN
     IF (j-ARRAY['held','used','released','broker_reflected','settled','source_cutoff','ledger_refs']) IS DISTINCT FROM
        (OLD.body-ARRAY['held','used','released','broker_reflected','settled','source_cutoff','ledger_refs']) THEN RAISE EXCEPTION 'execution_contract'; END IF;
   END IF;
   IF j->>'reservation_id' IS DISTINCT FROM NEW.id OR j->>'intent_id' IS DISTINCT FROM NEW.intent_id THEN RAISE EXCEPTION 'execution_contract'; END IF;
 END IF;
 RETURN NEW;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['execution_evidence','execution_intent','execution_reservation','execution_attempt','execution_broker_inbox'] LOOP
 EXECUTE format('CREATE TRIGGER execution_closed_row BEFORE INSERT OR UPDATE ON qh.%I FOR EACH ROW EXECUTE FUNCTION qh.execution_closed_row()',t);
 END LOOP;
END $$;
-- Exact logical row and actual index-key bytes. No pg_column_size/disk estimate.
CREATE FUNCTION qh.execution_cursor_owner(a text,c integer) RETURNS text
LANGUAGE sql STABLE SET search_path=pg_catalog,qh AS $$
 SELECT min(b.body->>'intent_id') FROM qh.ledger_decision d
 JOIN qh.execution_broker_inbox b ON b.account_ref=d.account_ref
 AND d.submission->'evidence_refs' ? (b.body->>'journal_id')
 WHERE d.account_ref=a AND d.cursor=c AND d.submission->>'source_kind'='synthetic-execution'
$$;
CREATE FUNCTION qh.execution_owner(a text,t text,j jsonb) RETURNS text
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,qh AS $$
DECLARE owner_id text; c integer;
BEGIN
 owner_id:=coalesce(j->>'intent_id',j->'body'->>'intent_id',j->'wire'->'payload'->>'intent_id');
 IF t='execution_budget' THEN owner_id:=j->>'owner'; END IF;
 IF t='execution_evidence' AND owner_id IS NULL THEN
   SELECT intent_id INTO owner_id FROM qh.execution_intent
    WHERE account_ref=a AND approval_id=coalesce(j->'wire'->'payload'->>'approval_id',j->'wire'->'payload'->'target_ref'->>'id');
 END IF;
 IF t LIKE 'ledger_%' AND t NOT IN ('ledger_stream','ledger_workstate') THEN
   c:=coalesce((j->>'bundle_cursor')::integer,(j->>'cursor')::integer);
   IF t='ledger_journal' THEN SELECT bundle_cursor INTO c FROM qh.ledger_event WHERE account_ref=a AND event_id=j->>'event_id'; END IF;
   IF t IN ('ledger_delivery','ledger_inbox','ledger_inbox_collision') THEN
     SELECT cursor INTO c FROM qh.ledger_outbox WHERE account_ref=a AND message_id=j->>'message_id';
   END IF;
   owner_id:=qh.execution_cursor_owner(a,c);
 END IF;
 RETURN coalesce(owner_id,'@common');
END $$;
CREATE FUNCTION qh.execution_storage_rows(a text)
RETURNS TABLE(relation_name text,owner text,category text,row_data jsonb,index_bytes bigint)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE t text; idx record; expression text; predicate text; cost_expr text; filter_expr text; row_record record; owner_id text;
BEGIN
 FOREACH t IN ARRAY ARRAY['execution_account','execution_evidence','execution_head','execution_claim',
 'execution_intent','execution_reservation','execution_attempt','execution_outbox','execution_broker_inbox',
 'execution_event_resolution','execution_budget','execution_cursor','ledger_stream','ledger_event',
 'ledger_journal','ledger_decision','ledger_projection','ledger_outbox','ledger_delivery','ledger_inbox',
 'ledger_inbox_collision','ledger_workstate'] LOOP
   cost_expr:='0::bigint';
   FOR idx IN SELECT i.indexrelid,i.indnatts,i.indpred,i.indrelid FROM pg_index i
      WHERE i.indrelid=to_regclass('qh.'||t) ORDER BY i.indexrelid LOOP
     SELECT string_agg(pg_get_indexdef(idx.indexrelid,k,true),',' ORDER BY k) INTO expression
       FROM generate_series(1,idx.indnatts) k;
     predicate:=coalesce(pg_get_expr(idx.indpred,idx.indrelid),'true');
     cost_expr:=cost_expr||format('+CASE WHEN %s THEN octet_length(qh.ledger_canonical(jsonb_build_array(%s))) ELSE 0 END',predicate,expression);
   END LOOP;
   filter_expr:=CASE WHEN t IN ('ledger_delivery','ledger_inbox','ledger_inbox_collision')
     THEN 'message_id IN (SELECT message_id FROM qh.ledger_outbox WHERE account_ref=$1)'
     ELSE 'account_ref=$1' END;
   FOR row_record IN EXECUTE format('SELECT to_jsonb(t) j,%s b FROM qh.%I t WHERE %s',cost_expr,t,filter_expr) USING a LOOP
     owner_id:=qh.execution_owner(a,t,row_record.j);
     relation_name:=t; owner:=owner_id;
     category:=CASE WHEN owner_id='@common' THEN 'common' WHEN t LIKE 'ledger_%' THEN 'ledger'
       WHEN t IN ('execution_broker_inbox','execution_event_resolution') THEN 'broker'
       WHEN t='execution_evidence' AND row_record.j->'wire'->>'schema_name' IN ('SyntheticOrderEvent','SyntheticBrokerReceipt') THEN 'broker'
       WHEN t='execution_evidence' AND row_record.j->>'kind' IN ('cancel','withdrawal','challenge','receipt') THEN 'control'
       ELSE 'base' END;
     row_data:=row_record.j; index_bytes:=row_record.b;
     IF t='execution_evidence' AND index_bytes>4096 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     IF t='execution_evidence' AND row_data->'wire'->>'schema_name' IN
       ('PrincipalEvidence','SessionRecord','SyntheticRuntimeEvidence','ActionChallenge','ActionReceipt','WithdrawalRequest','ExecutionReconciliation')
       AND octet_length(qh.ledger_canonical(row_data))>8192 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     -- Enforced bounds used by manifest_ledger_cost, including all real indexes.
     IF t IN ('ledger_event','ledger_projection') AND octet_length(qh.ledger_canonical(row_data->'body'))>65536 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     IF t='ledger_decision' AND octet_length(qh.ledger_canonical(row_data->'submission'))>65536 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     IF t IN ('ledger_event','ledger_decision','ledger_projection') AND
        octet_length(qh.ledger_canonical(row_data))>67584 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     IF t IN ('ledger_journal','ledger_outbox','ledger_delivery','ledger_inbox') AND
        octet_length(qh.ledger_canonical(row_data))>1024 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     -- Each index entry is separately bounded (not the sum).
     FOR idx IN SELECT i.indexrelid,i.indnatts,i.indpred,i.indrelid FROM pg_index i
       WHERE i.indrelid=to_regclass('qh.'||t) AND t LIKE 'ledger_%' LOOP
       SELECT jsonb_agg(row_data->att.attname ORDER BY k.ord) INTO row_record.j
         FROM pg_index i CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,ord)
         JOIN pg_attribute att ON att.attrelid=i.indrelid AND att.attnum=k.attnum
         WHERE i.indexrelid=idx.indexrelid;
       IF octet_length(qh.ledger_canonical(row_record.j))>512 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     END LOOP;
     RETURN NEXT;
   END LOOP;
 END LOOP;
END $$;
ALTER TABLE qh.execution_budget ADD remaining jsonb NOT NULL DEFAULT '{}';
ALTER TABLE qh.execution_budget ADD closed boolean NOT NULL DEFAULT false;
-- Category caps are fixed; row/index measurement consumes only its owner's reserve.
-- Trusted host stages exactly one fixed operation. Product cannot stage/issue.
CREATE TABLE qh.execution_stage (
 backend integer NOT NULL, transaction_id xid8 NOT NULL, token text NOT NULL,
 part integer NOT NULL CHECK(part>=0), payload bytea NOT NULL CHECK(octet_length(payload)<=65536),
 PRIMARY KEY(backend,transaction_id,token,part)
);
CREATE TABLE qh.execution_context (
 backend integer NOT NULL, transaction_id xid8 NOT NULL, token text NOT NULL,
 account_ref text NOT NULL, action text NOT NULL,
 header jsonb NOT NULL, payload jsonb NOT NULL,
 PRIMARY KEY(backend,transaction_id,token)
);
CREATE FUNCTION qh.execution_stage_chunk(token text,part integer,raw text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE n integer;
BEGIN
 IF token IS NULL OR part IS NULL OR raw IS NULL OR length(raw)>131072 OR raw !~ '^[0-9a-f]*$' OR length(raw)%2<>0
 THEN RAISE EXCEPTION 'execution_frame'; END IF;
 SELECT count(*) INTO n FROM qh.execution_stage WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND execution_stage.token=execution_stage_chunk.token;
 IF part<>n OR part>=1024 THEN RAISE EXCEPTION 'execution_frame'; END IF;
 INSERT INTO qh.execution_stage VALUES(pg_backend_pid(),pg_current_xact_id(),token,part,decode(raw,'hex'));
 RETURN to_jsonb(n+1);
END $$;
CREATE FUNCTION qh.execution_issue_context(a text,action text,token text,parts integer,raw_header text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE h jsonb; p jsonb; raw bytea; n integer;
BEGIN
 IF a IS NULL OR action IS NULL OR token IS NULL OR parts IS NULL OR raw_header IS NULL OR octet_length(raw_header)>4096
 OR action NOT IN ('save','event','append','consume') THEN RAISE EXCEPTION 'execution_auth'; END IF;
 h:=qh.execution_wire(raw_header);
 PERFORM qh.ledger_keys(h,ARRAY['version','generation','fence','source_hash','actor','session','action','nonce','target','target_version','at','issuer','fact','operation','command','current_validation']);
 IF h->>'operation' IS DISTINCT FROM action THEN RAISE EXCEPTION 'execution_auth'; END IF;
 PERFORM qh.execution_lock(a);
 IF h->>'at' IS NULL THEN RAISE EXCEPTION 'execution_auth'; END IF;
 PERFORM qh.ledger_instant(h->'at');
 SELECT count(*),string_agg(payload,''::bytea ORDER BY part) INTO n,raw FROM qh.execution_stage
  WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND execution_stage.token=execution_issue_context.token;
 IF n IS DISTINCT FROM parts OR n=0 OR octet_length(raw)>67108864 THEN RAISE EXCEPTION 'execution_frame'; END IF;
 p:=qh.execution_wire(convert_from(raw,'UTF8')); -- duplicate keys rejected before jsonb
 INSERT INTO qh.execution_context VALUES(pg_backend_pid(),pg_current_xact_id(),token,a,action,h,p);
 DELETE FROM qh.execution_stage WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND execution_stage.token=execution_issue_context.token;
 RETURN 'true'::jsonb;
END $$;
-- Financial payload comes from stored terms and the exact trusted broker fact.
CREATE FUNCTION qh.execution_derive_append(i qh.execution_intent,e jsonb,kind text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,qh AS $$
DECLARE terms jsonb:=i.body->'terms'; key text; previous qh.ledger_event; trade qh.ledger_event;
 qty numeric; amount numeric; currency text:=terms->>'currency'; legs jsonb; positions jsonb:='[]';
 dependencies jsonb:='[]'; prev_fact jsonb; stream text; buying boolean:=terms->>'side'='buy'; account_name text;
BEGIN
 PERFORM qh.execution_shape('SyntheticOrderEvent',e);
 IF e->>'account_ref' IS DISTINCT FROM i.account_ref OR e->>'intent_id' IS DISTINCT FROM i.intent_id OR
    e->>'request_hash' IS DISTINCT FROM i.body->>'request_hash' OR
    NOT coalesce(kind IN ('trade','fee','tax','settlement'),false) OR
    e->>'kind' IS DISTINCT FROM (CASE WHEN kind='settlement' THEN 'settlement' ELSE 'fill' END)
 THEN RAISE EXCEPTION 'execution_auth'; END IF;
 qty:=(e->>'quantity')::numeric;
 IF e->>'semantics'='cumulative' AND (e->>'stream_sequence')::integer>1 THEN
   SELECT b.body INTO prev_fact FROM qh.execution_broker_inbox b
    WHERE b.account_ref=i.account_ref AND b.body->>'intent_id'=i.intent_id AND b.body->>'execution_id'=e->>'execution_id'
     AND b.body->>'kind'='fill' AND (b.body->>'stream_sequence')::integer=(e->>'stream_sequence')::integer-1
     AND EXISTS(SELECT 1 FROM qh.execution_event_resolution r WHERE r.account_ref=b.account_ref AND r.issuer=b.issuer
       AND r.event_id=b.event_id AND r.revision=b.revision AND r.payload_hash=b.payload_hash AND r.disposition='applied')
    ORDER BY b.revision DESC LIMIT 1;
   IF prev_fact IS NULL THEN RAISE EXCEPTION 'execution_auth'; END IF;
   IF kind<>'settlement' THEN qty:=qty-(prev_fact->>'quantity')::numeric; END IF;
 END IF;
 IF qty<=0 OR qty>(terms->>'quantity')::numeric THEN RAISE EXCEPTION 'execution_contract'; END IF;
 stream:=CASE WHEN e->>'semantics'='cumulative' THEN e->>'stream_sequence' ELSE '0' END;
 IF kind='trade' THEN
   key:='execution:'||encode(sha256(convert_to(i.intent_id||':'||(e->>'execution_id')||CASE WHEN stream='0' THEN '' ELSE ':'||stream END,'UTF8')),'hex');
 ELSIF kind='settlement' THEN
   key:='settlement:'||encode(sha256(convert_to(i.intent_id||(e->>'execution_id')||stream,'UTF8')),'hex');
 ELSE
   key:='execution-cost:'||encode(sha256(convert_to(i.intent_id||(e->>'execution_id')||':'||stream||':'||kind,'UTF8')),'hex');
 END IF;
 SELECT * INTO previous FROM qh.ledger_event WHERE account_ref=i.account_ref AND source_kind='synthetic-execution'
  AND source_event_key=key AND ledger_event.kind='replacement' ORDER BY source_revision DESC LIMIT 1;
 IF kind IN ('fee','tax') THEN amount:=(e->>kind)::numeric-coalesce((prev_fact->>kind)::numeric,0);
 ELSE amount:=qty*(e->>'price')::numeric; END IF;
 IF amount<=0 THEN RAISE EXCEPTION 'execution_contract'; END IF;
 IF kind='trade' THEN
   account_name:=CASE WHEN buying THEN 'unsettled_payable' ELSE 'unsettled_receivable' END;
   amount:=amount*CASE WHEN buying THEN -1 ELSE 1 END;
   legs:=jsonb_build_array(jsonb_build_object('account',account_name,'currency',currency,'amount',trim_scale(amount)::text,'basis','trade'),
    jsonb_build_object('account','trade_clearing','currency',currency,'amount',trim_scale(-amount)::text,'basis','trade'));
   positions:=jsonb_build_array(terms->'position'||jsonb_build_object('amount',trim_scale(qty*CASE WHEN buying THEN 1 ELSE -1 END)::text));
 ELSE
   SELECT * INTO trade FROM qh.ledger_event WHERE account_ref=i.account_ref AND source_kind='synthetic-execution'
    AND source_event_key='execution:'||encode(sha256(convert_to(i.intent_id||':'||(e->>'execution_id')||CASE WHEN stream='0' THEN '' ELSE ':'||stream END,'UTF8')),'hex')
    AND ledger_event.kind='replacement' ORDER BY source_revision DESC LIMIT 1;
   IF trade.event_id IS NULL THEN RAISE EXCEPTION 'execution_auth'; END IF;
   dependencies:=jsonb_build_array(trade.event_id);
   IF kind='settlement' THEN
     account_name:=CASE WHEN buying THEN 'unsettled_payable' ELSE 'unsettled_receivable' END;
     amount:=amount*CASE WHEN buying THEN -1 ELSE 1 END;
     legs:=jsonb_build_array(jsonb_build_object('account','settled_cash','currency',currency,'amount',trim_scale(amount)::text,'basis','settlement'),
      jsonb_build_object('account',account_name,'currency',currency,'amount',trim_scale(-amount)::text,'basis','settlement'));
   ELSE
     legs:=jsonb_build_array(jsonb_build_object('account','settled_cash','currency',currency,'amount',trim_scale(-amount)::text,'basis','settlement'),
      jsonb_build_object('account',kind||'_expense','currency',currency,'amount',trim_scale(amount)::text,'basis','settlement'));
   END IF;
 END IF;
 RETURN jsonb_build_object('schema_version',1,'environment','synthetic','account_ref',i.account_ref,
  'source_kind','synthetic-execution','source_event_key',key,'source_revision',coalesce(previous.source_revision,0)+1,
  'predecessor_revision',previous.source_revision,'mapping_version',terms->'position'->>'mapping_version',
  'event_type',kind,'effective_at',e->>'effective_at','revision_mode',CASE WHEN previous.event_id IS NULL THEN 'original' ELSE 'retroactive' END,
  'correction_of',previous.event_id,'cash_legs',legs,'position_deltas',positions,'evidence_refs',jsonb_build_array(e->>'journal_id'),
  'completeness',jsonb_build_object('complete',true,'costs_known',true,'semantics_known',true),'baseline',NULL,
  'dependency_refs',dependencies,'split_ratio',NULL);
END $$;
CREATE FUNCTION qh.execution_map_get(packed jsonb,k jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,qh AS $$
 SELECT value->1 FROM jsonb_array_elements(packed->'map') WHERE value->0=k
$$;
-- Both ordinary persisted commands and the one atomic protective closure are
-- checked against the current DB session/target and the exact staged delta.
CREATE FUNCTION qh.execution_check_command(c qh.execution_context, old qh.execution_account, session_body jsonb) RETURNS void
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,qh AS $$
DECLARE command_body jsonb:=c.header->'command'; receipt_body jsonb; challenge_ref jsonb;
 receipt_ref jsonb; target_body jsonb; result_body jsonb; patched jsonb; fresh boolean; n integer;
BEGIN
 PERFORM qh.execution_shape('ActionChallenge',command_body);
 challenge_ref:=jsonb_build_object('kind','challenge','id',command_body->>'challenge_id','version',1,
  'canonicalization_version','qh-canonical-json-v1','sha256',qh.ledger_hash('ActionChallenge',command_body));
 IF c.action IS DISTINCT FROM 'save' OR c.header->>'actor' IS NULL OR session_body IS NULL OR
    command_body->>'nonce' IS DISTINCT FROM c.header->>'nonce' OR
    command_body->>'action' IS DISTINCT FROM c.header->>'action' OR
    command_body->>'session_id' IS DISTINCT FROM c.header->>'session' OR
    command_body->'principal_ref' IS DISTINCT FROM session_body->'principal_ref' OR
    command_body->>'account_ref' IS DISTINCT FROM c.account_ref OR
    command_body->'target_ref'->>'kind' IS DISTINCT FROM 'approval' OR
    command_body->'target_ref'->'version' IS DISTINCT FROM command_body->'expected_state_version' OR
    command_body->>'authority_generation' IS DISTINCT FROM old.generation OR
    (c.header->>'at')::timestamptz<(command_body->>'issued_at')::timestamptz
 THEN RAISE EXCEPTION 'execution_auth'; END IF;
 IF EXISTS(SELECT 1 FROM qh.execution_evidence e WHERE e.account_ref=c.account_ref AND e.kind='receipt'
   AND e.wire->'payload'->>'command_id'=command_body->>'command_id')
 THEN RAISE EXCEPTION 'execution_auth'; END IF;
 SELECT NOT EXISTS(SELECT 1 FROM qh.execution_evidence e WHERE e.account_ref=c.account_ref
   AND e.kind='challenge' AND e.wire->'payload'=command_body) INTO fresh;
 IF fresh THEN
   -- Only withdraw creates AND closes a challenge under one host gate/TX.
   IF command_body->>'action' IS DISTINCT FROM 'withdraw' OR
      (c.header->>'at')::timestamptz>=(command_body->>'expires_at')::timestamptz OR
      EXISTS(SELECT 1 FROM qh.execution_evidence e WHERE e.account_ref=c.account_ref AND e.kind='challenge'
       AND (e.id=command_body->>'challenge_id' OR e.wire->'payload'->>'nonce'=command_body->>'nonce'
        OR e.wire->'payload'->>'command_id'=command_body->>'command_id'))
   THEN RAISE EXCEPTION 'execution_auth'; END IF;
   SELECT count(*) INTO n FROM jsonb_array_elements(c.payload->'evidence') x
    WHERE x->'ref'=challenge_ref AND x->'wire'->>'schema_name'='ActionChallenge' AND x->'wire'->'payload'=command_body;
   IF n<>1 THEN RAISE EXCEPTION 'execution_auth'; END IF;
 END IF;
 SELECT count(*) INTO n FROM jsonb_array_elements(c.payload->'evidence') x
  WHERE x->'wire'->>'schema_name'='ActionReceipt' AND x->'wire'->'payload'->>'command_id'=command_body->>'command_id';
 IF n<>1 THEN RAISE EXCEPTION 'execution_auth'; END IF;
 SELECT x->'wire'->'payload',x->'ref' INTO receipt_body,receipt_ref FROM jsonb_array_elements(c.payload->'evidence') x
  WHERE x->'wire'->>'schema_name'='ActionReceipt' AND x->'wire'->'payload'->>'command_id'=command_body->>'command_id';
 PERFORM qh.execution_shape('ActionReceipt',receipt_body);
 IF receipt_body->>'action' IS DISTINCT FROM command_body->>'action' OR
    receipt_body->'challenge_ref' IS DISTINCT FROM challenge_ref OR
    receipt_body->>'command_payload_hash' IS DISTINCT FROM encode(sha256(convert_to(qh.ledger_canonical(
      jsonb_build_object('schema_name','ActionChallenge','schema_version',1,'environment','synthetic','payload',command_body)),
      'UTF8')),'hex') OR
    receipt_body->'target_ref' IS DISTINCT FROM command_body->'target_ref' OR
    receipt_body->'actor_evidence_ref' IS DISTINCT FROM command_body->'principal_ref' OR
    receipt_ref IS DISTINCT FROM jsonb_build_object('kind','receipt','id',command_body->>'command_id','version',1,
      'canonicalization_version','qh-canonical-json-v1','sha256',qh.ledger_hash('ActionReceipt',receipt_body)) OR
    (fresh AND receipt_body->>'outcome' IS DISTINCT FROM 'applied')
 THEN RAISE EXCEPTION 'execution_auth'; END IF;
 patched:=qh.execution_patch(old.state,c.payload->'state_delta');
 -- Exact immutable evidence above is the authority, never lookup existence.
 -- If indexes are retained, all three must agree; partial removal is forbidden.
 IF NOT ((qh.execution_map_get(qh.execution_map_get(patched,'"commands"'),command_body->'command_id')->'wire'->'payload'=challenge_ref AND
    qh.execution_map_get(qh.execution_map_get(patched,'"nonces"'),command_body->'nonce')->'wire'->'payload'=challenge_ref AND
    qh.execution_map_get(qh.execution_map_get(patched,'"receipts"'),command_body->'command_id')->'wire'->'payload'=receipt_ref) IS TRUE OR
   (qh.execution_map_get(qh.execution_map_get(patched,'"commands"'),command_body->'command_id') IS NULL AND
    qh.execution_map_get(qh.execution_map_get(patched,'"nonces"'),command_body->'nonce') IS NULL AND
    qh.execution_map_get(qh.execution_map_get(patched,'"receipts"'),command_body->'command_id') IS NULL))
 THEN RAISE EXCEPTION 'execution_auth'; END IF;
 IF receipt_body->>'outcome'='applied' THEN
   SELECT e.wire->'payload' INTO target_body FROM qh.execution_head h JOIN qh.execution_evidence e USING(account_ref,kind,id,version,hash)
    WHERE h.account_ref=c.account_ref AND h.kind='approval' AND h.id=command_body->'target_ref'->>'id'
     AND h.version=(command_body->>'expected_state_version')::integer AND h.hash=command_body->'target_ref'->>'sha256';
   IF target_body IS NULL OR target_body->'presentation_ref' IS DISTINCT FROM command_body->'presentation_ref' OR
      (c.header->>'at')::timestamptz>=(command_body->>'expires_at')::timestamptz
   THEN RAISE EXCEPTION 'execution_auth'; END IF;
   IF command_body->>'action'='withdraw' THEN
     SELECT x->'wire'->'payload' INTO result_body FROM jsonb_array_elements(c.payload->'evidence') x
      WHERE x->'ref'=receipt_body->'result_ref';
     IF result_body IS NULL THEN RAISE EXCEPTION 'execution_auth'; END IF;
     IF target_body->>'state'='approved' THEN
       IF receipt_body->'result_ref'->>'kind' IS DISTINCT FROM 'approval' OR result_body->>'state' IS DISTINCT FROM 'revoked'
        OR result_body->'previous_ref' IS DISTINCT FROM command_body->'target_ref' THEN RAISE EXCEPTION 'execution_auth'; END IF;
     ELSIF target_body->>'state'='consumed' THEN
       IF receipt_body->'result_ref'->>'kind' IS DISTINCT FROM 'withdrawal' OR
        result_body->'approval_ref' IS DISTINCT FROM command_body->'target_ref' OR
        result_body->'principal_ref' IS DISTINCT FROM command_body->'principal_ref' OR
        result_body->>'session_id' IS DISTINCT FROM command_body->>'session_id' OR
        result_body->>'authority_generation' IS DISTINCT FROM old.generation OR
        result_body->>'intent_id' IS DISTINCT FROM target_body->>'consumed_intent_id'
       THEN RAISE EXCEPTION 'execution_auth'; END IF;
     ELSE RAISE EXCEPTION 'execution_auth'; END IF;
   END IF;
 END IF;
END $$;
CREATE FUNCTION qh.execution_apply(token text,action text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE c qh.execution_context; old qh.execution_account; result jsonb; i qh.execution_intent; e jsonb; session_body jsonb; principal_body jsonb; allowed jsonb; command_body jsonb; current_target jsonb; receipt_body jsonb; staged jsonb; rec jsonb; validity jsonb; previous_archive jsonb; new_archive jsonb;
BEGIN
 DELETE FROM qh.execution_context WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id()
  AND execution_context.token=execution_apply.token AND execution_context.action=execution_apply.action RETURNING * INTO c;
 IF NOT FOUND THEN RAISE EXCEPTION 'execution_auth'; END IF;
 PERFORM qh.execution_lock(c.account_ref);
 SELECT * INTO old FROM qh.execution_account WHERE account_ref=c.account_ref;
 IF coalesce(old.version,-1) IS DISTINCT FROM (c.header->>'version')::integer OR
 (old.account_ref IS NOT NULL AND (old.generation IS DISTINCT FROM c.header->>'generation' OR
  old.fence IS DISTINCT FROM (c.header->>'fence')::integer OR old.source_hash IS DISTINCT FROM c.header->>'source_hash'))
 THEN RAISE EXCEPTION 'execution_auth'; END IF;
 IF c.header->>'actor' IS NOT NULL THEN
   SELECT e.wire->'payload' INTO session_body FROM qh.execution_head h JOIN qh.execution_evidence e USING(account_ref,kind,id,version,hash)
    WHERE h.account_ref=c.account_ref AND h.kind='session' AND h.id=c.header->>'session';
   SELECT e.wire->'payload' INTO principal_body FROM qh.execution_evidence e WHERE e.account_ref=c.account_ref AND e.kind='principal'
    AND e.id=session_body->'principal_ref'->>'id' AND e.wire->'payload'->>'principal_id'=c.header->>'actor'
    AND e.hash=session_body->'principal_ref'->>'sha256';
   allowed:=qh.execution_map_get(qh.execution_map_get(old.state,'"permissions"'::jsonb),to_jsonb(c.header->>'actor'))->'tuple';
   IF session_body IS NULL OR principal_body IS NULL OR session_body->>'state' IS DISTINCT FROM 'running'
    OR session_body->>'authority_generation' IS DISTINCT FROM old.generation
    OR principal_body->>'authority_generation' IS DISTINCT FROM old.generation
    OR principal_body->>'account_ref' IS DISTINCT FROM c.account_ref
    OR (c.header->'command' IS DISTINCT FROM 'null'::jsonb AND principal_body->>'issuer_instance_id' IS DISTINCT FROM c.header->>'issuer')
    OR (c.header->>'at')::timestamptz>=(principal_body->>'expires_at')::timestamptz
    OR NOT coalesce(principal_body->'allowed_actions' ? (c.header->>'action'),false)
    OR NOT coalesce(allowed ? (c.header->>'action'),false)
    OR (c.header->>'at')::timestamptz>=(session_body->>'expires_at')::timestamptz
    OR (c.header->>'at')::timestamptz>=(session_body->>'liveness_deadline')::timestamptz
   THEN RAISE EXCEPTION 'execution_auth'; END IF;
 END IF;
 IF c.header->'command' IS DISTINCT FROM 'null'::jsonb THEN
   PERFORM qh.execution_check_command(c,old,session_body);
 END IF;
 IF c.header->>'target' IS NOT NULL THEN
   SELECT * INTO i FROM qh.execution_intent WHERE account_ref=c.account_ref AND intent_id=c.header->>'target';
   IF NOT FOUND OR i.version IS DISTINCT FROM (c.header->>'target_version')::integer THEN RAISE EXCEPTION 'execution_auth'; END IF;
 END IF;
 IF action='save' THEN
   staged:=qh.execution_patch(old.state,c.payload->'state_delta');
   previous_archive:=qh.execution_map_get(old.state,'"source_archive"')->'tuple';
   new_archive:=qh.execution_map_get(staged,'"source_archive"')->'tuple';
   IF previous_archive IS NOT NULL AND (new_archive IS NULL OR jsonb_array_length(new_archive)<jsonb_array_length(previous_archive)
     OR EXISTS(SELECT 1 FROM jsonb_array_elements(previous_archive) WITH ORDINALITY x(value,n)
       WHERE new_archive->((x.n-1)::integer) IS DISTINCT FROM x.value))
   THEN RAISE EXCEPTION 'execution_atomicity'; END IF;
   IF old.account_ref IS NOT NULL AND EXISTS(SELECT 1 FROM unnest(ARRAY['current_policy_ref','target_policy_ref','pending_target_policy_ref']) AS policy_key(value)
     WHERE qh.execution_map_get(old.state,to_jsonb(policy_key.value)) IS DISTINCT FROM qh.execution_map_get(staged,to_jsonb(policy_key.value)))
      AND c.header->>'action' IS DISTINCT FROM 'policy'
   THEN RAISE EXCEPTION 'execution_auth'; END IF;
   validity:=c.header->'current_validation';
   IF validity IS DISTINCT FROM 'null'::jsonb THEN
     PERFORM qh.ledger_keys(validity,ARRAY['source_hash','current_identity','validator_version','valid_from','valid_to','query_ref','ledger_cursor','generation','fence']);
     IF validity->>'source_hash' IS DISTINCT FROM c.payload->>'source_hash'
       OR validity->>'validator_version' IS DISTINCT FROM 'q27-account-current-v1'
       OR validity->>'current_identity' IS DISTINCT FROM encode(sha256(convert_to((c.payload->>'source_hash')||':q27-account-current-v1','UTF8')),'hex')
       OR validity->'generation' IS DISTINCT FROM c.payload->'generation'
       OR validity->'fence' IS DISTINCT FROM c.payload->'fence'
       OR (validity->>'ledger_cursor')::integer IS DISTINCT FROM (SELECT cursor FROM qh.ledger_stream WHERE account_ref=c.account_ref)
       OR NOT coalesce((validity->>'valid_from')::timestamptz<=(c.header->>'at')::timestamptz
         AND (c.header->>'at')::timestamptz<(validity->>'valid_to')::timestamptz,false)
     THEN RAISE EXCEPTION 'execution_auth'; END IF;
   END IF;
   rec:=qh.execution_map_get(staged,'"reconciliation"')->'wire'->'payload';
   IF old.mode IS DISTINCT FROM 'running' AND c.payload->>'mode'='running' THEN
     IF c.header->>'action' IS DISTINCT FROM 'resume' OR rec->>'result' IS DISTINCT FROM 'matched'
       OR validity IS NULL OR validity='null'::jsonb
       OR (rec->>'source_hash',rec->>'current_identity',rec->>'validator_version',rec->>'valid_from',rec->>'valid_to') IS DISTINCT FROM
       (validity->>'source_hash',validity->>'current_identity',validity->>'validator_version',validity->>'valid_from',validity->>'valid_to')
       OR rec->'query_ref' IS DISTINCT FROM validity->'query_ref'
       OR rec->'ledger_cursor' IS DISTINCT FROM validity->'ledger_cursor'
       OR rec->>'session_id' IS DISTINCT FROM c.header->>'session'
       OR rec->'account_version' IS DISTINCT FROM qh.execution_map_get(old.state,'"version"')
       OR rec->>'generation' IS DISTINCT FROM old.generation OR rec->'fence' IS DISTINCT FROM to_jsonb(old.fence)
     THEN RAISE EXCEPTION 'execution_auth'; END IF;
   END IF;
   IF rec->>'result'='matched' AND rec IS DISTINCT FROM qh.execution_map_get(old.state,'"reconciliation"')->'wire'->'payload' THEN
     IF validity IS NULL OR validity='null'::jsonb OR
       (rec->>'source_hash',rec->>'current_identity',rec->>'validator_version',rec->>'valid_from',rec->>'valid_to') IS DISTINCT FROM
       (validity->>'source_hash',validity->>'current_identity',validity->>'validator_version',validity->>'valid_from',validity->>'valid_to')
       OR rec->'query_ref' IS DISTINCT FROM validity->'query_ref'
       OR rec->'ledger_cursor' IS DISTINCT FROM validity->'ledger_cursor'
       OR rec->'generation' IS DISTINCT FROM validity->'generation'
       OR rec->'fence' IS DISTINCT FROM validity->'fence'
       OR rec->>'generation' IS DISTINCT FROM c.payload->>'generation'
       OR rec->'fence' IS DISTINCT FROM c.payload->'fence'
       OR rec->>'session_id' IS DISTINCT FROM c.header->>'session'
       OR rec->'account_version' IS DISTINCT FROM qh.execution_map_get(staged,'"version"')
     THEN RAISE EXCEPTION 'execution_auth'; END IF;
   END IF;
   IF old.generation=c.payload->>'generation' AND EXISTS(
     SELECT 1 FROM jsonb_array_elements(qh.execution_map_get(old.state,'"commands"')->'map') pair
      WHERE qh.execution_map_get(qh.execution_map_get(qh.execution_patch(old.state,c.payload->'state_delta'),'"commands"'),pair->0) IS NULL)
    AND (principal_body->>'role' IS DISTINCT FROM 'controller' OR c.header->>'action' IS DISTINCT FROM 'query'
      OR c.header->'command' IS DISTINCT FROM 'null'::jsonb)
   THEN RAISE EXCEPTION 'execution_auth'; END IF;
   result:=qh.execution_save(c.account_ref,c.payload::text,c.header->>'version');
 ELSIF action='event' THEN
   IF c.header->'fact' IS DISTINCT FROM c.payload->'body' OR
      c.payload->'body'->>'issuer_instance' IS DISTINCT FROM c.header->>'issuer'
   THEN RAISE EXCEPTION 'execution_auth'; END IF;
   result:=qh.execution_event(c.account_ref,c.payload::text);
 ELSIF action='append' THEN
   e:=c.header->'fact';
   IF i.intent_id IS NULL OR e->>'intent_id' IS DISTINCT FROM i.intent_id OR
      e->>'request_hash' IS DISTINCT FROM i.body->>'request_hash' OR
      e->>'issuer_instance' IS DISTINCT FROM c.header->>'issuer' OR
      c.payload->'evidence_refs' IS DISTINCT FROM jsonb_build_array(e->>'journal_id') OR
      c.payload->>'mapping_version' IS DISTINCT FROM i.body->'terms'->'position'->>'mapping_version' OR
      c.payload->>'event_type' NOT IN ('trade','fee','tax','settlement')
   THEN RAISE EXCEPTION 'execution_auth'; END IF;
   e:=qh.execution_derive_append(i,e,c.payload->>'event_type');
   IF qh.ledger_submission(e) IS DISTINCT FROM qh.ledger_submission(c.payload) THEN RAISE EXCEPTION 'execution_contract'; END IF;
   result:=qh.execution_ledger(c.account_ref,'append',e::text,c.header->>'at');
 ELSIF action='consume' THEN
   result:=qh.execution_consume(c.account_ref,c.payload->>'message_id',c.payload->>'payload_hash');
 ELSE RAISE EXCEPTION 'execution_auth'; END IF;
 RETURN result;
END $$;
-- Read responses are byte pages, including UTF8 codepoint splits encoded as hex.
CREATE TABLE qh.execution_read_buffer (
 backend integer NOT NULL, transaction_id xid8 NOT NULL, request_key text NOT NULL,
 next_page integer NOT NULL, raw bytea NOT NULL CHECK(octet_length(raw)<=67108864),
 PRIMARY KEY(backend,transaction_id)
);
CREATE FUNCTION qh.execution_read_page(a text,operation text,payload text,at_text text,page integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE raw bytea; j jsonb; key text; pending qh.execution_read_buffer; total integer; chunk bytea;
BEGIN
 IF page IS NULL OR page<0 OR page>=1024 OR a IS NULL OR operation IS NULL OR payload IS NULL OR at_text IS NULL
 THEN RAISE EXCEPTION 'execution_frame'; END IF;
 key:=encode(sha256(convert_to(jsonb_build_array(a,operation,payload,at_text)::text,'UTF8')),'hex');
 IF page=0 THEN
   IF operation='load' THEN j:=qh.execution_load(a);
   ELSIF operation IN ('events','replay') THEN j:=qh.execution_ledger(a,operation,payload,at_text);
   ELSIF operation='fingerprint' THEN j:=qh.execution_fingerprint(a);
   ELSE RAISE EXCEPTION 'execution_contract'; END IF;
   raw:=convert_to(j::text,'UTF8');
   IF octet_length(raw)>67108864 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
   INSERT INTO qh.execution_read_buffer VALUES(pg_backend_pid(),pg_current_xact_id(),key,0,raw);
 END IF;
 SELECT * INTO pending FROM qh.execution_read_buffer WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id();
 IF pending.request_key IS DISTINCT FROM key OR pending.next_page IS DISTINCT FROM page THEN RAISE EXCEPTION 'execution_frame'; END IF;
 total:=octet_length(pending.raw);chunk:=substring(pending.raw FROM page*65536+1 FOR 65536);
 IF (page+1)*65536>=total THEN DELETE FROM qh.execution_read_buffer WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id();
 ELSE UPDATE qh.execution_read_buffer SET next_page=page+1 WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id(); END IF;
 RETURN jsonb_build_object('page',page,'total',total,'hex',encode(chunk,'hex'));
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA qh FROM qh_execution_product;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qh FROM PUBLIC;
GRANT EXECUTE ON FUNCTION qh.execution_lock(text),qh.execution_read_page(text,text,text,text,integer),
 qh.execution_apply(text,text) TO qh_execution_product;

-- Deferred constraints also cover owner/admin DML. AUTH tests are separate.
-- Deferred owner/admin DML checks. Pending obligations survive missing indexes.
CREATE FUNCTION qh.execution_check_lookups(a text) RETURNS void
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,qh AS $$
DECLARE ac qh.execution_account; c record; r qh.execution_evidence; cr jsonb; rr jsonb;
 cm jsonb; nm jsonb; rm jsonb; pair jsonb; map_name text;
BEGIN
 SELECT * INTO ac FROM qh.execution_account WHERE account_ref=a;
 FOR c IN SELECT * FROM qh.execution_evidence WHERE account_ref=a AND kind='challenge'
  AND wire->'payload'->>'authority_generation'=ac.generation LOOP
   cr:=jsonb_build_object('kind','challenge','id',c.id,'version',c.version,'canonicalization_version','qh-canonical-json-v1','sha256',c.hash);
   SELECT * INTO r FROM qh.execution_evidence WHERE account_ref=a AND kind='receipt'
    AND wire->'payload'->>'command_id'=c.wire->'payload'->>'command_id';
   rr:=CASE WHEN r.id IS NULL THEN NULL ELSE jsonb_build_object('kind','receipt','id',r.id,'version',r.version,'canonicalization_version','qh-canonical-json-v1','sha256',r.hash) END;
   cm:=qh.execution_map_get(qh.execution_map_get(ac.state,'"commands"'),c.wire->'payload'->'command_id')->'wire'->'payload';
   nm:=qh.execution_map_get(qh.execution_map_get(ac.state,'"nonces"'),c.wire->'payload'->'nonce')->'wire'->'payload';
   rm:=qh.execution_map_get(qh.execution_map_get(ac.state,'"receipts"'),c.wire->'payload'->'command_id')->'wire'->'payload';
   IF NOT ((cm=cr AND nm=cr AND rm IS NOT DISTINCT FROM rr) IS TRUE OR
       (rr IS NOT NULL AND cm IS NULL AND nm IS NULL AND rm IS NULL))
   THEN RAISE EXCEPTION 'execution_atomicity'; END IF;
 END LOOP;
 -- Every retained entry must point to exact current-generation evidence.
 FOREACH map_name IN ARRAY ARRAY['commands','nonces','receipts'] LOOP
   FOR pair IN SELECT value FROM jsonb_array_elements(qh.execution_map_get(ac.state,to_jsonb(map_name))->'map') LOOP
     IF NOT EXISTS(SELECT 1 FROM qh.execution_evidence e WHERE e.account_ref=a
      AND e.kind=CASE WHEN map_name='receipts' THEN 'receipt' ELSE 'challenge' END
      AND pair->1->'wire'->'payload'=jsonb_build_object('kind',e.kind,'id',e.id,'version',e.version,'canonicalization_version','qh-canonical-json-v1','sha256',e.hash)
      AND pair->0=e.wire->'payload'->CASE WHEN map_name='nonces' THEN 'nonce' ELSE 'command_id' END)
     THEN RAISE EXCEPTION 'execution_atomicity'; END IF;
   END LOOP;
 END LOOP;
END $$;
CREATE FUNCTION qh.execution_commit_constraint() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,qh AS $$
DECLARE a text:=coalesce(NEW.account_ref,OLD.account_ref);
BEGIN
 IF EXISTS(SELECT 1 FROM qh.execution_evidence e WHERE e.account_ref=a
  AND e.wire->>'schema_name'='ApprovalRecord' AND e.wire->'payload'->>'state'='consumed'
  AND NOT EXISTS(SELECT 1 FROM qh.execution_intent i JOIN qh.execution_claim c USING(account_ref,intent_id)
   JOIN qh.execution_outbox o USING(account_ref,intent_id)
   WHERE i.account_ref=a AND i.approval_id=e.wire->'payload'->>'approval_id'
   AND i.intent_id=e.wire->'payload'->>'consumed_intent_id'))
 OR EXISTS(SELECT 1 FROM qh.execution_intent i WHERE i.account_ref=a AND (
   NOT EXISTS(SELECT 1 FROM qh.execution_outbox o WHERE o.account_ref=a AND o.intent_id=i.intent_id) OR
   NOT EXISTS(SELECT 1 FROM qh.execution_claim c WHERE c.account_ref=a AND c.intent_id=i.intent_id
     AND c.candidate_id=i.candidate_id AND c.candidate_version=i.candidate_version) OR
   NOT EXISTS(SELECT 1 FROM qh.execution_head h JOIN qh.execution_evidence e USING(account_ref,kind,id,version,hash)
     WHERE h.account_ref=a AND h.kind='approval' AND h.id=i.approval_id
     AND e.wire->'payload'->>'state'='consumed' AND e.wire->'payload'->>'consumed_intent_id'=i.intent_id) OR
   (SELECT count(*) FROM qh.execution_reservation r WHERE r.account_ref=a AND r.intent_id=i.intent_id)<>4))
 THEN RAISE EXCEPTION 'execution_atomicity'; END IF;
 IF EXISTS(SELECT 1 FROM qh.execution_evidence r WHERE r.account_ref=a AND r.wire->>'schema_name'='ActionReceipt'
   AND NOT EXISTS(SELECT 1 FROM qh.execution_evidence c WHERE c.account_ref=a AND c.kind='challenge'
     AND c.id=r.wire->'payload'->'challenge_ref'->>'id'
     AND c.version=(r.wire->'payload'->'challenge_ref'->>'version')::integer
     AND c.hash=r.wire->'payload'->'challenge_ref'->>'sha256'
     AND c.wire->'payload'->>'command_id'=r.wire->'payload'->>'command_id'
     AND c.wire->'payload'->>'action'=r.wire->'payload'->>'action'
     AND c.wire->'payload'->'principal_ref'=r.wire->'payload'->'actor_evidence_ref'
     AND c.wire->'payload'->'target_ref'=r.wire->'payload'->'target_ref'
     AND r.wire->'payload'->>'command_payload_hash'=encode(sha256(convert_to(qh.ledger_canonical(c.wire),'UTF8')),'hex')))
 THEN RAISE EXCEPTION 'execution_contract'; END IF;
 PERFORM qh.execution_check_lookups(a);
 RETURN NULL;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['execution_account','execution_evidence','execution_head','execution_intent','execution_claim','execution_outbox','execution_reservation'] LOOP
 EXECUTE format('CREATE CONSTRAINT TRIGGER execution_commit_constraint AFTER INSERT OR UPDATE OR DELETE ON qh.%I DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.execution_commit_constraint()',t);
 END LOOP;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qh FROM PUBLIC;
CREATE UNIQUE INDEX execution_challenge_command ON qh.execution_evidence(account_ref,(wire->'payload'->>'command_id')) WHERE wire->>'schema_name'='ActionChallenge';
CREATE UNIQUE INDEX execution_challenge_nonce ON qh.execution_evidence(account_ref,(wire->'payload'->>'nonce')) WHERE wire->>'schema_name'='ActionChallenge';
CREATE UNIQUE INDEX execution_receipt_command ON qh.execution_evidence(account_ref,(wire->'payload'->>'command_id')) WHERE wire->>'schema_name'='ActionReceipt';
CREATE FUNCTION qh.execution_head_step() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,qh AS $$
DECLARE e qh.execution_evidence;
BEGIN
 IF TG_OP='INSERT' THEN
   IF EXISTS(SELECT 1 FROM qh.execution_head h WHERE h.account_ref=NEW.account_ref AND h.kind=NEW.kind AND h.id=NEW.id) THEN RETURN NEW; END IF;
   IF NEW.version<>1 THEN RAISE EXCEPTION 'execution_version'; END IF;
 ELSE
   IF NEW.version=OLD.version AND NEW.hash=OLD.hash THEN RETURN NEW; END IF;
   SELECT * INTO STRICT e FROM qh.execution_evidence WHERE account_ref=NEW.account_ref AND kind=NEW.kind AND id=NEW.id AND version=NEW.version;
   IF NEW.version<>OLD.version+1 OR e.wire->'payload'->'previous_ref'->>'sha256' IS DISTINCT FROM OLD.hash
   THEN RAISE EXCEPTION 'execution_version'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER execution_head_step BEFORE INSERT OR UPDATE ON qh.execution_head FOR EACH ROW EXECUTE FUNCTION qh.execution_head_step();
CREATE FUNCTION qh.execution_stage_empty() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,qh AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM qh.execution_stage WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id())
 OR EXISTS(SELECT 1 FROM qh.execution_context WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id())
 OR EXISTS(SELECT 1 FROM qh.execution_read_buffer WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id())
 THEN RAISE EXCEPTION 'execution_frame'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER execution_stage_empty AFTER INSERT OR UPDATE ON qh.execution_stage DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.execution_stage_empty();
CREATE CONSTRAINT TRIGGER execution_context_empty AFTER INSERT OR UPDATE ON qh.execution_context DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.execution_stage_empty();
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qh FROM PUBLIC;
CREATE CONSTRAINT TRIGGER execution_read_empty AFTER INSERT OR UPDATE ON qh.execution_read_buffer DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.execution_stage_empty();
-- Attribute the bytes of duplicated state entries to the same intent owner.
-- They remain part of the physical canonical account row; this is an exact
-- partition of its byte charge, not a second row or a discarded copy.
CREATE FUNCTION qh.execution_state_copies(a text)
RETURNS TABLE(owner text,category text,logical_records integer,canonical_bytes bigint)
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,qh AS $$
DECLARE packed jsonb; group_row jsonb; pair jsonb; value jsonb; reference jsonb; wire jsonb;
 map_name text; owner_id text; kind text; extra integer;
BEGIN
 SELECT state INTO packed FROM qh.execution_account WHERE account_ref=a;
 FOR group_row IN SELECT v FROM jsonb_array_elements(packed->'map') t(v) LOOP
   map_name:=group_row->>0;
   IF NOT coalesce(group_row->1 ? 'map',false) THEN CONTINUE; END IF;
   FOR pair IN SELECT v FROM jsonb_array_elements(group_row->1->'map') t(v) LOOP
     value:=pair->1;reference:=coalesce(pair->0->'wire'->'payload',CASE WHEN value->'wire'->'payload' ? 'sha256' THEN value->'wire'->'payload' END);wire:=value->'wire';
     owner_id:=coalesce(wire->'payload'->>'intent_id',
       CASE WHEN jsonb_typeof(pair->0)='string' AND EXISTS(SELECT 1 FROM qh.execution_intent WHERE account_ref=a AND intent_id=pair->>0) THEN pair->>0 END,
       CASE WHEN EXISTS(SELECT 1 FROM qh.execution_intent WHERE account_ref=a AND intent_id=pair->0->'tuple'->>0) THEN pair->0->'tuple'->>0 END);
     IF owner_id IS NULL AND reference IS NOT NULL THEN
       SELECT qh.execution_owner(a,'execution_evidence',to_jsonb(e)) INTO owner_id
        FROM qh.execution_evidence e WHERE e.account_ref=a AND e.kind=reference->>'kind' AND e.id=reference->>'id'
        AND e.version=(reference->>'version')::integer AND e.hash=reference->>'sha256';
     END IF;
     IF owner_id IS NULL AND map_name='holds' THEN
       SELECT intent_id INTO owner_id FROM qh.execution_intent WHERE account_ref=a AND approval_id=pair->>0;
     END IF;
     owner:=coalesce(owner_id,'@common');
     category:=CASE WHEN owner='@common' THEN 'common' WHEN map_name IN ('commands','nonces','receipts','holds','cancel_commands','cancel_nonces','withdrawals') THEN 'control'
       WHEN map_name IN ('events','event_dispositions','event_heads','unknown_costs','ledger_mapping') THEN 'broker' ELSE 'base' END;
     logical_records:=CASE WHEN map_name IN ('commands','nonces','receipts','holds','permissions') THEN 1 ELSE 0 END;
     IF owner='@common' AND map_name='records' THEN
       SELECT e.wire INTO wire FROM qh.execution_evidence e WHERE e.account_ref=a AND e.kind=reference->>'kind'
        AND e.id=reference->>'id' AND e.hash=reference->>'sha256' AND e.version=(reference->>'version')::integer;
       IF wire IS NULL THEN RAISE EXCEPTION 'execution_contract'; END IF;
       extra:=CASE WHEN wire->>'schema_name' IN ('PrincipalEvidence','SessionRecord','SyntheticRuntimeEvidence',
         'ActionChallenge','ActionReceipt','WithdrawalRequest','ExecutionReconciliation') THEN 20480 ELSE 147456 END;
       IF octet_length(qh.ledger_canonical(pair))>extra THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     END IF;
     canonical_bytes:=CASE WHEN owner='@common' THEN 0 ELSE octet_length(qh.ledger_canonical(pair)) END;
     RETURN NEXT;
   END LOOP;
 END LOOP;
END $$;
-- Common completion is finite: current issued command closures, terminal
-- session controls, prepared dispatch, and one recovery capsule per admission.
-- Optional new controls/restarts must fit again; no infinite history guarantee.
CREATE FUNCTION qh.execution_common_remaining(a text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,qh AS $$
DECLARE packed jsonb; plan jsonb; mode_name text; h record; body jsonb; principal jsonb;
 pair jsonb; command_body jsonb; pending boolean;
 n bigint:=0; z bigint:=65536; extra integer; slots integer; units integer; credit integer; credit_bytes bigint; stop_seen boolean;
 repair_records constant integer:=2; repair_bytes constant bigint:=393216;
 stop_records constant integer:=3; stop_bytes constant bigint:=458752;
 session_records constant integer:=13; session_bytes constant bigint:=1376256;
BEGIN
 SELECT state,common_plan,mode INTO packed,plan,mode_name FROM qh.execution_account WHERE account_ref=a;
 PERFORM qh.ledger_keys(plan,ARRAY['next','sessions','rebind','resume']);
 PERFORM qh.ledger_int(plan->'next',0,1);PERFORM qh.ledger_int(plan->'sessions',0,2);
 PERFORM qh.ledger_int(plan->'rebind',0,1);PERFORM qh.ledger_int(plan->'resume',0,1);
 FOR h IN SELECT e.wire->'payload' body,e.kind FROM qh.execution_head x JOIN qh.execution_evidence e USING(account_ref,kind,id,version,hash)
  WHERE x.account_ref=a AND x.kind IN ('session','approval') LOOP
   body:=h.body;
   IF h.kind='session' AND body->>'state'='running' THEN
     -- Terminal event + session version. Each controller separately owns
     -- a stop and a fresh-query repair before resume and after resume.
     -- Repair stores both query and reconciliation; even identical broker
     -- economics may arrive under a new immutable query identity.
     credit:=2;credit_bytes:=2*65536;
     SELECT e.wire->'payload' INTO principal FROM qh.execution_evidence e WHERE e.account_ref=a AND e.kind='principal'
      AND e.id=body->'principal_ref'->>'id' AND e.hash=body->'principal_ref'->>'sha256';
     IF principal->>'role'='controller' THEN
       SELECT EXISTS(SELECT 1 FROM qh.execution_evidence e JOIN qh.execution_account ac USING(account_ref)
        WHERE e.account_ref=a AND e.kind='runtime' AND e.wire->'payload'->>'authority_generation'=ac.generation
         AND e.wire->'payload'->>'kind'='explicit_synthetic_stop') INTO stop_seen;
       IF mode_name<>'stopped' OR (plan->>'resume'='1' AND plan->>'rebind'='1' AND NOT stop_seen)
        THEN credit:=credit+stop_records;credit_bytes:=credit_bytes+stop_bytes; END IF;
       IF plan->>'resume'='1' THEN credit:=credit+stop_records;credit_bytes:=credit_bytes+stop_bytes; END IF;
     ELSIF plan->>'resume'='1' THEN
       -- A noncontroller's mandatory terminal event/session update also
       -- invalidates a matched read-set. Its OWN live reserve funds the new
       -- query+reconciliation when an already-promised resume needs repair.
       -- Running/ordinary stopped have no resume promise. Elective rebind
       -- acquires this additional credit for every live noncontroller first.
       -- Do not borrow another session/controller/intent's completion budget.
       credit:=credit+repair_records;credit_bytes:=credit_bytes+repair_bytes;
     END IF;
     n:=n+credit;z:=z+credit_bytes;
   ELSIF h.kind='approval' AND body->>'state' IN ('pending','approved') THEN
     SELECT count(*)>0 INTO pending FROM qh.execution_evidence c WHERE c.account_ref=a AND c.kind='challenge'
       AND c.wire->'payload'->>'authority_generation'=(SELECT generation FROM qh.execution_account WHERE account_ref=a)
       AND c.wire->'payload'->'target_ref'->>'id'=body->>'approval_id'
       AND NOT EXISTS(
        SELECT 1 FROM qh.execution_evidence r WHERE r.account_ref=a AND r.kind='receipt'
         AND r.wire->'payload'->>'command_id'=c.wire->'payload'->>'command_id');
     -- Atomic unissued challenge+withdraw adds 3 challenge/index rows, then
     -- runtime+approval+receipt+receipt lookup minus hold = 3. Recovery needs
     -- another 2 query/reconciliation rows: 8 rather than the normal 7.
     -- If another (nonprotective) command keeps the hold alive, it needs 9.
     -- Approval closure remains funded even with issued protection: an expired
     -- command may be rejected while the approval stays live. Its receipt must
     -- not recreate an unfunded approval/atomic-withdraw promise.
     units:=CASE WHEN body->>'state'='pending' THEN 2
       WHEN plan->>'resume'='1' THEN 8+pending::integer ELSE 7 END;
     n:=n+units;z:=z+units*32768+262144;
     IF body->>'state'='approved' AND plan->>'resume'='1'
      THEN z:=z+repair_bytes; END IF;
   END IF;
 END LOOP;
 FOR command_body IN SELECT c.wire->'payload' FROM qh.execution_evidence c JOIN qh.execution_account ac USING(account_ref)
   WHERE c.account_ref=a AND c.kind='challenge' AND c.wire->'payload'->>'authority_generation'=ac.generation
    AND NOT EXISTS(SELECT 1 FROM qh.execution_evidence r WHERE r.account_ref=a AND r.kind='receipt'
      AND r.wire->'payload'->>'command_id'=c.wire->'payload'->>'command_id') LOOP
   IF EXISTS(SELECT 1 FROM qh.execution_intent i WHERE i.account_ref=a AND i.approval_id=command_body->'target_ref'->>'id') THEN CONTINUE; END IF;
   -- Current-generation immutable commands retain closure credit even after
   -- another command terminates their target. Protective closure owns >=5
   -- rows at issuance. During recovery, a retained hold means 4 actual rows
   -- plus repair 2, hence 6 (last command releasing its hold needs only 5).
   -- Other rejected commands can also expire/invalidate an approval; reserve
   -- 6 for them while resume is promised. Approve's 9 already covers this.
   units:=CASE WHEN command_body->>'action'='approve' THEN 9
     WHEN plan->>'resume'='1' THEN 6
     WHEN command_body->>'action' IN ('withdraw','revoke') THEN 5 ELSE 4 END;
   n:=n+units;z:=z+units*32768+262144;
   -- The new query has bounded large copies in addition to small closure rows.
   -- Fund these before elective rebind, including terminal-target rejection.
   IF plan->>'resume'='1' THEN z:=z+repair_bytes; END IF;
 END LOOP;
 -- An unused slot pays five actual rows + two terminal rows + two
 -- independently funded stop/repair pairs. Elective controls must fit anew.
 -- After a protective recovery stop, reconcile (without another mode change)
 -- completes the promise. Another rebind that reopens reconciling is elective.
 -- A funded repair must also accept a newly issued complete query. Never
 -- release its query row merely because an older query remains in history.
 -- Rows: session 5 + terminal 2 + two (stop 1 + repair 2) = 13.
 -- A recovering noncontroller needs 5 + terminal 2 + terminal repair 2 = 9
 -- rows, 5*65536 + 2*65536 + 393216 = 851968 bytes. This is within
 -- the SAME unused slot (13 / 1376256); no capsule/limit increase.
 -- Bytes: small row/index/copy 65536; repair also reserves 262144 for
 -- the bounded large query copies. The next two-session recovery is
 -- 29 rows / 3211264 bytes, without raising any account or owner limit.
 slots:=(plan->>'next')::integer;
 n:=n+slots*(2*session_records+repair_records+1)+(plan->>'sessions')::integer*session_records
  +(plan->>'rebind')::integer*repair_records+(plan->>'resume')::integer;
 z:=z+slots*(2*session_bytes+repair_bytes+65536)+(plan->>'sessions')::integer*session_bytes
  +(plan->>'rebind')::integer*repair_bytes+(plan->>'resume')::integer*65536;
 SELECT coalesce(sum(greatest(0,2-coalesce((qh.execution_map_get(qh.execution_map_get(packed,'"withdrawals"'),to_jsonb(i.intent_id)))::integer,0))),0)
 INTO extra FROM qh.execution_intent i WHERE i.account_ref=a;
 n:=n+2*extra;z:=z+2*extra*65536;
 -- Each still-possible issuer slot may invalidate a matched reconciliation.
 -- Closed issuers cannot create more facts; unresolved per-owner finance stays
 -- separately reserved in execution_budget. Reconciliation is one account-wide
 -- read-set only when all journals/owners match; these credits are never netted.
 SELECT coalesce(sum(greatest(0,8-(SELECT count(*) FROM qh.execution_broker_inbox x
   WHERE x.account_ref=a AND x.body->>'intent_id'=b.owner))),0) INTO extra
  FROM qh.execution_budget b WHERE b.account_ref=a AND NOT b.closed;
 n:=n+extra;z:=z+extra*65536;
 SELECT count(*)*2 INTO extra FROM qh.execution_intent WHERE account_ref=a AND state='prepared';
 n:=n+extra;z:=z+extra*262144;
 SELECT (CASE WHEN EXISTS(SELECT 1 FROM qh.execution_cursor WHERE account_ref=a) THEN 0 ELSE 1 END)+
  (CASE WHEN EXISTS(SELECT 1 FROM qh.ledger_workstate WHERE account_ref=a AND consumer='synthetic-execution') THEN 0 ELSE 1 END) INTO extra;
 n:=n+extra;z:=z+extra*1536;
 RETURN jsonb_build_object('records',n,'bytes',z,'plan',plan);
END $$;
CREATE FUNCTION qh.execution_check_budget(a text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,qh AS $$
DECLARE b record; limits jsonb:='{"base":32,"broker":64,"ledger":192,"control":64,"late":32}';
 cats text[]:=ARRAY['base','broker','ledger','control','late']; cat text; n bigint; z bigint;
 used_n bigint; used_b bigint; reserve_n bigint; reserve_b bigint; owner_n bigint; owner_b bigint;
 total_n bigint:=128; total_b bigint:=16777216; common_n bigint; common_b bigint; details jsonb; rows jsonb;
 common_future jsonb; old_budget jsonb; next_budget jsonb; old_bytes bigint; new_bytes bigint; adjustment bigint; step integer; reserve_count bigint; converged boolean;
BEGIN
 -- One measurement of each real row/index, including duplicated canonical state.
 SELECT coalesce(jsonb_agg(jsonb_build_object('owner',owner,'category',category,'relation',relation_name,
  'bytes',octet_length(qh.ledger_canonical(row_data))+index_bytes,'row',row_data)),'[]') INTO rows
 FROM qh.execution_storage_rows(a);
 rows:=rows||(SELECT coalesce(jsonb_agg(jsonb_build_object('owner',owner,'category',category,'records',logical_records,'bytes',canonical_bytes,'relation','state_copy')),'[]') FROM qh.execution_state_copies(a));
 SELECT coalesce(sum(coalesce((value->>'records')::integer,1)),0),coalesce(sum((value->>'bytes')::bigint),0) INTO common_n,common_b
 FROM jsonb_array_elements(rows) WHERE value->>'owner'='@common';
 common_b:=common_b-(SELECT coalesce(sum(canonical_bytes),0) FROM qh.execution_state_copies(a));
 common_future:=qh.execution_common_remaining(a);
 IF common_n+(common_future->>'records')::bigint>128 OR common_b+(common_future->>'bytes')::bigint>8388608
 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
 FOR b IN SELECT * FROM qh.execution_budget WHERE account_ref=a ORDER BY owner LOOP
   owner_n:=0; details:='{}'; used_b:=0; used_n:=0;
   FOR cat IN SELECT unnest(cats) LOOP
     SELECT coalesce(sum(coalesce((value->>'records')::integer,1)),0),coalesce(sum((value->>'bytes')::bigint),0) INTO n,z
      FROM jsonb_array_elements(rows) WHERE value->>'owner'=b.owner AND value->>'category'=cat;
     IF n>(limits->>cat)::integer THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     used_n:=used_n+n; used_b:=used_b+z;
     reserve_n:=CASE WHEN b.closed AND cat<>'control' THEN 0 ELSE (limits->>cat)::integer-n END;
     IF b.closed AND cat='control' THEN
       -- Terminal finality forbids new cancel attempts. Keep each remaining
       -- protective withdrawal and every still-authorized issued command closure.
       SELECT 8*greatest(0,2-coalesce((qh.execution_map_get(qh.execution_map_get(state,'"withdrawals"'),to_jsonb(b.owner)))::integer,0))
        INTO reserve_n FROM qh.execution_account WHERE account_ref=a;
       SELECT reserve_n+6*count(*) INTO reserve_n FROM qh.execution_evidence c
        JOIN qh.execution_intent i ON i.account_ref=c.account_ref AND i.approval_id=c.wire->'payload'->'target_ref'->>'id'
        JOIN qh.execution_account ac ON ac.account_ref=c.account_ref
        WHERE c.account_ref=a AND i.intent_id=b.owner AND c.kind='challenge'
         AND c.wire->'payload'->>'authority_generation'=ac.generation AND NOT EXISTS(
          SELECT 1 FROM qh.execution_evidence r WHERE r.account_ref=a AND r.kind='receipt'
           AND r.wire->'payload'->>'command_id'=c.wire->'payload'->>'command_id');
     END IF;
     IF b.closed AND cat='ledger' THEN
       SELECT count(*) INTO reserve_n FROM qh.ledger_outbox o
       WHERE o.account_ref=a AND qh.execution_cursor_owner(a,o.cursor)=b.owner AND NOT EXISTS(
         SELECT 1 FROM qh.ledger_inbox i WHERE i.consumer='synthetic-execution' AND i.message_id=o.message_id);
     END IF;
     IF n+reserve_n>(limits->>cat)::integer THEN RAISE EXCEPTION 'execution_capacity'; END IF;
     owner_n:=owner_n+n+reserve_n;
     details:=details||jsonb_build_object(cat,reserve_n);
   END LOOP;
   reserve_count:=owner_n-used_n;
   old_budget:=to_jsonb(b);old_bytes:=octet_length(qh.ledger_canonical(old_budget));adjustment:=0;converged:=false;
   FOR step IN 1..8 LOOP
     reserve_b:=CASE WHEN b.closed THEN (coalesce((details->>'control')::bigint,0)*202752+coalesce((details->>'ledger')::bigint,0)*1536) ELSE 25165824-used_b-adjustment END;
     next_budget:=old_budget||jsonb_build_object('reserved_records',reserve_count,'reserved_bytes',reserve_b,'remaining',details);
     new_bytes:=octet_length(qh.ledger_canonical(next_budget));
     IF adjustment=new_bytes-old_bytes THEN converged:=true;EXIT; END IF;
     adjustment:=new_bytes-old_bytes;
   END LOOP;
   IF NOT converged OR reserve_b<0 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
   owner_b:=used_b+adjustment+reserve_b;
   IF owner_n>384 OR owner_b>25165824 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
   UPDATE qh.execution_budget SET reserved_records=reserve_count,reserved_bytes=reserve_b,remaining=details
    WHERE account_ref=a AND owner=b.owner;
   total_n:=total_n+owner_n;total_b:=total_b+owner_b;
 END LOOP;
 IF total_n>1024 OR total_b>67108864 THEN RAISE EXCEPTION 'execution_capacity'; END IF;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qh FROM PUBLIC;

-- Exact common actual rows/index/copy bytes plus stage obligations. This also
-- includes the account metadata, common_plan and current reconciliation copy.
CREATE FUNCTION qh.execution_common_charge(a text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,qh AS $$
DECLARE n bigint; z bigint; future jsonb;
BEGIN
 SELECT coalesce(sum(r),0),coalesce(sum(b),0) INTO n,z FROM (
  SELECT 1::bigint r,octet_length(qh.ledger_canonical(row_data))+index_bytes b
   FROM qh.execution_storage_rows(a) WHERE owner='@common'
  UNION ALL SELECT CASE WHEN owner='@common' THEN logical_records ELSE 0 END,
   CASE WHEN owner='@common' THEN 0 ELSE -canonical_bytes END FROM qh.execution_state_copies(a)) costs;
 future:=qh.execution_common_remaining(a);
 RETURN jsonb_build_object('records',n+(future->>'records')::bigint,'bytes',z+(future->>'bytes')::bigint,
  'actual_records',n,'actual_bytes',z,'remaining',future);
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA qh FROM PUBLIC;
