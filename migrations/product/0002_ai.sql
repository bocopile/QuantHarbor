-- The common registry validates all v1 objects before entering this migration.
DO $upgrade$ BEGIN
IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='qh_product.schema_migrations'::regclass
 AND conname='schema_migrations_version_check' AND contype='c' AND convalidated
 AND pg_get_constraintdef(oid)='CHECK ((version = 1))') THEN
 RAISE EXCEPTION 'product_ai_version_check'; END IF;
END $upgrade$;
ALTER TABLE qh_product.schema_migrations DROP CONSTRAINT schema_migrations_version_check;
ALTER TABLE qh_product.schema_migrations ADD CONSTRAINT schema_migrations_version_check CHECK (version IN (1,2));
CREATE TABLE qh_product.ai_state (
 book integer PRIMARY KEY CHECK (book=1),
 codec integer NOT NULL CHECK (codec=1),
 record_count integer NOT NULL CHECK (record_count BETWEEN 0 AND 128),
 revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 9223372036854775806),
 checkpoint bytea NOT NULL CHECK (octet_length(checkpoint) BETWEEN 1 AND 33554432),
 checkpoint_hash text NOT NULL CHECK (checkpoint_hash ~ '^[0-9a-f]{64}$'),
 operation_id text NOT NULL CHECK (operation_id ~ '^[0-9a-f]{32}$'),
 input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
 opcode text NOT NULL CHECK (opcode IN ('append','reserve','dispatch','cancel','settle','query_charge','query_outcome','finish_processed','review_processed','restart_reconcile')),
 CHECK (encode(sha256(checkpoint),'hex')=checkpoint_hash)
);
CREATE TABLE qh_product.ai_processed (
 record_hash text PRIMARY KEY CHECK (record_hash ~ '^[0-9a-f]{64}$'),
 kind text NOT NULL CHECK (kind IN ('result','review')),
 transition text NOT NULL CHECK ((kind='result' AND transition='finish_processed') OR (kind='review' AND transition='review_processed')),
 revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 9223372036854775806)
);
CREATE FUNCTION qh_product.ai_metadata() RETURNS jsonb LANGUAGE plpgsql AS $meta$
DECLARE s qh_product.ai_state%ROWTYPE; m jsonb;
BEGIN
 IF (SELECT count(*) FROM qh_product.ai_processed)>128 THEN RAISE EXCEPTION 'ai_marker_capacity'; END IF;
 SELECT * INTO s FROM qh_product.ai_state WHERE book=1;
 IF NOT FOUND THEN
  IF EXISTS(SELECT 1 FROM qh_product.ai_processed) THEN RAISE EXCEPTION 'ai_orphan_marker'; END IF;
  RETURN jsonb_build_object('codec',1,'record_count',0,'chunk_count',0,'marker_count',0,'revision',0,'length',0,'hash',NULL,'operation_id',NULL,'input_digest',NULL,'opcode',NULL,'markers','[]'::jsonb);
 END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_array(record_hash,kind,transition,revision) ORDER BY record_hash),'[]'::jsonb) INTO m FROM qh_product.ai_processed;
 RETURN jsonb_build_object('codec',s.codec,'record_count',s.record_count,'chunk_count',(octet_length(s.checkpoint)+32767)/32768,'marker_count',jsonb_array_length(m),'revision',s.revision,'length',octet_length(s.checkpoint),'hash',s.checkpoint_hash,
 'operation_id',s.operation_id,'input_digest',s.input_digest,'opcode',s.opcode,'markers',m);
END $meta$;
CREATE FUNCTION qh_product.ai_chunk(wanted_revision bigint, wanted_hash text, chunk_index integer) RETURNS jsonb LANGUAGE plpgsql AS $chunk$
DECLARE s qh_product.ai_state%ROWTYPE; b bytea;
BEGIN
 IF chunk_index<0 OR chunk_index>=1024 THEN RAISE EXCEPTION 'ai_chunk_index'; END IF;
 SELECT * INTO STRICT s FROM qh_product.ai_state WHERE book=1 AND revision=wanted_revision AND checkpoint_hash=wanted_hash;
 b=substring(s.checkpoint FROM chunk_index*32768+1 FOR 32768);
 IF octet_length(b)=0 THEN RAISE EXCEPTION 'ai_chunk_empty'; END IF;
 RETURN jsonb_build_array(s.revision,s.checkpoint_hash,chunk_index,encode(b,'hex'));
