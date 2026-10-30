"""새 UUID 프로젝트만 사용하는 PostgreSQL 합성 어댑터.

생성자는 DSN/기존 DB/credential/SQL을 받지 않는다. 공개 경제 API는 고정 함수만
호출하며 각 append/consume는 단일 psql session transaction이다. 관리자/운영 어댑터가 아니다.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import time
from threading import RLock
import uuid

from quantharbor.domain.ledger import (AppendResult, ContractError, SyntheticLedgerSubmission,
    account, digest, exact, identifier, instant, integer, choice)
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = (ROOT / 'migrations/0001_synthetic_foundation.sql', ROOT / 'migrations/0002_synthetic_ledger.sql')


class LedgerStorageError(RuntimeError):
    def __init__(self, reason='synthetic_database_failure'):
        self.reason = reason
        super().__init__(reason)


def _text(value):
    """SQL literal은 UTF-8 hex만 포함한다. 따옴표/식별자 보간 경로가 없다."""
    if type(value) is not str:
        raise ContractError()
    return "convert_from(decode('" + value.encode('utf-8').hex() + "','hex'),'UTF8')"


def _append_sql(submission, recorded_at, reprocess=False, fault=None):
    exact(submission, SyntheticLedgerSubmission)
    if type(reprocess) is not bool or fault not in (None, 'events', 'projection', 'outbox'):
        raise ContractError()
    wire = json.loads(canonical_bytes(CanonicalPayload('SyntheticLedgerSubmission', 1, 'synthetic', submission)))
    payload = json.dumps(wire['payload'], separators=(',', ':'), ensure_ascii=False)
    return ('SELECT qh.ledger_append(' + _text(payload) + ',' + _text(instant(recorded_at)) + ',' +
            ('true' if reprocess else 'false') + ',' + ('NULL' if fault is None else _text(fault)) + ');')


class PostgresLedger:
    """명시 context manager 진입 때만 새 합성 DB를 생성하고 자신의 프로젝트만 정리한다."""
    def __init__(self):
        self._project = 'qh-ledger-' + uuid.uuid4().hex
        self._env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'DOCKER_CONFIG') if k in os.environ}
        self._env['COMPOSE_DISABLE_ENV_FILE'] = '1'
        self._compose = None
        self._ready = False
        self.cleanup = 'not_started'
        self.migration_checksums = {}
        self._product_database = None
        self._product_gate = RLock()
        self._product_generation = None

    @classmethod
    def product_synthetic(cls, runtime_root, *, binding_id):
        """기존 empty/private0700 외부 root의 합성 제품 DB. I/O는 with 진입 때만 한다."""
        from .product_database import ProductDatabase
        database = PostgresLedger()
        database._product_database = ProductDatabase(runtime_root, binding_id)
        return database

    def _run(self, args, *, data=None, timeout=60, expected=0, error_marker=None):
        try:
            result = subprocess.run(args, input=data, capture_output=True, env=self._env, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise LedgerStorageError('command_start_or_timeout') from None
        if result.returncode != expected:
            raise LedgerStorageError('command_exit_mismatch')
        if error_marker is not None and error_marker not in result.stderr:
            raise LedgerStorageError('expected_failure_reason_mismatch')
        return result.stdout

    def _psql(self, database='qh_synthetic'):
        # database is an internal runner-only fixed allowlist, never a runtime option.
        if self._compose is None or database not in ('qh_synthetic', 'qh_ledger_restore'):
            raise LedgerStorageError('synthetic_database_unavailable')
        return self._compose + ['exec', '-T', 'db', 'psql', '-X', '-q', '-A', '-t',
                                '-v', 'ON_ERROR_STOP=1', '-U', 'qh_synthetic', '-d', database]

    def _query(self, sql, *, database='qh_synthetic', expected=0, error_marker=None):
        if self._product_database is not None:
            with self._product_gate:
                return self._query_direct(sql, database=database, expected=expected, error_marker=error_marker)
        return self._query_direct(sql, database=database, expected=expected, error_marker=error_marker)

    def _query_direct(self, sql, *, database, expected, error_marker):
        return self._run(self._psql(database), data=sql.encode('utf-8'), expected=expected, error_marker=error_marker).decode('utf-8').strip()

    def _transaction(self, sql):
        if self._product_database is not None:
            with self._product_gate:
                return self._transaction_ready(sql)
        return self._transaction_ready(sql)

    def _transaction_ready(self, sql):
        if not self._ready:
            raise LedgerStorageError('synthetic_database_unavailable')
        return self._query("BEGIN; SET LOCAL statement_timeout='15s'; SET LOCAL lock_timeout='10s';\n" + sql + '\nCOMMIT;')

    def _migration_script(self, version, checksum=None):
        path = MIGRATIONS[version - 1]
        actual = sha256(path.read_bytes()).hexdigest()
        checksum = actual if checksum is None else checksum
        digest(checksum)
        body = path.read_text(encoding='utf-8')
        prerequisite = '' if version == 1 else f"IF NOT EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version=1 AND checksum='{self.migration_checksums[1]}') THEN RAISE EXCEPTION 'migration_order'; END IF;"
        return f"""BEGIN;
