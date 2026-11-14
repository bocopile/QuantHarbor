"""Explicit shared product schema registry. Import performs no I/O."""
from hashlib import sha256
import json
from .postgres_ledger import ROOT, LedgerStorageError, _text

V1_SHA = 'e82d7893e8a374ff8ff8409b5e2f003c80a11bc69620982a5abaf1e0bca96ee3'
V2_SHA = 'dabe5c871395c13be34b73bb8ae982c1b59aa850c39e0d3ae012d3d349a3da60'

# pg_get_constraintdef output for the fixed product PostgreSQL image. Counting
# constraints alone permits a weakened CHECK to hide the one authoritative book.
_CHECKS = {
    'schema_migrations': {
        'schema_migrations_version_check': 'CHECK ((version = ANY (ARRAY[1, 2])))',
        'schema_migrations_checksum_check': "CHECK ((checksum ~ '^[0-9a-f]{64}$'::text))",
    },
    'ai_state': {
        'ai_state_book_check': 'CHECK ((book = 1))',
        'ai_state_codec_check': 'CHECK ((codec = 1))',
        'ai_state_record_count_check': 'CHECK (((record_count >= 0) AND (record_count <= 128)))',
        'ai_state_revision_check': "CHECK (((revision >= 1) AND (revision <= '9223372036854775806'::bigint)))",
        'ai_state_checkpoint_check': 'CHECK (((octet_length(checkpoint) >= 1) AND (octet_length(checkpoint) <= 33554432)))',
        'ai_state_checkpoint_hash_check': "CHECK ((checkpoint_hash ~ '^[0-9a-f]{64}$'::text))",
        'ai_state_operation_id_check': "CHECK ((operation_id ~ '^[0-9a-f]{32}$'::text))",
        'ai_state_input_digest_check': "CHECK ((input_digest ~ '^[0-9a-f]{64}$'::text))",
        'ai_state_opcode_check': "CHECK ((opcode = ANY (ARRAY['append'::text, 'reserve'::text, 'dispatch'::text, 'cancel'::text, 'settle'::text, 'query_charge'::text, 'query_outcome'::text, 'finish_processed'::text, 'review_processed'::text, 'restart_reconcile'::text])))",
        'ai_state_check': "CHECK ((encode(sha256(checkpoint), 'hex'::text) = checkpoint_hash))",
    },
    'ai_processed': {
        'ai_processed_record_hash_check': "CHECK ((record_hash ~ '^[0-9a-f]{64}$'::text))",
        'ai_processed_kind_check': "CHECK ((kind = ANY (ARRAY['result'::text, 'review'::text])))",
        'ai_processed_check': "CHECK ((((kind = 'result'::text) AND (transition = 'finish_processed'::text)) OR ((kind = 'review'::text) AND (transition = 'review_processed'::text))))",
        'ai_processed_revision_check': "CHECK (((revision >= 1) AND (revision <= '9223372036854775806'::bigint)))",
    },
}


def _deny():
    raise LedgerStorageError('product_artifact_schema_invalid')


