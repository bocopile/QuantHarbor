"""P28-03 focused mocked units; Docker/actual PostgreSQL are never executed."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from quantharbor.adapters.postgres_ledger import PostgresLedger, LedgerStorageError, MIGRATIONS
from quantharbor.adapters import product_database as p
from quantharbor.adapters.execution_uow import ExecutionUnitOfWork


class Docker:
    """Command-boundary double: retains identity/data and models migration guards."""
    def __init__(self):
        self.calls = []
        self.volume = None
        self.container = None
        self.schema = {}
        self.data = b'synthetic durable sentinel'
        self.image = {'Id': 'sha256:' + 'a' * 64, 'RepoDigests': [p.IMAGE],
                      'Os': 'linux', 'Architecture': 'arm64',
                      'Config': {'Env': ['PATH=/usr/bin', 'PG_MAJOR=18'],
                                 'Entrypoint': ['docker-entrypoint.sh']}}
        self.remote = False
        self.fail_create = False
        self.fail_start = False
        self.fail_stop = False
        self.unsafe_create = False
        self.bad_role = False
        self.bad_schema = False
        self.bad_version = False

    def run(self, args, *, input=None, capture_output=None, env=None, timeout=None):
        self.calls.append((list(args), input))
        raw = b''
        def result(value):
            return json.dumps(value).encode()
        if args == ['docker', 'context', 'show']:
            raw = b'local'
        elif args[:3] == ['docker', 'context', 'inspect']:
            raw = result([{'Endpoints': {'docker': {'Host': 'tcp://remote:2375' if self.remote else 'unix:///synthetic.sock'}}}])
        else:
            cmd = args[3:]
            if cmd[0] == 'info':
                raw = result('daemon-synthetic')
            elif cmd[:2] == ['image', 'inspect']:
                raw = result([self.image])
            elif cmd[:2] == ['volume', 'ls']:
                raw = b'' if self.volume is None else self.volume['Name'].encode()
            elif cmd[:2] == ['volume', 'create']:
                labels = {}
                for i, value in enumerate(cmd):
                    if value == '--label':
                        key, val = cmd[i + 1].split('=', 1)
                        labels[key] = val
                self.volume = {'Name': cmd[-1], 'Driver': 'local', 'Scope': 'local',
                               'Labels': labels, 'Options': None, 'CreatedAt': 'synthetic-time-1'}
                raw = cmd[-1].encode()
            elif cmd[:2] == ['volume', 'inspect']:
                raw = result([self.volume])
            elif cmd[:2] == ['container', 'inspect']:
                raw = result([self.container])
            elif cmd[0] == 'ps':
                raw = b'' if self.container is None else self.container['Id'].encode()
            elif cmd[0] == 'start':
                if self.fail_start:
                    return subprocess.CompletedProcess(args, 1, b'', b'synthetic failure')
                self.container['State']['Running'] = True
            elif cmd[0] == 'stop':
                if self.fail_stop:
                    return subprocess.CompletedProcess(args, 1, b'', b'synthetic failure')
                self.container['State']['Running'] = False
            elif cmd[0] == 'compose':
                tail = cmd[7:]
                if tail == ['config', '--quiet']:
                    pass
                elif tail[:1] == ['create']:
                    if self.fail_create:
                        return subprocess.CompletedProcess(args, 1, b'', b'synthetic failure')
                    labels = {key: env[val] for key, val in (
                        ('io.quantharbor.product.token', 'QH_PRODUCT_TOKEN'),
                        ('io.quantharbor.product.binding', 'QH_PRODUCT_BINDING'),
                        ('io.quantharbor.product.root', 'QH_PRODUCT_ROOT'))}
                    labels.update({'io.quantharbor.product.synthetic': 'true',
                                   'com.docker.compose.project': cmd[4], 'com.docker.compose.service': 'db'})
                    self.container = {'Id': 'c' * 64, 'Image': self.image['Id'],
                        'Config': {'Image': p.IMAGE, 'User': '999:999', 'Cmd': p.COMMAND[:],
                                   'Entrypoint': self.image['Config']['Entrypoint'][:],
                                   'Env': self.image['Config']['Env'][:] + [k + '=' + v for k, v in p.ENVIRONMENT.items()],
                                   'Labels': labels},
                        'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True, 'CapDrop': ['ALL'],
                            'SecurityOpt': ['no-new-privileges:true'], 'Privileged': self.unsafe_create,
                            'AutoRemove': False,
                            'PublishAllPorts': False, 'PortBindings': {}, 'Binds': [],
                            'IpcMode': 'private', 'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
                            'PidsLimit': 128, 'Memory': 268435456, 'NanoCpus': 1000000000,
                            'Tmpfs': dict(p.TMPFS),
                            'LogConfig': {'Type': 'json-file', 'Config': {'max-size': '1m', 'max-file': '3'}}},
                        'Mounts': [{'Type': 'volume', 'Name': self.volume['Name'],
                                    'Destination': '/var/lib/postgresql', 'RW': True}],
                        'NetworkSettings': {'Networks': {'none': {}}}, 'State': {'Running': False}}
                elif tail[:1] == ['ps']:
                    raw = self.container['Id'].encode()
                elif tail[-2:] == ['cat', '/proc/1/comm']:
                    raw = b'postgres\n'
                elif 'pg_isready' in tail:
                    pass
                elif 'psql' in tail:
                    sql = input.decode()
                    if sql == 'SHOW server_version;':
                        raw = b'18.5' if self.bad_version else b'18.6'
                    elif 'json_build_array(current_user' in sql:
                        raw = result(['wrong' if self.bad_role else 'qh_synthetic', 'qh_synthetic', True])
                    elif 'json_object_agg' in sql:
                        raw = result({} if self.bad_schema else self.schema)
                    elif sql.startswith('SELECT count(*) FROM pg_roles'):
                        raw = b'1'
                    elif sql.startswith('BEGIN;') and 'apply_product' in sql:
                        for version in ('1', '2', '3'):
                            if 'WHERE version=' + version + ' AND checksum<>' in sql:
                                if version in self.schema and self.schema[version] != p.SCHEMA[version]:
                                    return subprocess.CompletedProcess(args, 1, b'', b'migration_checksum_mismatch')
                                if any(str(i) not in self.schema for i in range(1, int(version))):
                                    raise AssertionError('out of order')
                                self.schema[version] = p.SCHEMA[version]
                    else:
                        raise AssertionError('unexpected SQL')
                else:
                    raise AssertionError(tail)
            else:
                raise AssertionError(cmd)
        return subprocess.CompletedProcess(args, 0, raw, b'')

    def mutations(self, since=0):
        return [args for args, _ in self.calls[since:] if
                (len(args) > 3 and args[3] in ('start', 'stop'))
                or 'create' in args or 'up' in args or 'down' in args]


class ProductDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='qh-product-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.docker = Docker()
        self.run_patch = patch('quantharbor.adapters.postgres_ledger.subprocess.run', side_effect=self.docker.run)
        self.run_patch.start()
        self.addCleanup(self.run_patch.stop)

    def db(self, root=None, binding='synthetic:product-test'):
        return PostgresLedger.product_synthetic(self.root if root is None else root, binding_id=binding)

    def seed(self):
        with self.db() as db:
            self.assertTrue(db._ready)
        self.assertEqual(db.cleanup, 'own_product_stopped_data_preserved')
        return json.loads((self.root / 'manifest.json').read_text())

    def reject(self, root=None, binding='synthetic:product-test'):
        start = len(self.docker.calls)
        with self.assertRaises(LedgerStorageError):
            with self.db(root, binding):
                self.fail('invalid context opened')
        self.assertEqual(self.docker.mutations(start), [])

    def test_factory_is_exact_type_lazy_and_no_secret_environment(self):
        with patch.dict(os.environ, {'PGPASSWORD': 'synthetic-secret', 'DOCKER_HOST': 'tcp://remote'}):
            db = self.db()
        self.assertIs(type(db), PostgresLedger)
        self.assertFalse(db._ready)
        self.assertIsNone(db._compose)
        self.assertEqual(self.docker.calls, [])
        with db:
            self.assertNotIn('PGPASSWORD', db._env)
            self.assertNotIn('DOCKER_HOST', db._env)
            self.assertIs(type(ExecutionUnitOfWork(db, 'synthetic-account:test')), ExecutionUnitOfWork)
        for kwargs in ({'dsn': 'x'}, {'sql': 'x'}, {'credentials': {}}):
            with self.assertRaises(TypeError):
                PostgresLedger.product_synthetic(self.root, binding_id='synthetic:test', **kwargs)

    def test_stop_and_restart_preserve_same_volume_container_and_sentinel(self):
        manifest = self.seed()
        before = deepcopy(self.docker.volume), self.docker.data, self.docker.container['Id']
        with self.db() as db:
            self.assertTrue(self.docker.container['State']['Running'])
            self.assertEqual(db.migration_checksums, {int(k): v for k, v in p.SCHEMA.items()})
        self.assertEqual(before, (self.docker.volume, self.docker.data, self.docker.container['Id']))
        self.assertEqual(manifest, json.loads((self.root / 'manifest.json').read_text()))
        self.assertFalse(self.docker.container['State']['Running'])
        for args, _ in self.docker.calls:
            self.assertFalse(set(args) & {'down', '--volumes', 'rm', 'prune', 'pull', 'build', '--privileged'})
        self.assertEqual(sum('create' in a and 'volume' in a for a, _ in self.docker.calls), 1)
        for name in ('marker.json', 'manifest.json', 'writer.lock'):
            self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), 0o600)

    def test_product_open_generation_changes_only_on_success_and_close_invalidates(self):
        db = self.db()
        self.assertIsNone(db._product_generation)
        with db:
            first = db._product_generation
            self.assertIsNotNone(first)
            with self.assertRaises(LedgerStorageError):
                db.__enter__()
            self.assertIs(db._product_generation, first)
        self.assertIsNone(db._product_generation)
        with db:
            self.assertIsNot(db._product_generation, first)
            self.assertIsNotNone(db._product_generation)
        self.assertIsNone(db._product_generation)

    def test_legacy_constructor_uuid_and_down_volumes_unchanged(self):
        db = PostgresLedger()
        self.assertNotEqual(db._project, PostgresLedger()._project)
        self.assertTrue(db._project.startswith('qh-ledger-'))
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if args == ['docker', 'context', 'show']:
                return b'local'
            if args[:3] == ['docker', 'context', 'inspect']:
                return b'[{"Endpoints":{"docker":{"Host":"unix:///synthetic.sock"}}}]'
            if args[-2:] == ['cat', '/proc/1/comm']:
                return b'postgres'
            return b''
        with patch.object(db, '_run', side_effect=run), patch.object(db, '_query', return_value='18.6'):
            with db:
                self.assertTrue(db._ready)
        self.assertEqual(db.cleanup, 'own_project_removed')
        self.assertEqual(calls[-1][-3:], ['down', '--volumes', '--remove-orphans'])
        self.assertEqual(len(MIGRATIONS), 2)
        self.assertIn(str(p.ROOT / 'containers/compose.synthetic.yaml'), calls[-1])

    def test_relative_repository_and_parent_roots_rejected(self):
        for root in ('relative', p.ROOT, p.ROOT / 'src', p.ROOT.parent, '/'):
            with self.subTest(root=str(root)):
                self.reject(root)

    def test_unknown_contents_and_invalid_binding_rejected_without_reading(self):
        (self.root / 'unknown').write_bytes(b'unknown synthetic bytes')
        self.reject()
        self.assertEqual(self.docker.calls, [])
        for binding in ('', '../other', 'x' * 129, None, 1):
            with self.subTest(binding=binding):
                self.reject(binding=binding)

    def test_permissions_and_owner_rejected(self):
        self.root.chmod(0o755)
        self.reject()
        self.root.chmod(0o700)
        with patch.object(p.os, 'getuid', return_value=os.getuid() + 1):
            self.reject()
        self.seed()
        (self.root / 'manifest.json').chmod(0o644)
        self.reject()

    def test_symlink_root_and_metadata_and_hardlink_rejected(self):
        link = self.root / 'link'
        link.symlink_to(self.root, target_is_directory=True)
        self.reject(link)
        link.unlink()
        self.seed()
        target = self.root / 'manifest.json'
        original = target.read_bytes()
        target.unlink()
        outside = self.root.parent / (self.root.name + '-target')
        outside.write_bytes(original)
        outside.chmod(0o600)
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        target.symlink_to(outside)
        self.reject()
        target.unlink()
        os.link(outside, target)
        self.reject()

    def test_each_corrupt_metadata_and_size_limit_rejected(self):
        self.seed()
        for name in ('marker.json', 'manifest.json', 'writer.lock'):
            target = self.root / name
            original = target.read_bytes()
            for raw in (b'{broken', b'{}', b'x' * (p.LIMIT + 1), b'{"key":1,"key":2}', b'[' * 1500 + b']' * 1500):
                with self.subTest(name=name, length=len(raw)):
                    target.write_bytes(raw)
                    self.reject()
            target.write_bytes(original)

    def test_binding_and_root_inode_replacement_rejected(self):
        self.seed()
        self.reject(binding='synthetic:other')
        target = self.root / 'marker.json'
        marker = json.loads(target.read_text())
        marker['root']['inode'] += 1
        target.write_text(json.dumps(marker))
        self.reject()

    def test_flock_contention_and_failed_entry_release(self):
        with self.db() as first:
            self.reject()
            with self.assertRaises(LedgerStorageError):
                first.__enter__()
            self.assertTrue(first._ready)
        with self.db() as db:
            self.assertTrue(db._ready)

    def test_failed_initialization_never_cleans_unknown_resources(self):
        self.docker.fail_create = True
        with self.assertRaises(LedgerStorageError):
            with self.db():
                pass
        self.assertIsNotNone(self.docker.volume)
        self.assertFalse(any(a[3:4] == ['stop'] or 'down' in a or 'rm' in a for a, _ in self.docker.calls))
        self.reject()

    def test_failed_start_stops_only_verified_container_and_preserves_volume(self):
        self.docker.fail_start = True
        with self.assertRaises(LedgerStorageError):
            with self.db():
                pass
        self.assertIsNotNone(self.docker.volume)
        stops = [a for a, _ in self.docker.calls if a[3:4] == ['stop']]
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0][-1], self.docker.container['Id'])
        self.reject()

    def test_remote_daemon_or_wrong_image_rejected_before_allocation(self):
        self.docker.remote = True
        self.reject()
        self.assertEqual(self.docker.mutations(), [])

    def test_wrong_image_architecture_rejected_before_allocation(self):
        self.docker.image['Architecture'] = 'amd64'
        self.reject()

    def test_exact_own_named_volume_bind_representation_is_accepted(self):
        manifest = self.seed()
        self.docker.container['HostConfig']['Binds'] = [
            manifest['volume'] + ':/var/lib/postgresql:rw']
        with self.db() as db:
            self.assertTrue(db._ready)
        self.assertEqual(db.cleanup, 'own_product_stopped_data_preserved')

    def test_named_volume_bind_representation_rejects_other_source_target_or_mode(self):
        manifest = self.seed()
        own = manifest['volume'] + ':/var/lib/postgresql:rw'
        variants = [
            ['qh-product-data-other:/var/lib/postgresql:rw'],
            ['/synthetic-host-data:/var/lib/postgresql:rw'],
            [manifest['volume'] + ':/other:rw'],
            [manifest['volume'] + ':/var/lib/postgresql:ro'],
            [own, '/synthetic-other:/other:rw'],
        ]
        for binds in variants:
            with self.subTest(binds=binds):
                self.docker.container['HostConfig']['Binds'] = binds
                self.reject()

    def test_existing_container_safety_image_environment_and_identity_rejected(self):
        self.seed()
        baseline = deepcopy(self.docker.container)
        variants = [('Image', 'sha256:' + 'b' * 64), ('Id', 'd' * 64)]
        for key, val in variants:
            self.docker.container = deepcopy(baseline)
            self.docker.container[key] = val
            self.reject()
        host_variants = {'NetworkMode': 'host', 'Privileged': True, 'ReadonlyRootfs': False,
                         'AutoRemove': True, 'GroupAdd': ['0'], 'Sysctls': {'unsafe': '1'},
                         'CapAdd': ['SYS_ADMIN'], 'PortBindings': {'5432/tcp': [{}]},
                         'Binds': ['/synthetic:/host'], 'PidsLimit': -1, 'Memory': 0,
                         'RestartPolicy': {'Name': 'always', 'MaximumRetryCount': 0},
                         'LogConfig': {'Type': 'json-file', 'Config': {}},
                         'Tmpfs': {'/extra': ''}, 'SecurityOpt': []}
        for key, val in host_variants.items():
            with self.subTest(field=key):
                self.docker.container = deepcopy(baseline)
                self.docker.container['HostConfig'][key] = val
                self.reject()
        self.docker.container = deepcopy(baseline)
        self.docker.container['Config']['Env'].append('PGPASSWORD=synthetic-wrong')
        self.reject()
        self.docker.container = deepcopy(baseline)
        self.docker.container['Config']['Labels']['io.quantharbor.product.token'] = 'other'
        self.reject()

    def test_volume_identity_options_and_extra_mount_rejected(self):
        self.seed()
        self.docker.volume['CreatedAt'] = 'synthetic-time-2'
        self.reject()
        self.docker.volume['CreatedAt'] = 'synthetic-time-1'
        self.docker.volume['Options'] = {'device': '/synthetic'}
        self.reject()
        self.docker.volume['Options'] = None
        self.docker.container['Mounts'].append({'Type': 'bind', 'Destination': '/other'})
        self.reject()

    def test_manifest_image_schema_and_resource_tampering_rejected(self):
        self.seed()
        file = self.root / 'manifest.json'
        original = json.loads(file.read_text())
        for key, val in (('image', 'postgres:latest'), ('schema', {}),
                         ('project', 'other'), ('volume', 'other'), ('container_id', 'bad'),
                         ('phase', 'allocated'), ('unexpected', True)):
            with self.subTest(field=key):
                changed = deepcopy(original)
                changed[key] = val
                file.write_text(json.dumps(changed))
                self.reject()
        file.write_text(json.dumps(original))

    def test_migration_disk_and_compose_tampering_rejected_before_docker(self):
        read = Path.read_bytes
        def changed(path):
            data = read(path)
            return data + b'\n' if path == p.ROOT / 'migrations/0003_synthetic_execution.sql' else data
        with patch.object(Path, 'read_bytes', changed):
            self.reject()
        self.assertEqual(self.docker.calls, [])
        # Pending roots are deliberately not auto-repaired after failure.
        with tempfile.TemporaryDirectory(prefix='qh-product-compose-') as temporary:
            def compose_changed(path):
                data = read(path)
                return data + b'\n' if path == p.COMPOSE else data
            with patch.object(Path, 'read_bytes', compose_changed):
                self.reject(Path(temporary).resolve())

    def test_database_checksum_mismatch_rejected_and_preserved(self):
        self.seed()
        self.docker.schema['2'] = '0' * 64
        with self.assertRaises(LedgerStorageError):
            with self.db():
                pass
        self.assertIsNotNone(self.docker.volume)
        self.assertFalse(self.docker.container['State']['Running'])

    def test_role_server_version_and_final_schema_fail_closed(self):
        self.seed()
        for attribute in ('bad_role', 'bad_version', 'bad_schema'):
            with self.subTest(attribute=attribute):
                setattr(self.docker, attribute, True)
                db = self.db()
                with self.assertRaises(LedgerStorageError):
                    with db:
                        pass
                self.assertFalse(db._ready)
                self.assertFalse(self.docker.container['State']['Running'])
                setattr(self.docker, attribute, False)

    def test_migrations_order_exact_hashes_idempotent_guards_and_no_fixture_import(self):
        self.seed()
        with self.db():
            pass
        scripts = [raw.decode() for _, raw in self.docker.calls if raw and b'apply_product' in raw]
        self.assertEqual(len(scripts), 6)
        for index, sql in enumerate(scripts):
            version = index % 3 + 1
            self.assertIn(p.SCHEMA[str(version)], sql)
            self.assertIn('pg_advisory_xact_lock', sql)
            self.assertIn('SELECT NOT EXISTS', sql)
            for prior in range(1, version):
                self.assertIn(p.SCHEMA[str(prior)], sql)
        self.assertEqual(len(self.docker.schema), 3)

    def test_close_revalidation_refuses_changed_resource_and_releases_lock(self):
        db = self.db().__enter__()
        original = self.docker.container['Config']['User']
        self.docker.container['Config']['User'] = '0'
        count = len(self.docker.calls)
        with self.assertRaises(LedgerStorageError):
            db.close()
        self.assertEqual(self.docker.mutations(count), [])
        self.assertFalse(db._ready)
        self.docker.container['Config']['User'] = original
        with self.db():
            pass

    def test_unverified_new_container_is_never_started_or_stopped(self):
        self.docker.unsafe_create = True
        with self.assertRaises(LedgerStorageError):
            with self.db():
                pass
        self.assertIsNotNone(self.docker.volume)
        self.assertFalse(any(a[3:4] in (['start'], ['stop']) for a, _ in self.docker.calls))

    def test_failed_stop_preserves_data_and_releases_flock_for_verified_takeover(self):
        db = self.db().__enter__()
        self.docker.fail_stop = True
        with self.assertRaises(LedgerStorageError):
            db.close()
        self.assertEqual(db.cleanup, 'product_stop_failed_data_preserved')
        self.assertFalse(db._ready)
        self.assertTrue(self.docker.container['State']['Running'])
        self.docker.fail_stop = False
        with self.db():
            pass
        self.assertIsNotNone(self.docker.volume)
        self.assertFalse(self.docker.container['State']['Running'])


if __name__ == '__main__':
    unittest.main()