SELECT pg_advisory_xact_lock(5130001) IS NOT NULL;
CREATE SCHEMA IF NOT EXISTS qh;
CREATE TABLE IF NOT EXISTS qh.schema_migrations(version integer PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now());
DO $guard$ BEGIN
{prerequisite}
IF EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version={version} AND checksum<>'{checksum}') THEN RAISE EXCEPTION 'migration_checksum_mismatch'; END IF;
END $guard$;
SELECT NOT EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version={version}) AS apply_ledger \\gset
\\if :apply_ledger
{body}
INSERT INTO qh.schema_migrations(version,checksum) VALUES({version},'{checksum}');
\\endif
COMMIT;
"""

    def __enter__(self):
        if self._product_database is not None:
            with self._product_gate:
                result = self._product_database.open(self)
                self._product_generation = object()
                return result
        try:
            context = self._run(['docker', 'context', 'show']).decode().strip()
            metadata = json.loads(self._run(['docker', 'context', 'inspect', context]))
            if not metadata[0]['Endpoints']['docker']['Host'].startswith('unix://'):
                raise LedgerStorageError('nonlocal_docker_context')
            self._compose = ['docker', '--context', context, 'compose', '--env-file', '/dev/null',
                             '-p', self._project, '-f', str(ROOT / 'containers/compose.synthetic.yaml')]
            self._run(self._compose + ['config', '--quiet'])
            self._run(self._compose + ['up', '-d', '--no-build', '--pull', 'never', 'db'])
            for _ in range(30):
                try:
                    # The image starts a temporary server during init, then restarts.
                    # Only PID 1 postgres denotes the final exec'ed server.
                    if self._run(self._compose + ['exec', '-T', 'db', 'cat', '/proc/1/comm'], timeout=5).strip() != b'postgres':
                        raise LedgerStorageError('synthetic_database_initializing')
                    self._run(self._compose + ['exec', '-T', 'db', 'pg_isready', '-U', 'qh_synthetic', '-d', 'qh_synthetic'], timeout=5)
                    break
                except LedgerStorageError:
                    time.sleep(0.2)
            else:
                raise LedgerStorageError('synthetic_database_not_ready')
            if self._query('SHOW server_version;').split()[0] != '18.6':
                raise LedgerStorageError('postgres_version_mismatch')
            for version, path in enumerate(MIGRATIONS, 1):
                self.migration_checksums[version] = sha256(path.read_bytes()).hexdigest()
                self._query(self._migration_script(version))
            self._ready = True
            return self
        except (ValueError, KeyError, IndexError, UnicodeError):
            self.close()
            raise LedgerStorageError('invalid_local_metadata') from None
        except BaseException:
            self.close()
            raise

    def close(self):
        if self._product_database is not None:
            with self._product_gate:
                self._product_generation = None
                return self._product_database.close(self)
        self._ready = False
        if self._compose is not None:
            try:
                self._run(self._compose + ['down', '--volumes', '--remove-orphans'], timeout=30)
            except LedgerStorageError:
                self.cleanup = 'failed'
                raise
            self._compose = None
            self.cleanup = 'own_project_removed'

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def append(self, submission, *, recorded_at, reprocess=False):
        raw = self._transaction(_append_sql(submission, recorded_at, reprocess))
        try:
            result = json.loads(raw)
            result['event_ids'] = tuple(result['event_ids'])
            return AppendResult(**result)
        except (ValueError, KeyError, TypeError):
            raise LedgerStorageError('invalid_append_result') from None

    def replay(self, account_ref, *, as_of, knowledge_cutoff, cursor=None, mode='as_known',
               reducer_version='synthetic-ledger-v1', supersedes_projection_id=None):
        account(account_ref)
        choice(mode, ('as_known', 'restated'))
        choice(reducer_version, ('synthetic-ledger-v1',))
        if cursor is not None:
            integer(cursor, 0)
        if supersedes_projection_id is not None:
            identifier(supersedes_projection_id)
        sql = 'SELECT qh.ledger_replay(' + ','.join((_text(account_ref), _text(instant(as_of)),
            _text(instant(knowledge_cutoff)), 'NULL' if cursor is None else str(cursor), _text(mode),
            _text(reducer_version), 'NULL' if supersedes_projection_id is None else _text(supersedes_projection_id))) + ');'
        raw = self._transaction(sql)
        try:
            wrapper = dict(schema_name='LedgerProjection', schema_version=1, environment='synthetic', payload=json.loads(raw))
            return parse_payload(json.dumps(wrapper)).payload
        except (ValueError, TypeError):
            raise LedgerStorageError('invalid_projection_result') from None

    def consume(self, consumer, message_id, payload_hash):
        identifier(consumer)
        identifier(message_id)
        digest(payload_hash)
        return self._transaction('SELECT qh.ledger_consume(' + ','.join(map(_text, (consumer, message_id, payload_hash))) + ');')

    def acknowledge(self, message_id):
        identifier(message_id)
        self._transaction('SELECT qh.ledger_ack(' + _text(message_id) + ');')
