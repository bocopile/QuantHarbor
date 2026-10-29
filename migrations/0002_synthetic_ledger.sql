-- Q20 synthetic-only. Requires 0001 and PostgreSQL 18. No extension/driver.
-- Unlimited numeric with exact checks deliberately precedes any storage coercion.
CREATE FUNCTION qh.ledger_number(n numeric) RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT n::text NOT IN ('NaN','Infinity','-Infinity') AND abs(n)<100000000000000000000 AND trunc(n,18)=n
$$;
CREATE FUNCTION qh.ledger_decimal(v jsonb) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE t text; n numeric;
BEGIN
 IF jsonb_typeof(v) IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 t := v #>> '{}';
 IF length(t)>80 OR t !~ '^-?(0|[1-9][0-9]*)(\.[0-9]+)?$' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 n:=t::numeric;
 IF NOT qh.ledger_number(n) THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 IF length(split_part(ltrim(t,'-'),'.',1))>20 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 IF n=0 THEN RETURN '0'; END IF;
 RETURN trim_scale(n)::text;
END $$;
CREATE FUNCTION qh.ledger_identifier(v jsonb) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE t text;
BEGIN
 IF jsonb_typeof(v) IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 t:=v #>> '{}';
 IF t !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$' COLLATE "C" THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 RETURN t;
END $$;
CREATE FUNCTION qh.ledger_keys(v jsonb, names text[]) RETURNS void LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
 IF jsonb_typeof(v) IS DISTINCT FROM 'object' OR (SELECT array_agg(k ORDER BY k COLLATE "C") FROM jsonb_object_keys(v) k)
 IS DISTINCT FROM (SELECT array_agg(k ORDER BY k COLLATE "C") FROM unnest(names) k)
 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
END $$;
CREATE FUNCTION qh.ledger_int(v jsonb, lo integer, hi integer) RETURNS integer LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE t text;
BEGIN
 t:=v::text;
 IF jsonb_typeof(v) IS DISTINCT FROM 'number' OR t !~ '^(0|[1-9][0-9]*)$' OR length(t)>10
 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 IF t::bigint<lo OR t::bigint>hi THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 RETURN t::integer;
END $$;
CREATE FUNCTION qh.ledger_instant(v jsonb) RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE t text; z text; local_stamp timestamp; offset_minutes integer:=0; suffix text;
BEGIN
 IF jsonb_typeof(v) IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 t:=v #>> '{}';
 IF t !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-]([01][0-9]|2[0-3]):[0-5][0-9])$'
 OR substring(t,18,2)::int>59 OR substring(t,15,2)::int>59 OR substring(t,12,2)::int>23
 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 local_stamp:=regexp_replace(t,'(Z|[+-][0-9]{2}:[0-9]{2})$','')::timestamp;
 IF right(t,1)<>'Z' THEN
   suffix:=right(t,6);
   offset_minutes:=(substring(suffix,2,2)::integer*60+substring(suffix,5,2)::integer)*CASE WHEN left(suffix,1)='-' THEN -1 ELSE 1 END;
 END IF;
 z:=to_char(local_stamp-offset_minutes*interval '1 minute','YYYY-MM-DD"T"HH24:MI:SS.US"Z"');
 IF substring(z,1,4)<'2000' OR substring(z,1,4)>'2100' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 RETURN z;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RAISE EXCEPTION 'ledger_contract';
END $$;
CREATE FUNCTION qh.ledger_canonical(j jsonb) RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE result text;
BEGIN
 CASE jsonb_typeof(j)
 WHEN 'object' THEN
   SELECT '{'||coalesce(string_agg(to_jsonb(key)::text||':'||qh.ledger_canonical(value),',' ORDER BY key COLLATE "C"),'')||'}' INTO result FROM jsonb_each(j);
 WHEN 'array' THEN
   SELECT '['||coalesce(string_agg(qh.ledger_canonical(value),',' ORDER BY ord),'')||']' INTO result FROM jsonb_array_elements(j) WITH ORDINALITY a(value,ord);
 ELSE result:=j::text;
 END CASE;
 RETURN result;
END $$;
CREATE FUNCTION qh.ledger_hash(schema_name text, payload jsonb) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT encode(sha256(convert_to('QuantHarbor/qh-canonical-json-v1'||chr(10)||qh.ledger_canonical(
 jsonb_build_object('schema_name',schema_name,'schema_version',1,'environment','synthetic','payload',payload)),'UTF8')),'hex')
$$;
CREATE FUNCTION qh.ledger_wire_check(j json) RETURNS void LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE x json;
BEGIN
 IF json_typeof(j)='object' THEN
   IF (SELECT count(*)<>count(DISTINCT key) FROM json_each(j)) THEN RAISE EXCEPTION 'ledger_contract'; END IF;
   FOR x IN SELECT value FROM json_each(j) LOOP PERFORM qh.ledger_wire_check(x); END LOOP;
 ELSIF json_typeof(j)='array' THEN
   FOR x IN SELECT value FROM json_array_elements(j) LOOP PERFORM qh.ledger_wire_check(x); END LOOP;
 ELSIF json_typeof(j)='number' THEN
   IF j::text !~ '^(0|[1-9][0-9]*)$' OR length(j::text)>10 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 END IF;
END $$;
CREATE FUNCTION qh.ledger_wire(t text) RETURNS jsonb LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE j json;
BEGIN
 IF t IS NULL OR octet_length(t)>65536 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 j:=t::json; PERFORM qh.ledger_wire_check(j); RETURN j::jsonb;
EXCEPTION WHEN invalid_text_representation OR character_not_in_repertoire OR invalid_parameter_value
 THEN RAISE EXCEPTION 'ledger_contract';
