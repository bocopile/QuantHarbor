"""P28-03 합성 제품 DB 수명관리. 금융 권위/HTTP/분석 조립은 제공하지 않는다.

private root와 Docker labels는 실수 방지 경계다. 같은 OS 사용자/관리자 공격의
격리나 물리 디스크 quota를 보장하지 않는다. 실패 자원은 삭제하지 않는다.
"""
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

from .postgres_ledger import LedgerStorageError, ROOT

IMAGE = 'postgres@sha256:a5377a521c0383c9862394c90bdbf7707800ac9a6e40d18318193badfac52ce0'
COMPOSE = ROOT / 'containers/compose.product.synthetic.yaml'
COMPOSE_SHA = '82028dc230cbf4d8d0265abe16926bd4277814048245e7236d82514e30c4d4db'
SCHEMA = {
    '1': '3dcad32e09b30af71a557ee211a98fb6afdd96e3639f77990a0a904bb045997a',
    '2': 'd48e206c7b74133cc5a8d1645bc986272701ba0124409d3bdb23b602d05333f8',
    '3': 'bcc8af18e4bf300715ed6b0b288ffac052cd2b6d23be208876741b92593c6afa',
}
MIGRATION_NAMES = ('0001_synthetic_foundation.sql', '0002_synthetic_ledger.sql', '0003_synthetic_execution.sql')
ENVIRONMENT = {'POSTGRES_USER': 'qh_synthetic', 'POSTGRES_DB': 'qh_synthetic',
               'POSTGRES_PASSWORD': 'synthetic-only-not-a-credential',
               'PGDATA': '/var/lib/postgresql/18/docker'}
COMMAND = ['postgres', '-c', 'listen_addresses=', '-c', 'max_connections=10', '-c', 'shared_buffers=16MB']
TMPFS = {'/var/run/postgresql': 'size=1048576,uid=999,gid=999,mode=0700',
         '/tmp': 'size=16777216,mode=1777'}
LOCK_BYTES = b'product-synthetic-writer-v1\n'
LIMIT = 16384


def _deny(reason):
    raise LedgerStorageError(reason)


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode() + b'\n'


def _json(raw):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                _deny('product_metadata_invalid')
            obj[key] = value
        return obj
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise LedgerStorageError('product_metadata_invalid') from None


