"""P28-03 synthetic immutable payload storage; no authority restoration.

Quotas count canonical payload bytes, not physical disk or financial reservations.
Every facade reads the database; no restored dictionary is an authoritative cache.
"""
from collections.abc import MutableMapping
from hashlib import sha256
import json
import subprocess

from .postgres_ledger import PostgresLedger, LedgerStorageError, _text
from quantharbor.domain.ledger import account, choice, hash_record, integer
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import canonical_bytes, parse_payload

_NAMES = {'report': 'Report', 'snapshot': 'PortfolioSnapshot', 'experiment': 'ExperimentResult',
          'target': ('TargetPlan', 'OrderCandidate', 'TargetBuildResult')}
_FIELDS = ('namespace', 'kind', 'artifact_id', 'environment', 'account_ref', 'created_at',
           'record_hash', 'wire_sha256', 'payload', 'predecessor', 'comparison_key', 'plan_id')


def _deny(reason='product_artifact_corrupt'):
    raise LedgerStorageError(reason)


def _metadata(namespace, raw, plan=None):
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise ContractError()
    wire = parse_payload(raw)
    if canonical_bytes(wire) != raw or wire.schema_version != 1 or wire.environment != 'synthetic':
        raise ContractError()
    obj = wire.payload
    expected = _NAMES[namespace]
    if type(obj).__name__ not in ((expected,) if type(expected) is str else expected):
        raise ContractError()
    # The parser constructs the closed exact DTO types; also guard their identity.
    from quantharbor.domain.reporting import Report
    from quantharbor.domain.valuation import PortfolioSnapshot
    from quantharbor.domain.research import ExperimentResult
    from quantharbor.domain.target import TargetPlan, OrderCandidate, TargetBuildResult
    allowed = {'report': (Report,), 'snapshot': (PortfolioSnapshot,), 'experiment': (ExperimentResult,),
               'target': (TargetPlan, OrderCandidate, TargetBuildResult)}
    if type(obj) not in allowed[namespace] or wire.schema_name != type(obj).__name__:
        raise ContractError()
    predecessor = comparison = plan_id = None
    if namespace == 'target':
        kind = {TargetPlan: 'plan', OrderCandidate: 'candidate', TargetBuildResult: 'result'}[type(obj)]
        key = getattr(obj, {'plan': 'plan_id', 'candidate': 'candidate_id', 'result': 'result_id'}[kind])
        body = obj.body
        if kind == 'plan':
            plan = obj
            predecessor = body.request.predecessor_plan_ref
            predecessor = predecessor.id if predecessor is not None else None
        if type(plan) is not TargetPlan:
            raise ContractError()
        if kind != 'plan':
            from quantharbor.domain.target import ref
            if body.plan_ref != ref('plan', plan.plan_id, plan):
                raise ContractError()
        plan_id = plan.plan_id
        created = plan.body.request.evaluated_at
        acct, env = body.account_ref, body.environment
    elif namespace == 'experiment':
        key, kind = obj.result_id, 'ExperimentResult'
        acct, env, created = obj.manifest.account_ref, obj.environment, obj.manifest.created_at
        predecessor = obj.manifest.predecessor
        comparison = sha256(json.dumps(obj.manifest.comparison_key, separators=(',', ':')).encode()).hexdigest()
    else:
        kind = expected
        key = getattr(obj, 'report_id' if namespace == 'report' else 'snapshot_id')
        acct, env, created = obj.account_ref, obj.environment, obj.created_at
        predecessor = getattr(obj, 'supersedes_report_id' if namespace == 'report' else 'supersedes_snapshot_id')
    account(acct)
    if env != 'synthetic':
        raise ContractError()
    for value in (key, acct, predecessor, comparison, plan_id):
        if value is not None and (type(value) is not str or not value.isascii() or not 1 <= len(value) <= 128):
            raise ContractError()
    row = dict(zip(_FIELDS, (namespace, kind, key, env, acct, created, hash_record(obj),
                           sha256(raw).hexdigest(), raw.hex(), predecessor, comparison, plan_id)))
    return obj, row