END $$;
CREATE FUNCTION qh.ledger_submission(j jsonb) RETURNS jsonb LANGUAGE plpgsql STABLE AS $$
DECLARE x jsonb; legs jsonb:='[]'; positions jsonb:='[]'; vals jsonb; k text; a text; normalized jsonb;
BEGIN
 PERFORM qh.ledger_keys(j,ARRAY['schema_version','environment','account_ref','source_kind','source_event_key','source_revision',
 'predecessor_revision','mapping_version','event_type','effective_at','revision_mode','correction_of','cash_legs','position_deltas',
 'evidence_refs','completeness','baseline','dependency_refs','split_ratio']);
 IF octet_length(qh.ledger_canonical(j))>65536 OR qh.ledger_int(j->'schema_version',1,1)<>1 OR j->'environment' IS DISTINCT FROM '"synthetic"'::jsonb
 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 a:=qh.ledger_identifier(j->'account_ref');
 IF a NOT LIKE 'synthetic-account:%' OR a='synthetic-account:' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 FOREACH k IN ARRAY ARRAY['source_kind','source_event_key','mapping_version'] LOOP PERFORM qh.ledger_identifier(j->k); END LOOP;
 PERFORM qh.ledger_int(j->'source_revision',1,2147483647);
 IF j->'predecessor_revision'<>'null'::jsonb THEN PERFORM qh.ledger_int(j->'predecessor_revision',1,2147483647); END IF;
 IF j->'correction_of'<>'null'::jsonb THEN PERFORM qh.ledger_identifier(j->'correction_of'); END IF;
 IF j->>'event_type' NOT IN ('baseline','trade','fee','tax','deposit','withdrawal','dividend','fx','settlement','split','unsupported')
 OR jsonb_typeof(j->'event_type')<>'string' OR jsonb_typeof(j->'revision_mode')<>'string'
 OR j->>'revision_mode' NOT IN ('original','retroactive','prospective','unsupported') THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 FOREACH k IN ARRAY ARRAY['cash_legs','position_deltas','evidence_refs','dependency_refs'] LOOP
   IF jsonb_typeof(j->k)<>'array' OR jsonb_array_length(j->k)>32 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 END LOOP;
 FOR x IN SELECT value FROM jsonb_array_elements(j->'cash_legs') LOOP
   PERFORM qh.ledger_keys(x,ARRAY['account','currency','amount','basis']);
   IF x->>'account' NOT IN ('settled_cash','unsettled_receivable','unsettled_payable','trade_clearing','opening_equity','external_flow','fee_expense','tax_expense','dividend_income','fx_clearing')
   OR x->>'currency' NOT IN ('KRW','USD') OR x->>'basis' NOT IN ('trade','settlement')
   OR jsonb_typeof(x->'account')<>'string' OR jsonb_typeof(x->'currency')<>'string' OR jsonb_typeof(x->'basis')<>'string'
   THEN RAISE EXCEPTION 'ledger_contract'; END IF;
   legs:=legs||jsonb_build_array(x||jsonb_build_object('amount',qh.ledger_decimal(x->'amount')));
 END LOOP;
 IF (SELECT count(*)<>count(DISTINCT (value->>'account',value->>'currency')) FROM jsonb_array_elements(legs)) THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 FOR x IN SELECT value FROM jsonb_array_elements(j->'position_deltas') LOOP
   PERFORM qh.ledger_keys(x,ARRAY['instrument_id','venue_id','mapping_version','unit','amount']);
   FOREACH k IN ARRAY ARRAY['instrument_id','venue_id','mapping_version','unit'] LOOP PERFORM qh.ledger_identifier(x->k); END LOOP;
   IF x->>'mapping_version'<>j->>'mapping_version' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
   positions:=positions||jsonb_build_array(x||jsonb_build_object('amount',qh.ledger_decimal(x->'amount')));
 END LOOP;
 IF (SELECT count(*)<>count(DISTINCT (value->>'instrument_id',value->>'venue_id',value->>'mapping_version',value->>'unit')) FROM jsonb_array_elements(positions)) THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 FOREACH k IN ARRAY ARRAY['evidence_refs','dependency_refs'] LOOP
   FOR x IN SELECT value FROM jsonb_array_elements(j->k) LOOP PERFORM qh.ledger_identifier(x); END LOOP;
   IF (SELECT count(*)<>count(DISTINCT value) FROM jsonb_array_elements(j->k)) THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 END LOOP;
 vals:=j->'completeness'; PERFORM qh.ledger_keys(vals,ARRAY['complete','costs_known','semantics_known']);
 FOREACH k IN ARRAY ARRAY['complete','costs_known','semantics_known'] LOOP
   IF jsonb_typeof(vals->k)<>'boolean' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 END LOOP;
 vals:=j->'baseline';
 IF vals<>'null'::jsonb THEN
   PERFORM qh.ledger_keys(vals,ARRAY['cash_complete','positions_complete','scope']);
   IF jsonb_typeof(vals->'cash_complete')<>'boolean' OR jsonb_typeof(vals->'positions_complete')<>'boolean'
   OR vals->'scope'<>'"entire_account"'::jsonb THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 END IF;
 vals:=j->'split_ratio';
 IF vals<>'null'::jsonb THEN
   PERFORM qh.ledger_keys(vals,ARRAY['numerator','denominator']);
   PERFORM qh.ledger_int(vals->'numerator',1,1000000); PERFORM qh.ledger_int(vals->'denominator',1,1000000);
 END IF;
 normalized:=j||jsonb_build_object('cash_legs',legs,'position_deltas',positions,'effective_at',qh.ledger_instant(j->'effective_at'));
 RETURN normalized;
END $$;