def _hex(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _files():
    bodies = []
    for version, name in enumerate(MIGRATION_NAMES, 1):
        body = (ROOT / 'migrations' / name).read_bytes()
        if sha256(body).hexdigest() != SCHEMA[str(version)]:
            _deny('product_migration_checksum_mismatch')
        bodies.append(body.decode('utf-8'))
    if sha256(COMPOSE.read_bytes()).hexdigest() != COMPOSE_SHA:
        _deny('product_compose_mismatch')
    return bodies


def _migration(version, body):
    checksum = SCHEMA[str(version)]
    prior = '\n'.join(
        f"IF NOT EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version={i} AND checksum='{SCHEMA[str(i)]}') THEN RAISE EXCEPTION 'migration_order'; END IF;"
        for i in range(1, version))
    return f"""BEGIN;
SELECT pg_advisory_xact_lock(5130001) IS NOT NULL;
CREATE SCHEMA IF NOT EXISTS qh;
CREATE TABLE IF NOT EXISTS qh.schema_migrations(version integer PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now());
DO $guard$ BEGIN
{prior}
IF EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version={version} AND checksum<>'{checksum}') THEN RAISE EXCEPTION 'migration_checksum_mismatch'; END IF;
IF EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version NOT IN (1,2,3)) THEN RAISE EXCEPTION 'migration_version_mismatch'; END IF;
END $guard$;
SELECT NOT EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version={version}) AS apply_product \\gset
\\if :apply_product
{body}
INSERT INTO qh.schema_migrations(version,checksum) VALUES({version},'{checksum}');
\\endif
COMMIT;
"""


class ProductDatabase:
    """PostgresLedger가 소유하는 제한된 수명관리; 임의 DB/SQL 입력 seam 없음."""
    def __init__(self, runtime_root, binding_id):
        self.root_input, self.binding = runtime_root, binding_id
        self.fd = self.lock = None
        self.manifest = self.marker = None
        self.docker = None
        self.started = False
        self.active = False
        self.image = None

    def _check_file(self, fd):
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > LIMIT):
            _deny('product_private_file_invalid')

    def _read(self, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        try:
            self._check_file(fd)
            raw = os.read(fd, LIMIT + 1)
            if len(raw) > LIMIT:
                _deny('product_metadata_limit')
            return raw
        finally:
            os.close(fd)

    def _save(self, name, value):
        raw = _wire(value)
        if len(raw) > LIMIT:
            _deny('product_metadata_limit')
        # Existing targets must be regular private single-link files, never followed.
        if name in os.listdir(self.fd):
            self._read(name)
        temporary = '.pending-' + uuid.uuid4().hex
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        try:
            self._check_file(fd)
            offset = 0
            while offset < len(raw):
                offset += os.write(fd, raw[offset:])
            os.fsync(fd)
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
        finally:
            os.close(fd)
            if temporary in os.listdir(self.fd):
                os.unlink(temporary, dir_fd=self.fd)

    def _private_root(self):
        if (not isinstance(self.root_input, (str, Path)) or type(self.binding) is not str
                or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', self.binding) is None):
            _deny('product_binding_or_root_invalid')
        path = Path(self.root_input)
        if (not path.is_absolute() or '..' in path.parts or path == Path('/')
                or path.is_relative_to(ROOT) or ROOT.is_relative_to(path)):
            _deny('product_root_invalid')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in path.parts[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                _deny('product_root_not_private')
            self.root = {'path': str(path), 'device': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid}
            self.fd, fd = fd, None
        finally:
            if fd is not None:
                os.close(fd)
        names = set(os.listdir(self.fd))
        fresh = not names
        if not fresh and names != {'marker.json', 'manifest.json', 'writer.lock'}:
            _deny('product_unknown_root_contents')
        if fresh:
            self.lock = os.open('writer.lock', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                0o600, dir_fd=self.fd)
            self._check_file(self.lock)
            os.write(self.lock, LOCK_BYTES)
            os.fsync(self.lock)
            os.fsync(self.fd)
        else:
            # Validate all existing files before obtaining or modifying a resource.
            for name in names:
                self._read(name)
            self.lock = os.open('writer.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
            self._check_file(self.lock)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _deny('product_writer_locked')
        if os.pread(self.lock, LIMIT + 1, 0) != LOCK_BYTES:
            _deny('product_lock_invalid')
        if fresh:
            token = uuid.uuid4().hex
            self.marker = {'format': 'qh-product-synthetic-v1', 'binding_id': self.binding,
                           'root': self.root, 'token': token}
            self.manifest = {'marker': self.marker, 'image': IMAGE, 'schema': SCHEMA,
                             'project': 'qh-product-db-' + token,
                             'volume': 'qh-product-data-' + token, 'phase': 'allocated',
                             'context': None, 'endpoint': None, 'daemon_id': None,
                             'image_id': None, 'volume_created_at': None, 'container_id': None}
        else:
            self.marker = _json(self._read('marker.json'))
            self.manifest = _json(self._read('manifest.json'))
            self._validate_manifest()
        return fresh

    def _validate_manifest(self):
        marker, m = self.marker, self.manifest
        if (type(marker) is not dict or set(marker) != {'format', 'binding_id', 'root', 'token'}
                or marker['format'] != 'qh-product-synthetic-v1' or marker['binding_id'] != self.binding
                or marker['root'] != self.root or type(marker['token']) is not str
                or re.fullmatch('[0-9a-f]{32}', marker['token']) is None):
            _deny('product_binding_identity_mismatch')
        expected = {'marker', 'image', 'schema', 'project', 'volume', 'phase', 'context',
                    'endpoint', 'daemon_id', 'image_id', 'volume_created_at', 'container_id'}
        token = marker['token']
        if (type(m) is not dict or set(m) != expected or m['marker'] != marker
                or m['image'] != IMAGE or m['schema'] != SCHEMA
                or m['project'] != 'qh-product-db-' + token or m['volume'] != 'qh-product-data-' + token
                or m['phase'] != 'ready' or not _hex(m['container_id'])
                or not re.fullmatch('sha256:[0-9a-f]{64}', str(m['image_id']))
                or not all(type(m[k]) is str and 0 < len(m[k]) < 512
                           for k in ('context', 'endpoint', 'daemon_id', 'volume_created_at'))):
            _deny('product_manifest_invalid_or_initialization_requires_validation')

    def _labels(self):
        return {'io.quantharbor.product.synthetic': 'true',
                'io.quantharbor.product.token': self.marker['token'],
                'io.quantharbor.product.binding': sha256(self.binding.encode()).hexdigest(),
                'io.quantharbor.product.root': sha256(_wire(self.root)).hexdigest()}

    def _inspect(self, db, kind, identity):
        data = _json(db._run(self.docker + [kind, 'inspect', identity]))
        if type(data) is not list or len(data) != 1 or type(data[0]) is not dict:
            _deny('product_resource_metadata_invalid')
        return data[0]

    def _volume(self, db):
        m = self.manifest
        v = self._inspect(db, 'volume', m['volume'])
        if (v.get('Name') != m['volume'] or v.get('Driver') != 'local' or v.get('Scope') != 'local'
                or v.get('Options') not in (None, {}) or v.get('Labels') != self._labels()
                or type(v.get('CreatedAt')) is not str or not v['CreatedAt']
                or m['volume_created_at'] not in (None, v['CreatedAt'])):
            _deny('product_volume_identity_mismatch')
        return v['CreatedAt']

    def _container(self, db, identity):
        c = self._inspect(db, 'container', identity)
        m = self.manifest
        config, host = c['Config'], c['HostConfig']
        labels = config.get('Labels') or {}
        expected_labels = dict(self._labels(), **{'com.docker.compose.project': m['project'],
                                                 'com.docker.compose.service': 'db'})
        env = dict(x.split('=', 1) for x in config['Env'])
        expected_env = dict(x.split('=', 1) for x in self.image['Config']['Env'])
        expected_env.update(ENVIRONMENT)
        mounts = c.get('Mounts', [])
        data_mounts = [x for x in mounts if x.get('Type') == 'volume']
        if (not _hex(c.get('Id')) or m['container_id'] not in (None, c['Id'])
                or c.get('Image') != m['image_id'] or config.get('Image') != IMAGE
                or config.get('User') != '999:999' or config.get('Cmd') != COMMAND
                or config.get('Entrypoint') != self.image['Config']['Entrypoint']
                or env != expected_env or len(config['Env']) != len(env)
                or any(labels.get(k) != v for k, v in expected_labels.items())
                or host.get('NetworkMode') != 'none' or host.get('ReadonlyRootfs') is not True
                or host.get('CapDrop') != ['ALL'] or host.get('CapAdd') not in (None, [])
                or host.get('SecurityOpt') != ['no-new-privileges:true']
                or host.get('Privileged') is not False or host.get('PublishAllPorts') is not False
                or host.get('AutoRemove') is not False
                or host.get('PortBindings') not in (None, {})
                # Engines may also encode this named volume in Binds. Mounts
                # below must still independently identify the same own volume.
                or host.get('Binds') not in (None, [], [m['volume'] + ':/var/lib/postgresql:rw'])
                or host.get('Devices') not in (None, []) or host.get('DeviceRequests') not in (None, [])
                or host.get('PidMode', '') != '' or host.get('IpcMode') != 'private'
                or host.get('UTSMode', '') != '' or host.get('VolumesFrom') not in (None, [])
                or host.get('GroupAdd') not in (None, []) or host.get('DeviceCgroupRules') not in (None, [])
                or host.get('Sysctls') not in (None, {})
                or host.get('RestartPolicy') != {'Name': 'no', 'MaximumRetryCount': 0}
                or host.get('PidsLimit') != 128 or host.get('Memory') != 268435456
                or host.get('NanoCpus') != 1000000000 or host.get('Tmpfs') != TMPFS
                or host.get('LogConfig') != {'Type': 'json-file', 'Config': {'max-size': '1m', 'max-file': '3'}}
                or len(data_mounts) != 1 or data_mounts[0].get('Name') != m['volume']
                or data_mounts[0].get('Destination') != '/var/lib/postgresql'
                or data_mounts[0].get('RW') is not True
                or any(x.get('Type') not in ('volume', 'tmpfs') for x in mounts)
                or any(x.get('Destination') not in TMPFS for x in mounts if x.get('Type') == 'tmpfs')
                or set(c.get('NetworkSettings', {}).get('Networks', {})) - {'none'}):
            _deny('product_container_identity_or_safety_mismatch')
        # Exactly one service container, with the manifest's immutable Docker ID.
        ids = db._run(self.docker + ['ps', '-aq', '--no-trunc', '--filter',
                                    'label=com.docker.compose.project=' + m['project']]).decode().split()
        if ids != [c['Id']]:
            _deny('product_project_identity_mismatch')
        return c

    def _release(self):
        if self.lock is not None:
            os.close(self.lock)  # Closing releases flock, including failed entry.
            self.lock = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.active = False

    def open(self, db):
        if self.active or self.fd is not None:
            _deny('product_context_already_open')
        try:
            fresh = self._private_root()
            bodies = _files()
            # Do not inherit Docker/Compose/SQL overrides from the caller.
            db._env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR') if k in os.environ}
            db._env['COMPOSE_DISABLE_ENV_FILE'] = '1'
            context = db._run(['docker', 'context', 'show']).decode().strip()
            if re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', context) is None:
                _deny('product_context_invalid')
            meta = _json(db._run(['docker', 'context', 'inspect', context]))
            endpoint = meta[0]['Endpoints']['docker']['Host']
            if type(endpoint) is not str or not endpoint.startswith('unix:///') or len(endpoint) > 1024:
                _deny('nonlocal_docker_context')
            self.docker = ['docker', '--context', context]
            daemon = _json(db._run(self.docker + ['info', '--format', '{{json .ID}}']))
            if type(daemon) is not str or not daemon or len(daemon) > 256:
                _deny('product_daemon_identity_invalid')
            self.image = self._inspect(db, 'image', IMAGE)
            image_id = self.image['Id']
            if (IMAGE not in self.image['RepoDigests'] or self.image['Os'] != 'linux'
                    or self.image['Architecture'] != 'arm64'
                    or re.fullmatch('sha256:[0-9a-f]{64}', str(image_id)) is None):
                _deny('product_image_mismatch')
            m = self.manifest
            identity = {'context': context, 'endpoint': endpoint, 'daemon_id': daemon, 'image_id': image_id}
            if not fresh and any(m[k] != v for k, v in identity.items()):
                _deny('product_daemon_or_image_identity_mismatch')
            m.update(identity)
            db._project = m['project']
            for key, value in self._labels().items():
                env_key = {'io.quantharbor.product.token': 'QH_PRODUCT_TOKEN',
                           'io.quantharbor.product.binding': 'QH_PRODUCT_BINDING',
                           'io.quantharbor.product.root': 'QH_PRODUCT_ROOT'}.get(key)
                if env_key:
                    db._env[env_key] = value
            db._env['QH_PRODUCT_VOLUME'] = m['volume']
            db._compose = self.docker + ['compose', '--env-file', '/dev/null', '-p', m['project'], '-f', str(COMPOSE)]
            db._run(db._compose + ['config', '--quiet'])
            if fresh:
                # No existing name/project may be adopted. Read-only checks precede allocation.
                if (db._run(self.docker + ['volume', 'ls', '-q', '--filter', 'name=' + m['volume']]).strip()
                        or db._run(self.docker + ['ps', '-aq', '--filter',
                                                'label=com.docker.compose.project=' + m['project']]).strip()):
                    _deny('product_resource_collision')
                self._save('marker.json', self.marker)
                self._save('manifest.json', m)
                args = self.docker + ['volume', 'create', '--driver', 'local']
                for key, value in self._labels().items():
                    args += ['--label', key + '=' + value]
                db._run(args + [m['volume']])
                m['volume_created_at'] = self._volume(db)
                self._save('manifest.json', m)
                db._run(db._compose + ['create', '--no-build', '--pull', 'never', 'db'])
                ids = db._run(db._compose + ['ps', '--all', '--quiet', 'db']).decode().split()
                if len(ids) != 1 or not _hex(ids[0]):
                    _deny('product_container_identity_invalid')
                c = self._container(db, ids[0])
                m['container_id'] = c['Id']
                self._save('manifest.json', m)
            else:
                self._volume(db)
                c = self._container(db, m['container_id'])
            # Only fully inspected own resources can be started or stopped.
            self.started = True
            if not c['State']['Running']:
                db._run(self.docker + ['start', m['container_id']])
            for _ in range(30):
                try:
                    if db._run(db._compose + ['exec', '-T', 'db', 'cat', '/proc/1/comm'], timeout=5).strip() != b'postgres':
                        _deny('product_database_initializing')
                    db._run(db._compose + ['exec', '-T', 'db', 'pg_isready', '-U', 'qh_synthetic', '-d', 'qh_synthetic'], timeout=5)
                    break
                except LedgerStorageError:
                    time.sleep(0.2)
            else:
                _deny('product_initialization_requires_validation')
            if db._query('SHOW server_version;').split()[0] != '18.6':
                _deny('postgres_version_mismatch')
            role_sql = "SELECT json_build_array(current_user,current_database(),(SELECT rolsuper FROM pg_roles WHERE rolname=current_user));"
            if _json(db._query(role_sql)) != ['qh_synthetic', 'qh_synthetic', True]:
                _deny('product_database_role_mismatch')
            for version, body in enumerate(bodies, 1):
                db._query(_migration(version, body))
            rows = _json(db._query('SELECT json_object_agg(version,checksum) FROM qh.schema_migrations;'))
            if rows != SCHEMA:
                _deny('product_migration_checksum_mismatch')
            if db._query("SELECT count(*) FROM pg_roles WHERE rolname='qh_execution_product' AND NOT rolcanlogin AND NOT rolsuper;") != '1':
                _deny('product_database_role_mismatch')
            db.migration_checksums = {int(k): v for k, v in SCHEMA.items()}
            m['phase'] = 'ready'
            self._save('manifest.json', m)
            db._ready = True
            db.cleanup = 'product_active'
            self.active = True
            return db
        except BaseException as error:
            try:
                self.close(db)
            except LedgerStorageError:
                raise LedgerStorageError('product_stop_failed_requires_validation') from None
            if isinstance(error, (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, UnicodeError)):
                raise LedgerStorageError('product_metadata_or_private_path_invalid') from None
            raise

    def close(self, db):
        db._ready = False
        try:
            if self.started:
                # Revalidate before a destructive-to-liveness operation; never down/rm/prune.
                self._volume(db)
                self._container(db, self.manifest['container_id'])
                db._run(self.docker + ['stop', '--time', '30', self.manifest['container_id']], timeout=40)
                db.cleanup = 'own_product_stopped_data_preserved'
            elif self.fd is not None:
                db.cleanup = 'product_not_started_data_preserved'
        except (LedgerStorageError, OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            db.cleanup = 'product_stop_failed_data_preserved'
            raise LedgerStorageError('product_stop_failed_requires_validation') from None
        finally:
            self.started = False
            db._compose = None
            self._release()