def _target_groups(records):
    from .synthetic_target import _check_artifacts
    from quantharbor.domain.target import TargetPlan, OrderCandidate, TargetBuildResult
    from quantharbor.ports.target import TargetArtifacts
    objects = {k: parse_payload(v).payload for k, v in records.items()}
    covered = set()
    for key, plan in objects.items():
        if type(plan) is not TargetPlan:
            continue
        candidates = sorted((o for o in objects.values() if type(o) is OrderCandidate and o.body.plan_ref.id == plan.plan_id),
                            key=lambda o: o.body.order_index)
        results = [o for o in objects.values() if type(o) is TargetBuildResult and o.body.plan_ref.id == plan.plan_id]
        if len(results) != 1:
            raise ContractError()
        artifacts = TargetArtifacts(plan, tuple(candidates), results[0])
        keys, encoded, *_ = _check_artifacts(artifacts)
        covered.update(keys)
        yield artifacts, tuple(zip(keys, encoded))
    if covered != set(records):
        raise ContractError()


def _validate_lineage(namespace, records):
    # A temporary validation view, discarded before returning. Never a storage cache.
    if namespace == 'target':
        from .synthetic_target import SyntheticTargetRepository
        repo = SyntheticTargetRepository()
        repo._records = dict(records)
        for artifacts, _ in _target_groups(records):
            repo.append(artifacts)
        return
    if namespace == 'report':
        from .synthetic_reporting import SyntheticReportRepository
        repo, field = SyntheticReportRepository(), '_reports'
    elif namespace == 'snapshot':
        from .synthetic_valuation import SyntheticSnapshotRepository
        repo, field = SyntheticSnapshotRepository(), '_snapshots'
    else:
        from .synthetic_research import SyntheticExperimentRepository
        repo, field = SyntheticExperimentRepository(), '_results'
    view = dict(records)
    setattr(repo, field, view)
    for key, value in records.items():
        del view[key]
        repo.append(parse_payload(value[1]).payload)


def list_records(records, namespace, environment, account_ref):
    choice(environment, ('synthetic',))
    account(account_ref)
    if type(records) is ProductArtifacts:
        return records.list_records(environment=environment, account_ref=account_ref)
    result = []
    raw_records = dict(records)
    plans = {k[1]: parse_payload(v).payload for k, v in raw_records.items() if namespace == 'target' and k[0] == 'plan'}
    for value in raw_records.values():
        raw = value if namespace == 'target' else value[1]
        obj = parse_payload(raw).payload
        plan = plans.get(obj.body.plan_ref.id) if namespace == 'target' and hasattr(obj.body, 'plan_ref') else None
        obj, row = _metadata(namespace, raw, plan)
        if (row['environment'], row['account_ref']) == (environment, account_ref):
            result.append((row['created_at'], row['kind'], row['artifact_id'], obj))
    return tuple(x[3] for x in sorted(result, key=lambda x: x[:3]))