END $chunk$;
CREATE FUNCTION qh_product.ai_publish(expected_revision bigint, op text, op_id text, digest text, payload bytea, records_count integer, markers jsonb) RETURNS void LANGUAGE plpgsql AS $publish$
DECLARE current_revision bigint; m jsonb;
BEGIN
 PERFORM pg_advisory_xact_lock(5130029);
 SELECT revision INTO current_revision FROM qh_product.ai_state WHERE book=1 FOR UPDATE;
 IF coalesce(current_revision,0)<>expected_revision THEN RAISE EXCEPTION 'ai_stale_revision'; END IF;
 -- Runtime proof issuance is enforced by the private Python phase bridge.
 IF op IS NULL OR op NOT IN ('append','reserve','dispatch','cancel','settle','query_charge','query_outcome','finish_processed','review_processed','restart_reconcile')
 OR records_count NOT BETWEEN 0 AND 128 OR octet_length(payload) NOT BETWEEN 1 AND 33554432
 OR markers IS NULL OR jsonb_typeof(markers)<>'array' OR octet_length(markers::text)>32768
 OR jsonb_array_length(markers)>records_count THEN RAISE EXCEPTION 'ai_transition_invalid'; END IF;
 IF EXISTS(SELECT 1 FROM qh_product.ai_processed p WHERE NOT EXISTS(
 SELECT 1 FROM jsonb_array_elements(markers) x WHERE x=jsonb_build_array(p.record_hash,p.kind,p.transition,p.revision)))
 THEN RAISE EXCEPTION 'ai_marker_immutable'; END IF;
 IF (SELECT count(DISTINCT x->>0) FROM jsonb_array_elements(markers) x)<>jsonb_array_length(markers)
 THEN RAISE EXCEPTION 'ai_marker_duplicate'; END IF;
 FOR m IN SELECT value FROM jsonb_array_elements(markers) LOOP
  IF jsonb_typeof(m)<>'array' OR jsonb_array_length(m)<>4
  OR jsonb_typeof(m->0)<>'string' OR (m->>0)!~'^[0-9a-f]{64}$'
  OR jsonb_typeof(m->1)<>'string' OR jsonb_typeof(m->2)<>'string'
  OR jsonb_typeof(m->3)<>'number' OR (m->>3)!~'^[1-9][0-9]{0,18}$'
  THEN RAISE EXCEPTION 'ai_marker_shape'; END IF;
  IF NOT EXISTS(SELECT 1 FROM qh_product.ai_processed WHERE record_hash=m->>0) THEN
   IF op NOT IN ('finish_processed','review_processed') OR m->>2<>op OR (m->>3)::bigint<>expected_revision+1
   OR NOT ((m->>1='result' AND op='finish_processed') OR (m->>1='review' AND op='review_processed'))
   THEN RAISE EXCEPTION 'ai_marker_proof_transition'; END IF;
   INSERT INTO qh_product.ai_processed VALUES(m->>0,m->>1,m->>2,(m->>3)::bigint);
  END IF;
 END LOOP;
 INSERT INTO qh_product.ai_state VALUES(1,1,records_count,expected_revision+1,payload,encode(sha256(payload),'hex'),op_id,digest,op)
 ON CONFLICT(book) DO UPDATE SET record_count=EXCLUDED.record_count,revision=EXCLUDED.revision,checkpoint=EXCLUDED.checkpoint,
 checkpoint_hash=EXCLUDED.checkpoint_hash,operation_id=EXCLUDED.operation_id,input_digest=EXCLUDED.input_digest,opcode=EXCLUDED.opcode;
END $publish$;