def ensure_schema(database, *, _execute=None):
    body = (ROOT / 'migrations/product/0001_artifacts.sql').read_bytes()
    checksum = sha256(body).hexdigest()
    if checksum != V1_SHA:
        _deny()
    function_body = _text(body.decode().split('$fn$')[1])
    second = (ROOT / 'migrations/product/0002_ai.sql').read_bytes()
    checksum2 = sha256(second).hexdigest()
    if checksum2 != V2_SHA:
        _deny()
    sql = """BEGIN;
SET LOCAL statement_timeout='15s'; SET LOCAL lock_timeout='10s';
SELECT pg_advisory_xact_lock(5130028) IS NOT NULL;
SELECT NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='qh_product') AS install_artifacts \\gset
\\if :install_artifacts
""" + body.decode() + "\nINSERT INTO qh_product.schema_migrations VALUES(1,'" + checksum + "');\n\\endif\n"
    sql += """DO $guard$ BEGIN
IF (SELECT count(*) FROM qh_product.schema_migrations) NOT IN (1,2) OR EXISTS(SELECT 1 FROM qh_product.schema_migrations WHERE version NOT IN (1,2)) OR NOT EXISTS(
SELECT 1 FROM qh_product.schema_migrations WHERE version=1 AND checksum='""" + checksum + """') THEN
RAISE EXCEPTION 'product_artifact_migration_mismatch'; END IF;
IF to_regprocedure('qh_product.append_artifacts(jsonb,integer)') IS NULL
OR to_regclass('qh_product.artifacts_listing') IS NULL OR to_regclass('qh_product.experiment_one_child') IS NULL THEN
RAISE EXCEPTION 'product_artifact_structure'; END IF;
IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang
WHERE p.oid=to_regprocedure('qh_product.append_artifacts(jsonb,integer)')
AND p.prosrc=""" + function_body + """ AND l.lanname='plpgsql'
AND p.prokind='f' AND p.prorettype='void'::regtype AND NOT p.proretset
AND NOT p.prosecdef AND NOT p.proisstrict AND p.provolatile='v' AND p.proparallel='u'
AND p.proconfig IS NULL AND p.proacl IS NULL AND NOT p.proleakproof AND p.provariadic=0 AND p.pronargdefaults=0 AND p.proargmodes IS NULL AND pg_get_userbyid(p.proowner)=current_user) THEN
RAISE EXCEPTION 'product_artifact_structure'; END IF;
IF (SELECT array_agg(attname::text || ':' || format_type(atttypid,atttypmod) || ':' || attnotnull::text ORDER BY attnum)
FROM pg_attribute WHERE attrelid='qh_product.artifacts'::regclass AND attnum>0 AND NOT attisdropped)
IS DISTINCT FROM ARRAY['namespace:text:true','kind:text:true','artifact_id:text:true','environment:text:true',
'account_ref:text:true','created_at:text:true','record_hash:text:true','wire_sha256:text:true','payload:bytea:true',
'predecessor:text:false','comparison_key:text:false','plan_id:text:false'] THEN
RAISE EXCEPTION 'product_artifact_structure'; END IF;
IF (SELECT count(*) FROM pg_constraint WHERE conrelid='qh_product.artifacts'::regclass AND contype='c' AND convalidated)<>14
OR NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='qh_product.artifacts'::regclass AND contype='p' AND conkey=ARRAY[1,2,3]::smallint[])
OR NOT EXISTS(SELECT 1 FROM pg_index WHERE indexrelid='qh_product.artifacts_listing'::regclass AND indisvalid AND indkey::text='1 4 5 6 2 3')
OR NOT EXISTS(SELECT 1 FROM pg_index WHERE indexrelid='qh_product.experiment_one_child'::regclass AND indisvalid AND indisunique AND indkey::text='10' AND indpred IS NOT NULL) THEN
RAISE EXCEPTION 'product_artifact_structure'; END IF;
END $guard$;
SELECT namespace,kind,artifact_id,environment,account_ref,created_at,record_hash,wire_sha256,payload,
predecessor,comparison_key,plan_id FROM qh_product.artifacts LIMIT 0;

"""
    sql += """DO $registry$ BEGIN
IF (SELECT array_agg(attname::text || ':' || format_type(atttypid,atttypmod) || ':' || attnotnull::text ORDER BY attnum)
FROM pg_attribute WHERE attrelid='qh_product.schema_migrations'::regclass AND attnum>0 AND NOT attisdropped)
IS DISTINCT FROM ARRAY['version:integer:true','checksum:text:true']
OR (SELECT count(*) FROM pg_constraint WHERE conrelid='qh_product.schema_migrations'::regclass AND contype='c' AND convalidated)<>2
OR NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='qh_product.schema_migrations'::regclass AND contype='p' AND conkey=ARRAY[1]::smallint[])
THEN RAISE EXCEPTION 'product_registry_structure'; END IF;
END $registry$;
"""
    sql += """SELECT NOT EXISTS(SELECT 1 FROM qh_product.schema_migrations WHERE version=2) AS upgrade_ai \\gset
\\if :upgrade_ai
""" + second.decode() + "\nINSERT INTO qh_product.schema_migrations VALUES(2,'" + checksum2 + "');\n\\endif\n"
    sql += "DO $v2$ BEGIN IF (SELECT count(*) FROM qh_product.schema_migrations)<>2 OR NOT EXISTS(SELECT 1 FROM qh_product.schema_migrations WHERE version=2 AND checksum='" + checksum2 + "') THEN RAISE EXCEPTION 'product_ai_migration_mismatch'; END IF; END $v2$;\n"
    for name, signature, tag, result in (
            ('ai_metadata', '', 'meta', 'jsonb'),
            ('ai_chunk', 'bigint,text,integer', 'chunk', 'jsonb'),
            ('ai_publish', 'bigint,text,text,text,bytea,integer,jsonb', 'publish', 'void')):
        body2 = second.decode().split('$' + tag + '$')[1]
        sql += "DO $function$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang WHERE p.oid=to_regprocedure('qh_product." + name + "(" + signature + ")') AND p.prosrc=" + _text(body2) + " AND l.lanname='plpgsql' AND p.prokind='f' AND p.prorettype='" + result + "'::regtype AND NOT p.proretset AND NOT p.prosecdef AND NOT p.proisstrict AND p.provolatile='v' AND p.proparallel='u' AND p.proconfig IS NULL AND p.proacl IS NULL AND NOT p.proleakproof AND p.provariadic=0 AND p.pronargdefaults=0 AND p.proargmodes IS NULL AND pg_get_userbyid(p.proowner)=current_user) THEN RAISE EXCEPTION 'product_ai_function'; END IF; END $function$;\n"
    for table, columns, checks in (
        ('ai_state', ['book:integer:true','codec:integer:true','record_count:integer:true','revision:bigint:true','checkpoint:bytea:true','checkpoint_hash:text:true','operation_id:text:true','input_digest:text:true','opcode:text:true'],10),
        ('ai_processed', ['record_hash:text:true','kind:text:true','transition:text:true','revision:bigint:true'],4)):
        expected = 'ARRAY[' + ','.join(_text(x) for x in columns) + ']'
        sql += "DO $columns$ BEGIN IF (SELECT array_agg(attname::text || ':' || format_type(atttypid,atttypmod) || ':' || attnotnull::text ORDER BY attnum) FROM pg_attribute WHERE attrelid='qh_product." + table + "'::regclass AND attnum>0 AND NOT attisdropped) IS DISTINCT FROM " + expected + " OR (SELECT count(*) FROM pg_constraint WHERE conrelid='qh_product." + table + "'::regclass AND contype='c' AND convalidated)<>" + str(checks) + " OR NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='qh_product." + table + "'::regclass AND contype='p' AND conkey=ARRAY[1]::smallint[]) THEN RAISE EXCEPTION 'product_ai_structure'; END IF; END $columns$;\n"
    for table, definitions in _CHECKS.items():
        expected = _text(json.dumps(definitions, sort_keys=True, separators=(',', ':'))) + '::jsonb'
        sql += "DO $checks$ BEGIN IF (SELECT jsonb_object_agg(conname,pg_get_constraintdef(oid)) FROM pg_constraint WHERE conrelid='qh_product." + table + "'::regclass AND contype='c') IS DISTINCT FROM " + expected + " THEN RAISE EXCEPTION 'product_ai_check_definition'; END IF; END $checks$;\n"
    sql += """DO $registry2$ BEGIN
IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='qh_product.schema_migrations'::regclass
AND conname='schema_migrations_version_check' AND contype='c' AND convalidated
AND pg_get_constraintdef(oid)='CHECK ((version = ANY (ARRAY[1, 2])))') THEN
RAISE EXCEPTION 'product_registry_version_check'; END IF;
IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='qh_product' AND c.relkind='r' AND (c.relrowsecurity OR c.relforcerowsecurity
OR c.relpersistence<>'p' OR pg_get_userbyid(c.relowner)<>current_user))
OR EXISTS(SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='qh_product' AND NOT t.tgisinternal)
OR EXISTS(SELECT 1 FROM pg_inherits WHERE
inhrelid IN ('qh_product.schema_migrations'::regclass,'qh_product.artifacts'::regclass,'qh_product.ai_state'::regclass,'qh_product.ai_processed'::regclass)
OR inhparent IN ('qh_product.schema_migrations'::regclass,'qh_product.artifacts'::regclass,'qh_product.ai_state'::regclass,'qh_product.ai_processed'::regclass)) THEN
RAISE EXCEPTION 'product_registry_owner_or_trigger'; END IF;
END $registry2$;
"""
    sql += "COMMIT;"
    try:
        (database._query if _execute is None else _execute)(sql)
    except LedgerStorageError:
        _deny()
