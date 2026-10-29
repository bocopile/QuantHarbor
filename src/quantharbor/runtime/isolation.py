"""Q14 trusted controller의 합성 연구 Docker 실행기.

untrusted Python은 stdin으로만 전달된다. host mount/소켓/부모 환경/도구 API는
주지 않는다. host 관리자·Docker daemon·고정 image·controller 소스는 신뢰한다.
RLIMIT_CPU 2초는 프로세스별이며 전체 작업은 CPU quota1 및 wall5초로 제한한다.
"""

from dataclasses import dataclass
import fcntl
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import uuid

from .boundary import BoundaryError, authorize


_ROOT = Path(__file__).resolve().parents[3]
MAX_INPUT_BYTES = 1048576
MAX_OUTPUT_BYTES = 1048576
WALL_SECONDS = 5
_UUID = re.compile(r"[0-9a-f]{32}")
_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
_SCOPE = "synthetic-isolation-v1"
_LOCK_ROOT = Path("/tmp").resolve()
_BOOTSTRAP = """import json,resource,sys
resource.setrlimit(resource.RLIMIT_CPU,(2,2))
resource.setrlimit(resource.RLIMIT_FSIZE,(16777216,16777216))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
raw=sys.stdin.buffer.read(1048577)
if len(raw)>1048576: raise SystemExit(65)
request=json.loads(raw)
scope={"__name__":"__main__","data":request["data"]}
exec(compile(request["code"],"<synthetic-research>","exec"),scope,scope)
"""


@dataclass(frozen=True, slots=True)
class _ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    limit: str | None


def _stop_process(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)


def _bounded_process(args, *, env, data=b"", timeout=3, output_limit=65536):
    """stdin도 동시에 전송해 pipe deadlock을 피하고 합산 출력만 보존한다."""
    process = None
    try:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env, start_new_session=True)
        stdout, stderr = bytearray(), bytearray()
        offset = 0
        limit = None
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            for stream, channel in ((process.stdout, "out"), (process.stderr, "err")):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, channel)
            if data:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "in")
            else:
                process.stdin.close()
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    limit = "wall_limit"
                    break
                for key, _ in selector.select(min(remaining, 0.05)):
                    stream, channel = key.fileobj, key.data
                    if channel == "in":
                        try:
                            written = os.write(stream.fileno(), data[offset:offset + 65536])
                            offset += written
                        except BrokenPipeError:
                            offset = len(data)
                        except BlockingIOError:
                            continue
                        if offset == len(data):
                            selector.unregister(stream)
                            stream.close()
                        continue
                    available = output_limit - len(stdout) - len(stderr)
                    try:
                        chunk = os.read(stream.fileno(), min(65536, available + 1))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                    elif len(chunk) > available:
                        (stdout if channel == "out" else stderr).extend(chunk[:available])
                        limit = "output_limit"
                        break
                    else:
                        (stdout if channel == "out" else stderr).extend(chunk)
                if limit:
                    break
            if limit:
                _stop_process(process)
            else:
                try:
                    process.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    limit = "wall_limit"
                    _stop_process(process)
        return _ProcessResult(process.returncode, bytes(stdout), bytes(stderr), limit)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        if process is not None and process.poll() is None:
            _stop_process(process)
        raise BoundaryError("docker_control_failure") from None
    finally:
        if process is not None:
            if process.poll() is None:
                _stop_process(process)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


@dataclass(frozen=True, slots=True)
class _PendingRun:
    run_id: str
    daemon_fingerprint: str

    def __post_init__(self):
        if (type(self.run_id) is not str or not _UUID.fullmatch(self.run_id)
                or type(self.daemon_fingerprint) is not str
                or not _FINGERPRINT.fullmatch(self.daemon_fingerprint)):
            raise BoundaryError("lock_invalid")


def _unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise BoundaryError("lock_invalid")
        value[key] = item
    return value