class ProductArtifacts(MutableMapping):
    """Private fixed namespace mapping used only by the four exact repositories."""
    def __init__(self, database, namespace, *, capacity=128):
        integer(capacity, 1, 128)
        if type(database) is not PostgresLedger or namespace not in _NAMES:
            raise ContractError()
        self._database, self._namespace, self._capacity = database, namespace, capacity
        self._generation = database._product_generation

    @classmethod
    def product_synthetic(cls, database, namespace, *, capacity=128):
        backend = ProductArtifacts(database, namespace, capacity=capacity)
        with database._product_gate:
            backend._check()
            backend._ensure_schema()
        return backend

    def _check(self):
        db = self._database
        from .product_database import ProductDatabase
        p = db._product_database
        if (type(db) is not PostgresLedger or type(p) is not ProductDatabase or not db._ready
                or not p.active or p.lock is None or p.fd is None or db._compose is None
                or self._generation is None or self._generation is not db._product_generation):
            _deny('product_artifact_database_unavailable')

    def _ensure_schema(self):
        from .product_schema import ensure_schema
        ensure_schema(self._database)

    def _load(self):
        self._check()
        sql = "SELECT coalesce(json_agg(r),'[]'::json) FROM (SELECT namespace,kind,artifact_id,environment,account_ref,created_at,record_hash,wire_sha256,encode(payload,'hex') AS payload,predecessor,comparison_key,plan_id FROM qh_product.artifacts WHERE namespace=" + _text(self._namespace) + ' ORDER BY created_at,kind,artifact_id LIMIT 129) r;'
        try:
            rows = json.loads(self._database._query(sql))
            if type(rows) is not list or len(rows) > 128:
                raise ContractError()
            plans = {}
            if self._namespace == 'target':
                for row in rows:
                    if row['kind'] == 'plan':
                        obj, _ = _metadata('target', bytes.fromhex(row['payload']))
                        plans[obj.plan_id] = obj
            records = {}
            for row in rows:
                if set(row) != set(_FIELDS) or row['namespace'] != self._namespace:
                    raise ContractError()
                raw = bytes.fromhex(row['payload'])
                obj, expected = _metadata(self._namespace, raw, plans.get(row['plan_id']))
                if row != expected:
                    raise ContractError()
                key = (row['kind'], row['artifact_id']) if self._namespace == 'target' else row['artifact_id']
                if key in records:
                    raise ContractError()
                records[key] = raw if self._namespace == 'target' else (hash_record(obj), raw)
            _validate_lineage(self._namespace, records)
            return records
        except (ContractError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            _deny()

    def __getitem__(self, key):
        with self._database._product_gate:
            return self._load()[key]

    def __iter__(self):
        with self._database._product_gate:
            return iter(self._load())

    def __len__(self):
        with self._database._product_gate:
            return len(self._load())

    def __delitem__(self, key):
        raise ContractError()

    def __setitem__(self, key, value):
        self.update(((key, value),))

    def values(self):
        with self._database._product_gate:
            return tuple(self._load().values())

    def update(self, other=(), **kwargs):
        if kwargs:
            raise ContractError()
        with self._database._product_gate:
            current = self._load()
            proposed = dict(other)
            combined = current | proposed
            for key, value in proposed.items():
                if key in current and current[key] != value:
                    raise ContractError()
            _validate_lineage(self._namespace, combined)
            plans = {}
            if self._namespace == 'target':
                # Reject incomplete writes even when each individual DTO is valid.
                for artifacts, _ in _target_groups(proposed):
                    plans[artifacts.plan.plan_id] = artifacts.plan
            rows = []
            for key, value in proposed.items():
                raw = value if self._namespace == 'target' else value[1]
                obj = parse_payload(raw).payload
                plan = plans.get(obj.body.plan_ref.id) if self._namespace == 'target' and hasattr(obj.body, 'plan_ref') else None
                obj, row = _metadata(self._namespace, raw, plan)
                expected_key = (row['kind'], row['artifact_id']) if self._namespace == 'target' else row['artifact_id']
                if key != expected_key or (self._namespace != 'target' and value[0] != row['record_hash']):
                    raise ContractError()
                rows.append(row)
            if not rows:
                return
            # Plan precedes candidates/result in the one SQL transaction.
            rows.sort(key=lambda r: (r['kind'] != 'plan', r['kind'], r['artifact_id']))
            sql = "BEGIN; SET LOCAL statement_timeout='15s'; SET LOCAL lock_timeout='10s';\nSELECT qh_product.append_artifacts(" + _text(json.dumps(rows, separators=(',', ':'))) + '::jsonb,' + str(self._capacity) + ");\nCOMMIT;\nSELECT 'product_artifacts_committed';"
            self._commit(sql, proposed)

    def _commit(self, sql, proposed):
        db = self._database
        try:
            response = subprocess.run(db._psql(), input=sql.encode(), capture_output=True, env=db._env, timeout=60)
        except FileNotFoundError:
            _deny('product_artifact_write_rolled_back')
        except (OSError, subprocess.TimeoutExpired):
            response = None
        if response is not None and response.returncode == 0 and response.stdout.strip().endswith(b'product_artifacts_committed'):
            return
        server_error = response is not None and response.returncode != 0 and b'ERROR:' in response.stderr
        # An ERROR may belong to the confirmation SELECT after a successful COMMIT.
        # Confirm immutable rows before classifying it as a rolled-back write.
        try:
            stored = self._load()
            if all(stored.get(key) == value for key, value in proposed.items()):
                return
        except LedgerStorageError:
            _deny('product_artifact_commit_unknown')
        if server_error:
            _deny('product_artifact_write_rolled_back')
        _deny('product_artifact_commit_unknown')

    def list_records(self, *, environment, account_ref):
        with self._database._product_gate:
            return list_records(self._load(), self._namespace, environment, account_ref)