CREATE TABLE qh.ledger_stream (
 account_ref text PRIMARY KEY CHECK (account_ref=qh.ledger_identifier(to_jsonb(account_ref)) AND account_ref LIKE 'synthetic-account:%' AND account_ref<>'synthetic-account:'),
 environment text NOT NULL DEFAULT 'synthetic' CHECK(environment='synthetic'),
 cursor integer NOT NULL DEFAULT 0 CHECK(cursor>=0), recorded_at timestamptz,
 UNIQUE(account_ref,environment)
);
CREATE TABLE qh.ledger_decision (
 account_ref text NOT NULL REFERENCES qh.ledger_stream, cursor integer NOT NULL CHECK(cursor>0),
 recorded_at timestamptz NOT NULL, submission jsonb NOT NULL,
 submission_hash text NOT NULL CHECK(submission_hash=qh.ledger_hash('SyntheticLedgerSubmission',submission)),
 status text NOT NULL CHECK(status IN ('accepted','quarantined')), reason text CHECK(reason IS NULL OR reason=qh.ledger_identifier(to_jsonb(reason))),
 event_ids text[] NOT NULL, projection_id text NOT NULL,
 PRIMARY KEY(account_ref,cursor), CHECK(submission->'account_ref'=to_jsonb(account_ref)),
 CHECK((status='accepted' AND reason IS NULL AND cardinality(event_ids) BETWEEN 1 AND 2) OR
       (status='quarantined' AND reason IS NOT NULL AND cardinality(event_ids)=0))
);
CREATE TABLE qh.ledger_event (
 account_ref text NOT NULL REFERENCES qh.ledger_stream, sequence integer NOT NULL CHECK(sequence>0),
 event_id text NOT NULL UNIQUE, bundle_cursor integer NOT NULL,
 body jsonb NOT NULL, payload_hash text NOT NULL CHECK(payload_hash=qh.ledger_hash('LedgerEventBody',body)),
 canonicalization_version text NOT NULL DEFAULT 'qh-canonical-json-v1' CHECK(canonicalization_version='qh-canonical-json-v1'),
 kind text GENERATED ALWAYS AS (body->>'kind') STORED,
 correction_of text GENERATED ALWAYS AS (body->>'correction_of') STORED,
 source_kind text GENERATED ALWAYS AS (body->>'source_kind') STORED,
 source_event_key text GENERATED ALWAYS AS (body->>'source_event_key') STORED,
 source_revision integer GENERATED ALWAYS AS ((body->>'source_revision')::integer) STORED,
 PRIMARY KEY(account_ref,sequence), UNIQUE(account_ref,event_id),
 FOREIGN KEY(account_ref,bundle_cursor) REFERENCES qh.ledger_decision(account_ref,cursor) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(account_ref,correction_of) REFERENCES qh.ledger_event(account_ref,event_id) DEFERRABLE INITIALLY DEFERRED,
 CHECK(body->'environment'='"synthetic"'::jsonb AND body->'account_ref'=to_jsonb(account_ref) AND body->'event_id'=to_jsonb(event_id) AND (body->>'sequence')::integer=sequence),
 CHECK(kind IN ('replacement','reversal') AND (kind<>'reversal' OR correction_of IS NOT NULL))
);
CREATE UNIQUE INDEX ledger_source_revision ON qh.ledger_event(account_ref,source_kind,source_event_key,source_revision) WHERE kind='replacement';
CREATE UNIQUE INDEX ledger_single_reversal ON qh.ledger_event(correction_of) WHERE kind='reversal';
CREATE TABLE qh.ledger_journal (
 account_ref text NOT NULL, event_id text NOT NULL, ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 32),
 account text NOT NULL CHECK(account IN ('settled_cash','unsettled_receivable','unsettled_payable','trade_clearing','opening_equity','external_flow','fee_expense','tax_expense','dividend_income','fx_clearing')),
 currency text NOT NULL CHECK(currency IN ('KRW','USD')), amount numeric NOT NULL CHECK(qh.ledger_number(amount)),
 basis text NOT NULL CHECK(basis IN ('trade','settlement')), PRIMARY KEY(event_id,ordinal),
 FOREIGN KEY(account_ref,event_id) REFERENCES qh.ledger_event(account_ref,event_id)
);
CREATE TABLE qh.ledger_projection (
 account_ref text NOT NULL REFERENCES qh.ledger_stream, cursor integer NOT NULL,
 projection_id text NOT NULL PRIMARY KEY, supersedes text,
 body jsonb NOT NULL, payload_hash text NOT NULL CHECK(payload_hash=qh.ledger_hash('LedgerProjection',body)),
 UNIQUE(account_ref,projection_id), UNIQUE(account_ref,cursor,projection_id),
 FOREIGN KEY(account_ref,cursor) REFERENCES qh.ledger_decision(account_ref,cursor) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(account_ref,supersedes) REFERENCES qh.ledger_projection(account_ref,projection_id),
 CHECK(body->>'environment'='synthetic' AND body->>'account_ref'=account_ref AND body->>'projection_id'=projection_id AND (body->>'ledger_cursor')::integer=cursor)
);
CREATE TABLE qh.ledger_outbox (
 message_id text PRIMARY KEY REFERENCES qh.ledger_projection(projection_id),
 account_ref text NOT NULL, cursor integer NOT NULL, projection_id text NOT NULL,
 payload_hash text NOT NULL CHECK(payload_hash ~ '^[0-9a-f]{64}$'),
 FOREIGN KEY(account_ref,cursor,projection_id) REFERENCES qh.ledger_projection(account_ref,cursor,projection_id),
 CHECK(message_id=projection_id)
);
CREATE TABLE qh.ledger_delivery (
 message_id text PRIMARY KEY REFERENCES qh.ledger_outbox, acknowledged boolean NOT NULL DEFAULT false
);
CREATE TABLE qh.ledger_inbox (
 consumer text NOT NULL CHECK(consumer=qh.ledger_identifier(to_jsonb(consumer))),
 message_id text NOT NULL REFERENCES qh.ledger_outbox, payload_hash text NOT NULL CHECK(payload_hash ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(consumer,message_id)
);
CREATE TABLE qh.ledger_workstate (
 consumer text NOT NULL CHECK(consumer=qh.ledger_identifier(to_jsonb(consumer))),
 account_ref text NOT NULL REFERENCES qh.ledger_stream, cursor integer NOT NULL CHECK(cursor>0),
 PRIMARY KEY(consumer,account_ref), FOREIGN KEY(account_ref,cursor) REFERENCES qh.ledger_decision(account_ref,cursor)
);
CREATE TABLE qh.ledger_inbox_collision (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 consumer text NOT NULL CHECK(consumer=qh.ledger_identifier(to_jsonb(consumer))),
 message_id text NOT NULL REFERENCES qh.ledger_outbox, supplied_hash text NOT NULL CHECK(supplied_hash ~ '^[0-9a-f]{64}$')
);
CREATE FUNCTION qh.ledger_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'ledger_immutable'; END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['ledger_decision','ledger_event','ledger_journal','ledger_projection','ledger_outbox','ledger_inbox','ledger_inbox_collision'] LOOP
 EXECUTE format('CREATE TRIGGER ledger_immutable BEFORE UPDATE OR DELETE ON qh.%I FOR EACH ROW EXECUTE FUNCTION qh.ledger_immutable()',t);
 END LOOP;
END $$;
CREATE FUNCTION qh.ledger_event_id(a text, seq integer) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT 'ledger:'||substring(encode(sha256(convert_to(a,'UTF8')),'hex'),1,16)||':'||seq::text
$$;
CREATE FUNCTION qh.ledger_projection_id(a text,c integer,t text,k text,m text,s text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
 SELECT 'projection:'||encode(sha256(convert_to(a||'|'||c::text||'|'||t||'|'||k||'|'||m||'|synthetic-ledger-v1|'||coalesce(s,''),'UTF8')),'hex')
$$;
CREATE FUNCTION qh.ledger_signed(xs jsonb, sign integer) RETURNS jsonb LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT coalesce(jsonb_agg(value||jsonb_build_object('amount',qh.ledger_decimal(to_jsonb(trim_scale((value->>'amount')::numeric*sign)::text))) ORDER BY ord),'[]'::jsonb)
 FROM jsonb_array_elements(xs) WITH ORDINALITY a(value,ord)
$$;
CREATE FUNCTION qh.ledger_active(a text) RETURNS SETOF qh.ledger_event LANGUAGE sql VOLATILE AS $$
 SELECT e.* FROM qh.ledger_event e WHERE e.account_ref=a AND e.kind='replacement'
 AND NOT EXISTS(SELECT 1 FROM qh.ledger_event r WHERE r.account_ref=a AND r.kind='reversal' AND r.correction_of=e.event_id)
$$;
CREATE FUNCTION qh.ledger_replay(a text, asof_input text, cutoff_input text, c integer DEFAULT NULL,
 mode text DEFAULT 'as_known', reducer text DEFAULT 'synthetic-ledger-v1', supersedes_input text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql VOLATILE AS $$
DECLARE t text; k text; cash jsonb; holdings jsonb; reasons text[]:='{}'; baseline_count integer;
 invalid boolean; consequence boolean; p jsonb; pid text;
BEGIN
 PERFORM qh.ledger_identifier(to_jsonb(a));
 IF a NOT LIKE 'synthetic-account:%' OR a='synthetic-account:' OR mode IS NULL OR mode NOT IN ('as_known','restated')
 OR reducer IS DISTINCT FROM 'synthetic-ledger-v1' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 t:=qh.ledger_instant(to_jsonb(asof_input)); k:=qh.ledger_instant(to_jsonb(cutoff_input));
 c:=coalesce(c,(SELECT cursor FROM qh.ledger_stream WHERE account_ref=a),0);
 IF c<0 OR (c<>0 AND NOT EXISTS(SELECT 1 FROM qh.ledger_decision WHERE account_ref=a AND cursor=c)) THEN RAISE EXCEPTION 'ledger_cursor'; END IF;
 IF supersedes_input IS NOT NULL AND NOT EXISTS(SELECT 1 FROM qh.ledger_projection WHERE account_ref=a AND projection_id=supersedes_input)
 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 WITH selected AS (
   SELECT * FROM qh.ledger_event WHERE account_ref=a AND sequence<=c AND body->>'recorded_at'<=k AND body->>'effective_at'<=t
 ), cash_values AS (
   SELECT x->>'account' AS acc,x->>'currency' AS curr,sum((x->>'amount')::numeric) AS amount
   FROM selected e CROSS JOIN LATERAL jsonb_array_elements(e.body->'cash_legs') x GROUP BY 1,2
 ), position_values AS (
   SELECT x->>'instrument_id' AS instrument,x->>'venue_id' AS venue,x->>'mapping_version' AS mapping,x->>'unit' AS unit,
     sum((x->>'amount')::numeric) AS amount
   FROM selected e CROSS JOIN LATERAL jsonb_array_elements(e.body->'position_deltas') x GROUP BY 1,2,3,4
 )
 SELECT
 (SELECT coalesce(jsonb_agg(jsonb_build_object('account',acc,'currency',curr,'amount',qh.ledger_decimal(to_jsonb(trim_scale(amount)::text))) ORDER BY acc COLLATE "C",curr COLLATE "C"),'[]') FROM cash_values),
 (SELECT coalesce(jsonb_agg(jsonb_build_object('instrument_id',instrument,'venue_id',venue,'mapping_version',mapping,'unit',unit,'amount',qh.ledger_decimal(to_jsonb(trim_scale(amount)::text))) ORDER BY instrument COLLATE "C",venue COLLATE "C",mapping COLLATE "C",unit COLLATE "C"),'[]') FROM position_values),
 (SELECT coalesce(sum(CASE WHEN kind='reversal' THEN -1 ELSE 1 END),0) FROM selected WHERE body->'submission'->>'event_type'='baseline'),
 (EXISTS(SELECT 1 FROM position_values WHERE amount<0) OR EXISTS(SELECT 1 FROM cash_values WHERE
    (acc IN ('settled_cash','unsettled_receivable') AND amount<0) OR (acc='unsettled_payable' AND amount>0))),
 EXISTS(SELECT 1 FROM selected e WHERE e.kind='replacement' AND
   NOT EXISTS(SELECT 1 FROM selected r WHERE r.kind='reversal' AND r.correction_of=e.event_id)
   AND (EXISTS(SELECT 1 FROM jsonb_array_elements_text(e.body->'submission'->'dependency_refs') d
     JOIN selected r ON r.kind='reversal' AND r.correction_of=d.value)
   OR (e.body->'submission'->>'event_type'='split' AND EXISTS(
     SELECT 1 FROM selected r CROSS JOIN LATERAL jsonb_array_elements(r.body->'position_deltas') rp
     CROSS JOIN LATERAL jsonb_array_elements(e.body->'position_deltas') ep
     WHERE rp-'amount'=ep-'amount' AND (
       (r.kind='reversal' AND (r.sequence>e.sequence OR r.body->>'effective_at'>e.body->>'effective_at'))
       OR (r.kind='replacement' AND r.sequence>e.sequence AND r.body->>'effective_at'<=e.body->>'effective_at'))))))
 INTO cash,holdings,baseline_count,invalid,consequence;
 IF baseline_count<>1 THEN reasons:=array_append(reasons,'baseline_missing'); END IF;
 IF invalid THEN reasons:=array_append(reasons,'economic_balance_invalid'); END IF;
 IF consequence THEN reasons:=array_append(reasons,'correction_consequences_unresolved'); END IF;
 IF EXISTS(SELECT 1 FROM qh.ledger_decision d WHERE d.account_ref=a AND d.cursor<=c AND d.recorded_at<=k::timestamptz
   AND d.status='quarantined' AND d.submission->>'effective_at'<=t AND NOT EXISTS(
   SELECT 1 FROM qh.ledger_decision x WHERE x.account_ref=a AND x.cursor<=c AND x.recorded_at<=k::timestamptz
   AND x.status='accepted' AND x.submission_hash=d.submission_hash)) THEN reasons:=array_append(reasons,'quarantined_observation'); END IF;
 SELECT coalesce(array_agg(v ORDER BY v COLLATE "C"),'{}') INTO reasons FROM unnest(reasons) v;
 pid:=qh.ledger_projection_id(a,c,t,k,mode,supersedes_input);
 p:=jsonb_build_object('schema_version',1,'environment','synthetic','account_ref',a,'projection_id',pid,
 'ledger_cursor',c,'as_of',t,'knowledge_cutoff',k,'mode',mode,'reducer_version',reducer,'supersedes_projection_id',supersedes_input,
 'cash_balances',cash,'holdings',holdings,'baseline_known',baseline_count=1,'complete',cardinality(reasons)=0,
 'reason_codes',to_jsonb(reasons),'available_cash',NULL,'reserved_cash',NULL,'broker_buy_capacity',NULL,
 'availability_reason','availability_semantics_unverified');
 IF octet_length(qh.ledger_canonical(jsonb_build_object('schema_name','LedgerProjection','schema_version',1,'environment','synthetic','payload',p)))>65536
 OR jsonb_array_length(cash)>4096 OR jsonb_array_length(holdings)>4096 THEN RAISE EXCEPTION 'ledger_limit'; END IF;
 RETURN p;
END $$;

CREATE FUNCTION qh.ledger_validate_projection() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE b jsonb:=NEW.body; expected jsonb;
BEGIN
 PERFORM qh.ledger_keys(b,ARRAY['schema_version','environment','account_ref','projection_id','ledger_cursor','as_of',
 'knowledge_cutoff','mode','reducer_version','supersedes_projection_id','cash_balances','holdings','baseline_known','complete',
 'reason_codes','available_cash','reserved_cash','broker_buy_capacity','availability_reason']);
 expected:=qh.ledger_replay(NEW.account_ref,b->>'as_of',b->>'knowledge_cutoff',NEW.cursor,b->>'mode',b->>'reducer_version',NEW.supersedes);
 IF b IS DISTINCT FROM expected OR NEW.projection_id IS DISTINCT FROM b->>'projection_id' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ledger_validate_projection BEFORE INSERT ON qh.ledger_projection FOR EACH ROW EXECUTE FUNCTION qh.ledger_validate_projection();

CREATE FUNCTION qh.ledger_semantics(a text,s jsonb,previous jsonb) RETURNS text LANGUAGE plpgsql VOLATILE AS $$
DECLARE event_type text:=s->>'event_type'; legs jsonb:=s->'cash_legs'; pos jsonb:=s->'position_deltas';
 n integer:=jsonb_array_length(legs); np integer:=jsonb_array_length(pos); nc integer; accounts text[];
 dependency_ref jsonb; dep qh.ledger_event; dep_count integer:=0; dep_event qh.ledger_event;
 target text; buying boolean; amount numeric; expected jsonb; actual jsonb; counterparty text; direction integer;
 projection jsonb; old numeric; change numeric;
BEGIN
 IF s->'completeness'<>'{"complete":true,"costs_known":true,"semantics_known":true}'::jsonb THEN RETURN 'incomplete_input'; END IF;
 IF jsonb_array_length(s->'evidence_refs')=0 THEN RETURN 'evidence_missing'; END IF;
 IF event_type='unsupported' OR s->>'revision_mode'='unsupported' THEN RETURN 'unsupported_semantics'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(legs) l GROUP BY l->>'currency' HAVING sum((l->>'amount')::numeric)<>0) THEN RETURN 'unbalanced_journal'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(legs||pos) x WHERE (x->>'amount')::numeric=0) THEN RETURN 'zero_leg'; END IF;
 SELECT count(DISTINCT l->>'currency'),coalesce(array_agg(DISTINCT l->>'account' ORDER BY l->>'account'),'{}') INTO nc,accounts FROM jsonb_array_elements(legs) l;
 IF event_type<>'baseline' AND s->'baseline'<>'null'::jsonb THEN RETURN 'baseline_misuse'; END IF;
 IF event_type<>'split' AND s->'split_ratio'<>'null'::jsonb THEN RETURN 'ratio_misuse'; END IF;
 FOR dependency_ref IN SELECT value FROM jsonb_array_elements(s->'dependency_refs') LOOP
   SELECT * INTO dep FROM qh.ledger_active(a) WHERE event_id=dependency_ref #>> '{}';
   IF NOT FOUND OR dep.body->>'effective_at'>s->>'effective_at' THEN RETURN 'dependency_unresolved'; END IF;
   dep_count:=dep_count+1; dep_event:=dep;
 END LOOP;
 IF event_type='baseline' THEN
   IF previous IS NULL AND EXISTS(SELECT 1 FROM qh.ledger_event WHERE account_ref=a) THEN RETURN 'baseline_requires_first'; END IF;
   IF s->'baseline'='null'::jsonb OR NOT (s->'baseline'->>'cash_complete')::boolean OR NOT (s->'baseline'->>'positions_complete')::boolean THEN RETURN 'baseline_incomplete'; END IF;
   IF dep_count>0 OR NOT accounts <@ ARRAY['settled_cash','opening_equity'] THEN RETURN 'baseline_shape'; END IF;
   IF EXISTS(SELECT 1 FROM jsonb_array_elements(legs) l WHERE l->>'basis'<>'settlement') OR EXISTS(SELECT 1 FROM jsonb_array_elements(pos) p WHERE (p->>'amount')::numeric<0) THEN RETURN 'baseline_shape'; END IF;
   RETURN NULL;
 END IF;
 IF event_type='split' THEN
   IF previous IS NOT NULL THEN RETURN 'split_revision_unsupported'; END IF;
   IF n<>0 OR np<>1 OR s->'split_ratio'='null'::jsonb THEN RETURN 'split_shape'; END IF;
   projection:=qh.ledger_replay(a,s->>'effective_at',coalesce((SELECT to_char(recorded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') FROM qh.ledger_stream WHERE account_ref=a),s->>'effective_at'));
   IF NOT (projection->>'baseline_known')::boolean OR jsonb_array_length(projection->'reason_codes')>0 THEN RETURN 'split_basis_unknown'; END IF;
   SELECT (value->>'amount')::numeric INTO old FROM jsonb_array_elements(projection->'holdings') WHERE value-'amount'=(pos->0)-'amount';
   old:=coalesce(old,0); change:=(pos->0->>'amount')::numeric;
   IF old<=0 OR (old+change)*(s->'split_ratio'->>'denominator')::integer<>old*(s->'split_ratio'->>'numerator')::integer THEN RETURN 'split_ratio_mismatch'; END IF;
   RETURN NULL;
 END IF;
 IF event_type='trade' THEN
   IF np<>1 OR n<>2 OR nc<>1 THEN RETURN 'trade_shape'; END IF;
   buying:=(pos->0->>'amount')::numeric>0;
   target:=CASE WHEN buying THEN 'unsettled_payable' ELSE 'unsettled_receivable' END;
   IF NOT accounts @> ARRAY[target,'trade_clearing'] OR EXISTS(SELECT 1 FROM jsonb_array_elements(legs) l WHERE l->>'basis'<>'trade') THEN RETURN 'trade_shape'; END IF;
   SELECT (l->>'amount')::numeric INTO amount FROM jsonb_array_elements(legs) l WHERE l->>'account'=target;
   IF (amount<0)<>buying THEN RETURN 'trade_direction'; END IF;
   RETURN NULL;
 END IF;
 IF np<>0 THEN RETURN 'unexpected_position_delta'; END IF;
 IF event_type='settlement' THEN
   IF dep_count<>1 OR dep_event.body->'submission'->>'event_type'<>'trade' THEN RETURN 'settlement_dependency'; END IF;
   IF EXISTS(SELECT 1 FROM qh.ledger_active(a) e WHERE e.event_id IS DISTINCT FROM previous->>'event_id' AND
     e.body->'submission'->>'event_type'='settlement' AND e.body->'submission'->'dependency_refs' ? dep_event.event_id) THEN RETURN 'already_settled'; END IF;
   SELECT jsonb_agg(x ORDER BY x->>'account',x->>'currency') INTO expected FROM (
     SELECT l||jsonb_build_object('amount',qh.ledger_decimal(to_jsonb(trim_scale(-(l->>'amount')::numeric)::text)),'basis','settlement') x
     FROM jsonb_array_elements(dep_event.body->'cash_legs') l WHERE l->>'account' LIKE 'unsettled_%'
     UNION ALL SELECT l||jsonb_build_object('account','settled_cash','basis','settlement') x
     FROM jsonb_array_elements(dep_event.body->'cash_legs') l WHERE l->>'account' LIKE 'unsettled_%') q;
   SELECT jsonb_agg(l ORDER BY l->>'account',l->>'currency') INTO actual FROM jsonb_array_elements(legs) l;
   IF actual IS DISTINCT FROM expected THEN RETURN 'settlement_shape'; END IF;
   RETURN NULL;
 END IF;
 IF event_type='fx' THEN
   IF n<>4 OR nc<>2 OR accounts<>ARRAY['fx_clearing','settled_cash'] THEN RETURN 'fx_shape'; END IF;
   IF EXISTS(SELECT 1 FROM jsonb_array_elements(legs) l WHERE l->>'basis'<>'settlement') THEN RETURN 'fx_shape'; END IF;
   IF (SELECT min((l->>'amount')::numeric)*max((l->>'amount')::numeric)>=0 FROM jsonb_array_elements(legs) l WHERE l->>'account'='settled_cash') THEN RETURN 'fx_shape'; END IF;
   RETURN NULL;
 END IF;
 counterparty:=CASE event_type WHEN 'fee' THEN 'fee_expense' WHEN 'tax' THEN 'tax_expense' WHEN 'deposit' THEN 'external_flow' WHEN 'withdrawal' THEN 'external_flow' WHEN 'dividend' THEN 'dividend_income' END;
 direction:=CASE WHEN event_type IN ('deposit','dividend') THEN 1 ELSE -1 END;
 IF n<>2 OR nc<>1 OR NOT accounts @> ARRAY['settled_cash',counterparty] THEN RETURN 'cash_event_shape'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(legs) l WHERE l->>'basis'<>'settlement') THEN RETURN 'cash_event_shape'; END IF;
 SELECT (l->>'amount')::numeric INTO amount FROM jsonb_array_elements(legs) l WHERE l->>'account'='settled_cash';
 IF amount*direction<=0 THEN RETURN 'cash_event_direction'; END IF;
 RETURN NULL;
END $$;
CREATE FUNCTION qh.ledger_validate_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE b jsonb:=NEW.body; s jsonb; sign integer;
BEGIN
 PERFORM qh.ledger_keys(b,ARRAY['schema_version','environment','account_ref','event_id','sequence','recorded_at','effective_at',
 'bundle_id','kind','source_kind','source_event_key','source_revision','correction_of','submission_hash','submission','cash_legs','position_deltas']);
 s:=qh.ledger_submission(b->'submission');
 IF s IS DISTINCT FROM b->'submission' OR qh.ledger_int(b->'schema_version',1,1)<>1
 OR qh.ledger_int(b->'sequence',1,2147483647)<>NEW.sequence OR b->'environment'<>'"synthetic"'::jsonb
 OR (b->>'account_ref') IS DISTINCT FROM (s->>'account_ref') OR b->>'event_id' IS DISTINCT FROM qh.ledger_event_id(NEW.account_ref,NEW.sequence)
 OR b->>'submission_hash' IS DISTINCT FROM qh.ledger_hash('SyntheticLedgerSubmission',s)
 OR b->>'recorded_at'<>qh.ledger_instant(b->'recorded_at') OR b->>'effective_at'<>qh.ledger_instant(b->'effective_at')
 OR b->>'bundle_id' IS DISTINCT FROM replace(qh.ledger_event_id(NEW.account_ref,NEW.bundle_cursor),'ledger:','bundle:')
 OR b->'kind' NOT IN ('"reversal"'::jsonb,'"replacement"'::jsonb)
 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 IF b->>'kind'='reversal' THEN
   IF b->'source_kind' IS DISTINCT FROM '"internal-reversal"'::jsonb OR b->'source_event_key' IS DISTINCT FROM b->'event_id' OR qh.ledger_int(b->'source_revision',1,1)<>1 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 ELSE
   IF b->'source_kind' IS DISTINCT FROM s->'source_kind' OR b->'source_event_key' IS DISTINCT FROM s->'source_event_key' OR b->'source_revision' IS DISTINCT FROM s->'source_revision' THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 END IF;
 sign:=CASE WHEN b->>'kind'='reversal' THEN -1 ELSE 1 END;
 IF b->'cash_legs'<>qh.ledger_signed(s->'cash_legs',sign) OR b->'position_deltas'<>qh.ledger_signed(s->'position_deltas',sign)
 THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 IF b->'correction_of'<>'null'::jsonb THEN PERFORM qh.ledger_identifier(b->'correction_of'); END IF;
 IF octet_length(qh.ledger_canonical(jsonb_build_object('schema_name','LedgerEventBody','schema_version',1,'environment','synthetic','payload',b)))>65536 THEN RAISE EXCEPTION 'ledger_limit'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ledger_validate_event BEFORE INSERT ON qh.ledger_event FOR EACH ROW EXECUTE FUNCTION qh.ledger_validate_event();

CREATE FUNCTION qh.ledger_commit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a text:=NEW.account_ref; c integer; d qh.ledger_decision; e qh.ledger_event; r qh.ledger_event;
 journal jsonb; ids text[]; prior integer; n integer; p qh.ledger_projection; canonical_time text; current_stream qh.ledger_stream;
BEGIN
 IF TG_TABLE_NAME='ledger_stream' THEN
   SELECT max(cursor) INTO c FROM qh.ledger_decision WHERE account_ref=a;
   SELECT * INTO STRICT current_stream FROM qh.ledger_stream WHERE account_ref=a;
   IF current_stream.cursor IS DISTINCT FROM coalesce(c,0) OR current_stream.recorded_at IS DISTINCT FROM (SELECT recorded_at FROM qh.ledger_decision WHERE account_ref=a AND cursor=c)
   THEN RAISE EXCEPTION 'ledger_commit_stream'; END IF;
   RETURN NULL;
 END IF;
 c:=CASE WHEN TG_TABLE_NAME='ledger_decision' THEN (to_jsonb(NEW)->>'cursor')::integer WHEN TG_TABLE_NAME='ledger_journal' THEN (SELECT bundle_cursor FROM qh.ledger_event WHERE event_id=to_jsonb(NEW)->>'event_id') ELSE (to_jsonb(NEW)->>'bundle_cursor')::integer END;
 SELECT * INTO STRICT d FROM qh.ledger_decision WHERE account_ref=a AND cursor=c;
 IF d.submission<>qh.ledger_submission(d.submission) THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 SELECT array_agg(event_id ORDER BY sequence) INTO ids FROM qh.ledger_event WHERE account_ref=a AND bundle_cursor=c;
 IF coalesce(ids,'{}')<>d.event_ids THEN RAISE EXCEPTION 'ledger_commit_events'; END IF;
 n:=cardinality(d.event_ids); prior:=coalesce((SELECT max(cursor) FROM qh.ledger_decision WHERE account_ref=a AND cursor<c),0);
 IF c-prior<>greatest(n,1) OR EXISTS(SELECT 1 FROM qh.ledger_decision WHERE account_ref=a AND cursor<c AND recorded_at>d.recorded_at)
 THEN RAISE EXCEPTION 'ledger_commit_sequence'; END IF;
 canonical_time:=qh.ledger_instant(to_jsonb(to_char(d.recorded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')));
 FOR e IN SELECT * FROM qh.ledger_event WHERE account_ref=a AND bundle_cursor=c ORDER BY sequence LOOP
   IF e.body->>'recorded_at'<>canonical_time OR e.sequence<=prior OR e.sequence>c THEN RAISE EXCEPTION 'ledger_commit_bundle'; END IF;
   SELECT coalesce(jsonb_agg(jsonb_build_object('account',account,'currency',currency,'amount',qh.ledger_decimal(to_jsonb(trim_scale(amount)::text)),'basis',basis) ORDER BY ordinal),'[]') INTO journal FROM qh.ledger_journal WHERE event_id=e.event_id;
   IF journal<>e.body->'cash_legs' OR EXISTS(SELECT 1 FROM qh.ledger_journal WHERE event_id=e.event_id GROUP BY currency HAVING sum(amount)<>0) THEN RAISE EXCEPTION 'ledger_commit_journal'; END IF;
   IF e.kind='reversal' THEN
     SELECT * INTO STRICT r FROM qh.ledger_event WHERE account_ref=a AND event_id=e.correction_of;
     IF n<>2 OR e.sequence<>c-1 OR r.kind<>'replacement' OR r.sequence>=e.sequence
     OR e.body->'submission'<>r.body->'submission' OR e.body->'cash_legs'<>qh.ledger_signed(r.body->'cash_legs',-1)
     OR e.body->'position_deltas'<>qh.ledger_signed(r.body->'position_deltas',-1)
     THEN RAISE EXCEPTION 'ledger_commit_reversal'; END IF;
   ELSE
     IF e.sequence<>c OR e.body->'submission'<>d.submission OR e.body->>'effective_at'<>d.submission->>'effective_at'
     OR e.body->'correction_of'<>d.submission->'correction_of' THEN RAISE EXCEPTION 'ledger_commit_replacement'; END IF;
     IF n=2 AND NOT EXISTS(SELECT 1 FROM qh.ledger_event x WHERE x.account_ref=a AND x.sequence=c-1 AND x.kind='reversal'
       AND x.correction_of=e.correction_of AND x.body->>'effective_at'=e.body->>'effective_at') THEN RAISE EXCEPTION 'ledger_commit_reversal'; END IF;
     IF e.source_revision=1 AND (n<>1 OR e.correction_of IS NOT NULL) THEN RAISE EXCEPTION 'ledger_commit_revision'; END IF;
     IF e.source_revision>1 THEN
       SELECT * INTO STRICT r FROM qh.ledger_event WHERE account_ref=a AND event_id=e.correction_of;
       IF n<>2 OR r.source_kind<>e.source_kind OR r.source_event_key<>e.source_event_key OR r.source_revision+1<>e.source_revision
       OR (d.submission->>'predecessor_revision')::integer<>r.source_revision
       OR r.body->'submission'->>'event_type'<>e.body->'submission'->>'event_type'
       OR r.body->>'effective_at'>canonical_time
       OR (d.submission->>'revision_mode'='retroactive' AND e.body->>'effective_at'<>r.body->>'effective_at')
       OR (d.submission->>'revision_mode'='prospective' AND e.body->>'effective_at'<=greatest(canonical_time,r.body->>'effective_at'))
       OR d.submission->>'revision_mode' NOT IN ('retroactive','prospective')
       THEN RAISE EXCEPTION 'ledger_commit_revision'; END IF;
     END IF;
   END IF;
 END LOOP;
 SELECT * INTO STRICT p FROM qh.ledger_projection WHERE account_ref=a AND projection_id=d.projection_id;
 IF p.cursor<>c OR NOT EXISTS(SELECT 1 FROM qh.ledger_outbox WHERE account_ref=a AND cursor=c AND projection_id=p.projection_id AND payload_hash=p.payload_hash)
 OR NOT EXISTS(SELECT 1 FROM qh.ledger_delivery WHERE message_id=p.projection_id)
 THEN RAISE EXCEPTION 'ledger_commit_outbox'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ledger_commit_stream AFTER INSERT OR UPDATE ON qh.ledger_stream DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.ledger_commit_guard();
CREATE CONSTRAINT TRIGGER ledger_commit_decision AFTER INSERT ON qh.ledger_decision DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.ledger_commit_guard();
CREATE CONSTRAINT TRIGGER ledger_commit_event AFTER INSERT ON qh.ledger_event DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.ledger_commit_guard();

CREATE CONSTRAINT TRIGGER ledger_commit_journal AFTER INSERT ON qh.ledger_journal DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.ledger_commit_guard();

CREATE FUNCTION qh.ledger_append(input text, recorded_input text, reprocess boolean DEFAULT false, fault text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE s jsonb; a text; h text; now_text text; stream qh.ledger_stream; previous qh.ledger_event;
 same qh.ledger_decision; accepted qh.ledger_decision; reason text; rev integer; n integer; ending integer;
 ids text[]:='{}'; sources jsonb[]; kinds text[]; corrections text[]; i integer; seq integer; b jsonb; source jsonb;
 eid text; bundle text; pid text; supersedes text; p jsonb; ph text;
BEGIN
 IF reprocess IS NULL OR (fault IS NOT NULL AND fault NOT IN ('events','projection','outbox')) THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 s:=qh.ledger_submission(qh.ledger_wire(input)); a:=s->>'account_ref'; h:=qh.ledger_hash('SyntheticLedgerSubmission',s);
 now_text:=qh.ledger_instant(to_jsonb(recorded_input));
 IF octet_length(qh.ledger_canonical(jsonb_build_object('schema_name','SyntheticLedgerSubmission','schema_version',1,'environment','synthetic','payload',s)))>65536 THEN RAISE EXCEPTION 'ledger_limit'; END IF;
 INSERT INTO qh.ledger_stream(account_ref) VALUES(a) ON CONFLICT DO NOTHING;
 SELECT * INTO STRICT stream FROM qh.ledger_stream WHERE account_ref=a FOR UPDATE;
 SELECT * INTO same FROM qh.ledger_decision WHERE account_ref=a AND submission->>'source_kind'=s->>'source_kind'
 AND submission->>'source_event_key'=s->>'source_event_key' AND submission->>'source_revision'=s->>'source_revision'
 AND submission_hash=h ORDER BY cursor DESC LIMIT 1;
 IF FOUND AND (same.status='accepted' OR NOT reprocess) THEN
   RETURN jsonb_build_object('status','duplicate','reason',same.reason,'cursor',same.cursor,'event_ids',to_jsonb(same.event_ids),'submission_hash',h,'projection_id',same.projection_id);
 END IF;
 IF stream.recorded_at>now_text::timestamptz THEN RAISE EXCEPTION 'ledger_clock'; END IF;
 SELECT * INTO accepted FROM qh.ledger_decision WHERE account_ref=a AND submission->>'source_kind'=s->>'source_kind'
 AND submission->>'source_event_key'=s->>'source_event_key' AND submission->>'source_revision'=s->>'source_revision' AND status='accepted' LIMIT 1;
 SELECT * INTO previous FROM qh.ledger_event WHERE account_ref=a AND kind='replacement' AND source_kind=s->>'source_kind'
 AND source_event_key=s->>'source_event_key' ORDER BY sequence DESC LIMIT 1;
 rev:=(s->>'source_revision')::integer;
 IF accepted.cursor IS NOT NULL THEN reason:='source_collision';
 ELSIF rev=1 THEN
   IF previous.sequence IS NOT NULL OR s->'predecessor_revision'<>'null'::jsonb OR s->'correction_of'<>'null'::jsonb OR s->>'revision_mode'<>'original'
   THEN reason:='revision_link_invalid'; END IF;
 ELSE
   IF previous.sequence IS NULL OR rev<>previous.source_revision+1 THEN reason:='predecessor_missing';
   ELSIF (s->>'predecessor_revision')::integer IS DISTINCT FROM previous.source_revision OR s->>'correction_of' IS DISTINCT FROM previous.event_id
     OR s->>'event_type'<>previous.body->'submission'->>'event_type' THEN reason:='revision_link_invalid';
   ELSIF previous.body->>'effective_at'>now_text THEN reason:='uneffective_revision';
   ELSIF s->>'revision_mode'='retroactive' THEN
     IF s->>'effective_at'<>previous.body->>'effective_at' THEN reason:='effective_move_unsupported'; END IF;
   ELSIF s->>'revision_mode'='prospective' THEN
     IF s->>'effective_at'<=greatest(previous.body->>'effective_at',now_text) THEN reason:='prospective_time_invalid';
     ELSIF s->>'event_type'='settlement' AND s->'dependency_refs' IS DISTINCT FROM previous.body->'submission'->'dependency_refs'
       THEN reason:='prospective_dependency_change_unsupported'; END IF;
   ELSE reason:='revision_mode_unsupported'; END IF;
 END IF;
 IF reason IS NULL THEN reason:=qh.ledger_semantics(a,s,previous.body); END IF;
 n:=CASE WHEN reason IS NOT NULL OR rev=1 THEN 1 ELSE 2 END;
 IF stream.cursor::bigint+n>2147483647 OR (SELECT count(*)+n>4096 FROM qh.ledger_event WHERE account_ref=a)
 OR (SELECT count(*)>=4096 FROM qh.ledger_decision WHERE account_ref=a) THEN RAISE EXCEPTION 'ledger_limit'; END IF;
 ending:=stream.cursor+n;
 bundle:=replace(qh.ledger_event_id(a,ending),'ledger:','bundle:');
 SELECT projection_id INTO supersedes FROM qh.ledger_projection WHERE account_ref=a ORDER BY cursor DESC LIMIT 1;
 pid:=qh.ledger_projection_id(a,ending,now_text,now_text,'as_known',supersedes);
 IF reason IS NULL THEN
   IF n=2 THEN sources:=ARRAY[previous.body->'submission',s]; kinds:=ARRAY['reversal','replacement']; corrections:=ARRAY[previous.event_id,s->>'correction_of'];
   ELSE sources:=ARRAY[s]; kinds:=ARRAY['replacement']; corrections:=ARRAY[s->>'correction_of']; END IF;
   FOR i IN 1..n LOOP ids:=array_append(ids,qh.ledger_event_id(a,stream.cursor+i)); END LOOP;
 END IF;
 INSERT INTO qh.ledger_decision VALUES(a,ending,now_text::timestamptz,s,h,CASE WHEN reason IS NULL THEN 'accepted' ELSE 'quarantined' END,reason,ids,pid);
 IF reason IS NULL THEN
   FOR i IN 1..n LOOP
     source:=sources[i]; seq:=stream.cursor+i; eid:=ids[i];
     b:=jsonb_build_object('schema_version',1,'environment','synthetic','account_ref',a,'event_id',eid,'sequence',seq,
       'recorded_at',now_text,'effective_at',s->>'effective_at','bundle_id',bundle,'kind',kinds[i],
       'source_kind',CASE WHEN kinds[i]='reversal' THEN 'internal-reversal' ELSE source->>'source_kind' END,
       'source_event_key',CASE WHEN kinds[i]='reversal' THEN eid ELSE source->>'source_event_key' END,
       'source_revision',CASE WHEN kinds[i]='reversal' THEN 1 ELSE (source->>'source_revision')::integer END,'correction_of',corrections[i],
       'submission_hash',qh.ledger_hash('SyntheticLedgerSubmission',source),'submission',source,
       'cash_legs',qh.ledger_signed(source->'cash_legs',CASE WHEN kinds[i]='reversal' THEN -1 ELSE 1 END),
       'position_deltas',qh.ledger_signed(source->'position_deltas',CASE WHEN kinds[i]='reversal' THEN -1 ELSE 1 END));
     INSERT INTO qh.ledger_event(account_ref,sequence,event_id,bundle_cursor,body,payload_hash) VALUES(a,seq,eid,ending,b,qh.ledger_hash('LedgerEventBody',b));
     INSERT INTO qh.ledger_journal SELECT a,eid,ord::integer,l->>'account',l->>'currency',(l->>'amount')::numeric,l->>'basis'
     FROM jsonb_array_elements(b->'cash_legs') WITH ORDINALITY x(l,ord);
   END LOOP;
 END IF;
 IF fault='events' THEN RAISE EXCEPTION 'ledger_injected'; END IF;
 UPDATE qh.ledger_stream SET cursor=ending,recorded_at=now_text::timestamptz WHERE account_ref=a;
 p:=qh.ledger_replay(a,now_text,now_text,ending,'as_known','synthetic-ledger-v1',supersedes); ph:=qh.ledger_hash('LedgerProjection',p);
 INSERT INTO qh.ledger_projection VALUES(a,ending,pid,supersedes,p,ph);
 IF fault='projection' THEN RAISE EXCEPTION 'ledger_injected'; END IF;
 INSERT INTO qh.ledger_outbox VALUES(pid,a,ending,pid,ph);
 INSERT INTO qh.ledger_delivery(message_id) VALUES(pid);
 IF fault='outbox' THEN RAISE EXCEPTION 'ledger_injected'; END IF;
 RETURN jsonb_build_object('status',CASE WHEN reason IS NULL THEN 'accepted' ELSE 'quarantined' END,'reason',reason,'cursor',ending,'event_ids',to_jsonb(ids),'submission_hash',h,'projection_id',pid);
END $$;

CREATE FUNCTION qh.ledger_consume(c text,m text,h text,fail_before_commit boolean DEFAULT false) RETURNS text LANGUAGE plpgsql AS $$
DECLARE message qh.ledger_outbox; old_hash text;
BEGIN
 PERFORM qh.ledger_identifier(to_jsonb(c)); PERFORM qh.ledger_identifier(to_jsonb(m));
 IF h IS NULL OR h !~ '^[0-9a-f]{64}$' OR fail_before_commit IS NULL THEN RAISE EXCEPTION 'ledger_contract'; END IF;
 SELECT * INTO STRICT message FROM qh.ledger_outbox WHERE message_id=m;
 -- Serializes a consumer's work in this account and its inbox insert, including first delivery.
 PERFORM 1 FROM qh.ledger_stream WHERE account_ref=message.account_ref FOR UPDATE;
 SELECT payload_hash INTO old_hash FROM qh.ledger_inbox WHERE consumer=c AND message_id=m;
 IF h<>message.payload_hash OR (old_hash IS NOT NULL AND old_hash<>h) THEN
   INSERT INTO qh.ledger_inbox_collision(consumer,message_id,supplied_hash) VALUES(c,m,h); RETURN 'collision';
 END IF;
 IF old_hash IS NOT NULL THEN RETURN 'duplicate'; END IF;
 INSERT INTO qh.ledger_inbox VALUES(c,m,h);
 INSERT INTO qh.ledger_workstate VALUES(c,message.account_ref,message.cursor)
 ON CONFLICT(consumer,account_ref) DO UPDATE SET cursor=greatest(qh.ledger_workstate.cursor,excluded.cursor);
 IF fail_before_commit THEN RAISE EXCEPTION 'ledger_injected'; END IF;
 RETURN 'accepted';
END $$;
CREATE FUNCTION qh.ledger_ack(m text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 PERFORM qh.ledger_identifier(to_jsonb(m));
 UPDATE qh.ledger_delivery SET acknowledged=true WHERE message_id=m;
 IF NOT FOUND THEN RAISE EXCEPTION 'ledger_contract'; END IF;
END $$;
REVOKE ALL ON FUNCTION qh.ledger_append(text,text,boolean,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION qh.ledger_consume(text,text,text,boolean) FROM PUBLIC;

CREATE FUNCTION qh.ledger_inbox_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c text:=NEW.consumer; a text; expected_cursor integer; actual_cursor integer;
BEGIN
 IF TG_TABLE_NAME='ledger_inbox' THEN
   SELECT account_ref INTO STRICT a FROM qh.ledger_outbox WHERE message_id=NEW.message_id AND payload_hash=NEW.payload_hash;
 ELSE a:=NEW.account_ref; END IF;
 SELECT max(o.cursor) INTO expected_cursor FROM qh.ledger_inbox i JOIN qh.ledger_outbox o USING(message_id)
 WHERE i.consumer=c AND o.account_ref=a;
 SELECT cursor INTO actual_cursor FROM qh.ledger_workstate WHERE consumer=c AND account_ref=a;
 IF actual_cursor IS DISTINCT FROM expected_cursor THEN RAISE EXCEPTION 'ledger_commit_inbox'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ledger_commit_inbox AFTER INSERT ON qh.ledger_inbox DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.ledger_inbox_guard();
CREATE CONSTRAINT TRIGGER ledger_commit_workstate AFTER INSERT OR UPDATE ON qh.ledger_workstate DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION qh.ledger_inbox_guard();