class _ControllerLock:
    """동일 UID의 고정 inode flock. stale 파일을 unlink하지 않는다."""

    def __init__(self):
        self.fd = None

    def __enter__(self):
        directory = _LOCK_ROOT / f"qh-isolation-{os.getuid()}"
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
            info = directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise BoundaryError("lock_invalid")
            path = directory / "controller.lock"
            self.fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
            info = os.fstat(self.fd)
            linked = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino)):
                raise BoundaryError("lock_invalid")
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise BoundaryError("runner_busy") from None
            return self
        except (OSError, BoundaryError) as failure:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            if isinstance(failure, BoundaryError):
                raise
            raise BoundaryError("lock_unavailable") from None

    def pending(self):
        os.lseek(self.fd, 0, os.SEEK_SET)
        value = os.read(self.fd, 513)
        if not value:
            return None
        try:
            if len(value) > 512:
                raise ValueError()
            item = json.loads(value.decode("ascii"), object_pairs_hook=_unique_fields)
            if (type(item) is not dict or item.keys() != {"schema_version", "run_id", "daemon_fingerprint"}
                    or type(item["schema_version"]) is not int or item["schema_version"] != 2):
                raise ValueError()
            return _PendingRun(item["run_id"], item["daemon_fingerprint"])
        except (ValueError, TypeError, UnicodeError):
            # UUID만 남은 v1은 대상 daemon을 증명하지 못하므로 보존·차단한다.
            raise BoundaryError("lock_invalid") from None

    def record(self, pending):
        if pending is not None and type(pending) is not _PendingRun:
            raise BoundaryError("lock_invalid")
        if pending is not None:
            pending.__post_init__()
        encoded = (json.dumps({"schema_version": 2, "run_id": pending.run_id,
                               "daemon_fingerprint": pending.daemon_fingerprint},
                              sort_keys=True, separators=(",", ":")).encode("ascii")
                   if pending is not None else b"")
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.ftruncate(self.fd, 0)
        if encoded and os.write(self.fd, encoded) != len(encoded):
            raise BoundaryError("lock_invalid")
        os.fsync(self.fd)

    def __exit__(self, *_):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


@dataclass(frozen=True, slots=True)
class ResearchResult:
    status: str
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    cleanup_verified: bool
    oom_killed: bool
    policy_verified: bool


def _request_bytes(code, data):
    if type(code) is not str:
        raise BoundaryError("input_invalid")
    budget = MAX_INPUT_BYTES

    def inspect(value, depth=0):
        nonlocal budget
        if depth > 32:
            raise BoundaryError("input_invalid")
        budget -= 1
        if type(value) is str:
            budget -= len(value)
        elif type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise BoundaryError("input_invalid")
                inspect(key, depth + 1)
                inspect(item, depth + 1)
        elif type(value) is list:
            for item in value:
                inspect(item, depth + 1)
        elif value is not None and type(value) not in (bool, int, float):
            raise BoundaryError("input_invalid")
        elif type(value) is float and not math.isfinite(value):
            raise BoundaryError("input_invalid")
        if budget < 0:
            raise BoundaryError("input_limit")

    request = {"code": code, "data": data}
    inspect(request)
    encoded = bytearray()
    try:
        for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False,
                                      separators=(",", ":")).iterencode(request):
            raw = chunk.encode("utf-8")
            if len(encoded) + len(raw) > MAX_INPUT_BYTES:
                raise BoundaryError("input_limit")
            encoded.extend(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError) as failure:
        if isinstance(failure, BoundaryError):
            raise
        raise BoundaryError("input_invalid") from None
    return bytes(encoded)


class DockerResearchRunner:
    """고정 합성 연구 실행. caller가 Docker flags/env/mount/image를 공급하지 못한다."""

    def __init__(self, binding):
        authorize(binding, "synthetic.compute")
        self._binding = binding
        self._env = {key: os.environ[key] for key in ("PATH", "TMPDIR")
                     if key in os.environ}
        binary = shutil.which("docker", path=self._env.get("PATH", os.defpath))
        if binary is None:
            raise BoundaryError("docker_unavailable")
        self._binary = binary
        try:
            lock = json.loads((_ROOT / "config/runtime-lock.json").read_bytes())
            self._image = lock["python"]["image"]
            self._platform = lock["platform"]
            if (type(self._image) is not str or not re.fullmatch(r"python@sha256:[0-9a-f]{64}", self._image)
                    or self._platform != "linux/arm64"):
                raise BoundaryError("runtime_lock_invalid")
        except (OSError, ValueError, KeyError, TypeError):
            raise BoundaryError("runtime_lock_invalid") from None
        # 기존 설정은 context 이름/endpoint 선별 조회에만 사용한다. 내용을
        # 읽거나 복사하지 않으며 이후 control/create/start에는 넘기지 않는다.
        discovery_env = self._env | {key: os.environ[key] for key in ("HOME", "DOCKER_CONFIG")
                                    if key in os.environ}
        context = self._discover_metadata([binary, "context", "show"], discovery_env).decode("utf-8").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", context):
            raise BoundaryError("docker_context_invalid")
        endpoint = self._discover_metadata([binary, "context", "inspect", "--format",
                                            "{{json .Endpoints.docker.Host}}", context], discovery_env)
        try:
            endpoint = json.loads(endpoint)
            if (type(endpoint) is not str or not endpoint.startswith("unix:///")
                    or any(ord(char) < 32 for char in endpoint)):
                raise ValueError()
        except (ValueError, TypeError):
            raise BoundaryError("docker_nonlocal_denied") from None
        self._endpoint = endpoint
        self._base = [binary, "--host", endpoint]
        try:
            self._image_env = self._environment_map(json.loads(self._command(
                ["image", "inspect", "--format", "{{json .Config.Env}}", self._image])))
        except (ValueError, TypeError):
            raise BoundaryError("pinned_image_environment_invalid") from None

    def _discover_metadata(self, args, env):
        result = _bounded_process(args, env=env)
        if result.limit or result.returncode != 0:
            raise BoundaryError("docker_control_failure")
        return result.stdout

    def _private_process(self, args, *, data=b"", timeout=3, output_limit=65536):
        # Docker CLI는 proxies 설정으로 컨테이너 env를 자동 추가할 수 있다.
        # 모든 control 요청마다 빈0700 config/HOME을 사용하고 공유하지 않는다.
        with tempfile.TemporaryDirectory(prefix="qh-docker-empty-", dir=_LOCK_ROOT) as directory:
            env = self._env | {"DOCKER_CONFIG": directory, "HOME": directory}
            return _bounded_process(args, env=env, data=data, timeout=timeout, output_limit=output_limit)

    def _metadata(self, args):
        result = self._private_process(args)
        if result.limit or result.returncode != 0:
            raise BoundaryError("docker_control_failure")
        return result.stdout

    def _command(self, args):
        return self._metadata(self._base + args)

    def _current_fingerprint(self):
        try:
            identity = json.loads(self._command(["info", "--format", "{{json .ID}}"] ))
            if type(identity) is not str or not re.fullmatch(r"[A-Za-z0-9:_.-]{1,256}", identity):
                raise ValueError()
            raw = json.dumps([self._endpoint, identity], ensure_ascii=True,
                             separators=(",", ":")).encode("ascii")
            return sha256(b"QuantHarbor/isolation-daemon-v1\x00" + raw).hexdigest()
        except (ValueError, TypeError):
            raise BoundaryError("daemon_identity_unconfirmed") from None

    @staticmethod
    def _environment_map(entries):
        if type(entries) is not list:
            raise BoundaryError("container_environment_invalid")
        result = {}
        for entry in entries:
            if type(entry) is not str or "=" not in entry:
                raise BoundaryError("container_environment_invalid")
            key, value = entry.split("=", 1)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in result:
                raise BoundaryError("container_environment_invalid")
            result[key] = value
        return result

    def _create_args(self, run_id):
        return ["container", "create", "--pull=never", "--platform", self._platform,
                "--name", "qh-isolation-" + run_id, "--label", "quantharbor.scope=" + _SCOPE,
                "--label", "quantharbor.run=" + run_id, "--label", f"quantharbor.uid={os.getuid()}",
                "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt",
                "no-new-privileges=true", "--pids-limit", "16", "--memory", "128m",
                "--memory-swap", "128m", "--cpus", "1", "--ulimit", "cpu=2:2",
                "--ulimit", "fsize=16777216:16777216", "--ulimit", "nofile=64:64",
                "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=1777",
                "--ipc", "none", "--log-driver", "none", "--user", "10001:10001",
                "--workdir", "/tmp", "--interactive", "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--env", "PYTHONUNBUFFERED=1", "--entrypoint", "python", self._image,
                "-I", "-S", "-u", "-c", _BOOTSTRAP]

    def _cleanup(self, pending):
        """보호된 state의 UUID와 정확한3개 label/name을 확인한 객체만 지운다."""
        if type(pending) is not _PendingRun:
            raise BoundaryError("cleanup_failed")
        pending.__post_init__()
        if self._current_fingerprint() != pending.daemon_fingerprint:
            raise BoundaryError("daemon_binding_mismatch")
        run_id = pending.run_id
        name = "qh-isolation-" + run_id
        listing = ["container", "ls", "--all", "--filter", "name=^/" + name + "$",
                   "--format", "{{.Names}}"]
        names = self._command(listing).decode("ascii").strip()
        if not names:
            # create 응답 유실 뒤 늦은 생성일 수 있다. 현재 부재만으로
            # marker를 지우지 않는다. 외부 삭제 후에도 수동 확인이 필요하다.
            raise BoundaryError("cleanup_unconfirmed")
        if names != name:
            raise BoundaryError("cleanup_failed")
        template = ('{{.Name}}|{{index .Config.Labels "quantharbor.scope"}}|'
                    '{{index .Config.Labels "quantharbor.run"}}|{{index .Config.Labels "quantharbor.uid"}}')
        identity = self._command(["container", "inspect", "--format", template, name]).decode("ascii").strip()
        if identity != f"/{name}|{_SCOPE}|{run_id}|{os.getuid()}":
            raise BoundaryError("cleanup_failed")
        self._command(["container", "rm", "--force", name])
        if self._command(listing).strip():
            raise BoundaryError("cleanup_failed")

    def _verify_created_policy(self, name):
        # 생성된 자기 컨테이너의 최소 정책 metadata만 읽고 실행 전에 확인한다.
        template = ('[{{json .HostConfig.NetworkMode}},{{json .HostConfig.ReadonlyRootfs}},'
                    '{{json .HostConfig.Privileged}},{{json .HostConfig.LogConfig.Type}},'
                    '{{json .Config.Env}}]')
        raw = self._command(["container", "inspect", "--format", template, name])
        try:
            policy = json.loads(raw)
            if (type(policy) is not list or len(policy) != 5 or policy[0] != "none"
                    or policy[1] is not True or policy[2] is not False or policy[3] != "none"):
                raise ValueError()
            expected_env = self._image_env | {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
            if self._environment_map(policy[4]) != expected_env:
                raise ValueError()
        except (ValueError, TypeError):
            raise BoundaryError("container_policy_invalid") from None

    def run(self, code, data):
        authorize(self._binding, "synthetic.compute")
        request = _request_bytes(code, data)
        with _ControllerLock() as controller_lock:
            stale = controller_lock.pending()
            current_fingerprint = self._current_fingerprint()
            if stale is not None:
                if stale.daemon_fingerprint != current_fingerprint:
                    raise BoundaryError("daemon_binding_mismatch")
                self._cleanup(stale)
                controller_lock.record(None)
            run_id = uuid.uuid4().hex
            pending = _PendingRun(run_id, current_fingerprint)
            controller_lock.record(pending)
            result = None
            state = None
            try:
                self._command(self._create_args(run_id))
                name = "qh-isolation-" + run_id
                self._verify_created_policy(name)
                # wall 한도는 살아 있는 controller가 감시한다. host SIGKILL 뒤의
                # 5초 종료를 보장하지 않으며 다음 실행은 bound stale marker로 복구한다.
                result = self._private_process(self._base + ["container", "start", "--attach", "--interactive", name],
                                               data=request, timeout=WALL_SECONDS, output_limit=MAX_OUTPUT_BYTES)
                if result.limit is None:
                    raw = self._command(["container", "inspect", "--format",
                                         "{{.State.Status}} {{.State.Running}} {{.State.ExitCode}} {{.State.OOMKilled}}", name])
                    state = raw.decode("ascii").strip().split()
                    if (len(state) != 4 or state[0] != "exited" or state[1] != "false"
                            or state[3] not in ("true", "false")):
                        raise BoundaryError("docker_state_invalid")
                    exit_code = int(state[2])
                    if not 0 <= exit_code <= 255:
                        raise BoundaryError("docker_state_invalid")
                    if result.returncode != 0 and exit_code == 0:
                        raise BoundaryError("docker_control_failure")
            finally:
                # start client 종료만으로 작업 종료를 추정하지 않는다.
                # 실패하면 marker를 보존해 다음 실행도 stale 정리 전 차단한다.
                try:
                    self._cleanup(pending)
                except Exception:
                    raise BoundaryError("cleanup_failed") from None
                controller_lock.record(None)
            if result.limit:
                return ResearchResult(result.limit, None, result.stdout, result.stderr, True, False, True)
            return ResearchResult("succeeded" if exit_code == 0 else "failed", exit_code,
                                  result.stdout, result.stderr, True, state[3] == "true", True)
