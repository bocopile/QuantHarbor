#!/usr/bin/env python3
"""Q15 공개 후보의 읽기 전용 로컬 검사. 분석 파일을 import/실행하지 않는다."""

import sys

# sys는 interpreter 내장 모듈이다. script/PYTHONPATH의 shadow stdlib를
# import하기 전에 CLI를 거부한다. 개발 단위시험의 신뢰된 import는 별도다.
if __name__ == "__main__" and (not sys.flags.isolated or not sys.flags.no_site):
    sys.stdout.write('{"scope":"Q15_public_candidates_only","result":"fail","reason":"isolated_python_required"}\n')
    raise SystemExit(2)

import ast
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import stat
import subprocess
import time
import tomllib


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 1048576
MAX_TOTAL_BYTES = 16777216
MAX_LIST_BYTES = 2097152
MAX_FILES = 4096
CI_ACTIONS = (
    ("actions/checkout", "3d3c42e5aac5ba805825da76410c181273ba90b1"),
    ("actions/setup-python", "6d4fd22b20465ccc0f7354476588e8df7c9ca0e0"),
)
BASELINE_PATHS = frozenset((
    "docs/architecture.md", "docs/contracts/serialization-v1.md", "docs/implementation-backlog.md",
    "docs/decisions/ARC-DEC-004-implementation-baseline.md", "docs/contracts/data-v1.md",
    "docs/contracts/execution-v1.md", "docs/contracts/operations-v1.md",
))
_ROOT_FILES = frozenset(("AGENTS.md", "README.md", "pyproject.toml", ".gitignore", ".dockerignore", ".env.example"))
_CONFIG_FILES = frozenset((
    "config/README.md", "config/runtime-lock.json", "config/runtime.synthetic.toml", "config/market-storage-lock.json",
    "config/ai/development-policy.toml", "config/ai/execution-queue.json", "config/ai/team.toml",
    "config/ai/slack-notifications.example.json", "config/ci/quality.workflow.example.yml",
))
_PUBLIC_ROOTS = frozenset(("docs", "src", "scripts", "tests", "migrations", "containers"))
_TEXT_SUFFIXES = frozenset((".md", ".py", ".json", ".toml", ".yaml", ".yml", ".sql", ".txt", ".sh"))
_PROTECTED_PARTS = frozenset((".git", ".idea", ".vscode", ".aws", ".ssh", "private", ".private",
                              "secrets", ".secrets", "credentials", ".credentials", "keys", ".keys",
                              ".runtime", "runtime", "raw",
                              "processed", "logs", "backups", "artifacts", "reports"))
_PROTECTED_SUFFIXES = (".pem", ".key", ".p8", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3",
                       ".dump", ".log", ".sql.gz", ".db-wal", ".db-shm", ".keystore")
_SENSITIVE_NAMES = frozenset(("token.json", "tokens.json", "kis_devlp.yaml", "credentials.json",
                              "secrets.json", "secrets.yaml", "secrets.yml", "accounts.csv", "transactions.csv"))
_HEX64 = re.compile(r"[0-9a-f]{64}")
_SECRET_PATTERNS = (
    ("secret_private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")),
    ("secret_github_token", re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{36}(?![A-Za-z0-9])")),
    ("secret_github_token", re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{70,255}(?![A-Za-z0-9_])")),
    ("secret_slack_token", re.compile(r"(?<![A-Za-z0-9_])xox[baprs]-[0-9]{8,15}-[0-9]{8,15}-[A-Za-z0-9]{20,64}")),
    ("secret_api_token", re.compile(r"(?<![A-Za-z0-9_])sk-(?:proj-|svcacct-|ant-)?[A-Za-z0-9_-]{32,}")),
    ("secret_aws_access_id", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])")),
)
_PUBLISHED_DUMMIES = frozenset(("AKIAIOSFODNN7EXAMPLE",))
_DOMAIN_IMPORTS = frozenset(("dataclasses", "datetime", "decimal", "enum", "fractions", "functools",
                             "hashlib", "hmac", "itertools", "json", "math", "operator", "re",
                             "statistics", "string", "types", "typing", "collections"))
_IO_CALLS = frozenset(("open", "read_text", "read_bytes", "write_text", "write_bytes", "connect",
                       "urlopen", "system", "popen", "Popen", "fork", "spawn", "execute", "executemany"))

MARKET_STORAGE_LOCK = {'schema_version': 1, 'scope': 'Q17 synthetic local Parquet only', 'checked_on': '2026-10-24', 'platform': 'linux/arm64', 'python_image': 'python@sha256:608b27b2db85abf38d81685085cd1166a5ed7ada66549f0dfe53a75bb830cd5d', 'python_version': '3.13.17', 'package': 'pyarrow', 'version': '26.0.0', 'wheel': 'pyarrow-26.0.0-cp313-cp313-manylinux_2_28_aarch64.whl', 'wheel_sha256': 'e3b190ba1d3d22a5a8758597f797111b77d433473744352a184a5ee0a42d672e', 'wheel_size': 50865064, 'url': 'https://files.pythonhosted.org/packages/3b/7c/cea852a832a327a8de797b3a68e5c25ce0f5aa1d20503807671bd90ec642/pyarrow-26.0.0-cp313-cp313-manylinux_2_28_aarch64.whl', 'source_revision': '446167169a0dc547e00e1bc29f417a40c0ca267a', 'license': 'Apache-2.0 plus bundled third-party LICENSE/NOTICE retained', 'license_sha256': 'cd03925a27219d326d622609fbcae6567279af8b8885c33d5969a9e4ef5d7525', 'notice_sha256': 'afd895d61a00101f6d5a41cf518c83865d815e8109e956f512a0ce4ea9738c06', 'python_dependencies': [], 'compatibility_status': 'synthetic_fixed_runtime_pass', 'limits': 'No claim of full native dependency vulnerability audit, binary/source attestation, real-data rights or production runtime adoption'}
MARKET_STORAGE_DOCKERFILE = 'FROM python@sha256:608b27b2db85abf38d81685085cd1166a5ed7ada66549f0dfe53a75bb830cd5d\nWORKDIR /app\nENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\nCOPY wheels/ /opt/wheels/\nCOPY containers/requirements.market-storage.txt /opt/requirements.txt\nRUN ["python", "-I", "-m", "pip", "install", "--no-index", "--no-deps", "--no-cache-dir", "--disable-pip-version-check", "--require-hashes", "--find-links=/opt/wheels", "-r", "/opt/requirements.txt"]\nCOPY src/ /app/src/\nCOPY tests/product/ /app/tests/product/\nCOPY tests/storage/ /app/tests/storage/\nCOPY config/runtime.synthetic.toml /app/config/runtime.synthetic.toml\nCOPY config/runtime-lock.json /app/config/runtime-lock.json\nCOPY config/market-storage-lock.json /app/config/market-storage-lock.json\nCOPY pyproject.toml /app/pyproject.toml\nRUN ["python", "-I", "-c", "import os; os.mkdir(\'/store\',0o700); os.chown(\'/store\',10001,10001)"]\nUSER 10001:10001\nCMD ["python", "-m", "unittest", "discover", "-s", "tests/storage", "-v"]\n'
MARKET_STORAGE_REQUIREMENTS = 'pyarrow==26.0.0 --hash=sha256:e3b190ba1d3d22a5a8758597f797111b77d433473744352a184a5ee0a42d672e\n'


class QualityFailure(Exception):
    pass


@dataclass(frozen=True)
class Finding:
    reason: str
    path: str | None = None

    def public(self):
        result = {"reason": self.reason}
        if self.path is not None:
            result["path"] = safe_label(self.path)
        return result


def safe_label(path):
    if (type(path) is str and len(path) <= 240
            and re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", path)
            and all(part not in (".", "..") and len(part) <= 80 for part in path.split("/"))
            and not any(pattern.search(path) for _, pattern in _SECRET_PATTERNS)):
        return path
    return "<redacted_path>"


def classify(path):
    """이름만 검사한다. 실패 경로의 content/target을 조회하지 않는다."""
    if type(path) is not str or safe_label(path) != path:
        raise QualityFailure("unsafe_path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in (".", "..") for part in path.split("/")):
        raise QualityFailure("unsafe_path")
    lower = tuple(part.lower() for part in pure.parts)
    name = lower[-1]
    for index, part in enumerate(lower):
        if ((part.startswith(".env") and path != ".env.example") or ".local." in part
                or part.endswith(".local") or part in _SENSITIVE_NAMES):
            raise QualityFailure("protected_path")
        if part in _PROTECTED_PARTS:
            if (part == "runtime" and lower[:3] == ("src", "quantharbor", "runtime")
                    and index == 2 and name.endswith(".py")):
                continue
            raise QualityFailure("protected_path")
    if (name.endswith(_PROTECTED_SUFFIXES) or name in _SENSITIVE_NAMES or ".local." in name
            or name.endswith(".local") or (name.startswith(".env") and path != ".env.example")
            or lower[:2] == ("data", "private") or lower[0] in ("data", "accounts")
            or (len(lower) >= 2 and lower[:2] == (".github", "workflows"))):
        raise QualityFailure("protected_path")
    safe_example = bool(re.search(r"\.(?:example|synthetic|fixture)\.(?:yaml|yml|json|toml|txt|md)$", name))
    allowed = (path in _ROOT_FILES or path in _CONFIG_FILES or lower[0] in _PUBLIC_ROOTS
               or (lower[0] == "config" and safe_example)
               or bool(re.fullmatch(r"\.codex/agents/qh_[a-z_]+\.toml", path))
               or path in (".codex/config.toml", ".codex/hooks.json")
               or bool(re.fullmatch(r"\.agents/skills/qh-[a-z-]+/SKILL\.md", path)))
    if not allowed:
        raise QualityFailure("unclassified_candidate")
    if (path not in _ROOT_FILES and pure.suffix.lower() not in _TEXT_SUFFIXES
            and path not in ("containers/Dockerfile.synthetic", "containers/Dockerfile.market-storage")):
        raise QualityFailure("unsupported_file_type")


def _git(root, arguments, data=b"", allowed=(0,)):
    """고정 Git 읽기 명령만 호출한다. 출력/입력은 NUL 목록이며 bounded다."""
    binary = shutil.which("git", path=os.defpath)
    if binary is None:
        raise QualityFailure("git_unavailable")
    command = [binary, "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
               "-c", "core.hooksPath=/dev/null", *arguments]
    # 표준 global/system exclude도 보존한다. 전역 설정을 끄면 사용자가
    # ignore한 개인 파일이 공개 후보로 다시 나타날 수 있다. 해당 내용을
    # Python에서 열지 않으며 Git에는 선택된 HOME/XDG 경로만 전달한다.
    environment = {"PATH": os.defpath, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    environment.update({key: os.environ[key] for key in ("HOME", "XDG_CONFIG_HOME") if key in os.environ})
    process = None
    try:
        process = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        output = bytearray()
        count = 0
        offset = 0
        deadline = time.monotonic() + 5
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            if data:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE)
            else:
                process.stdin.close()
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise QualityFailure("git_timeout")
                for key, event in selector.select(0.05):
                    stream = key.fileobj
                    try:
                        if stream is process.stdin:
                            offset += os.write(stream.fileno(), data[offset:offset + 65536])
                            if offset == len(data):
                                selector.unregister(stream)
                                stream.close()
                        else:
                            chunk = os.read(stream.fileno(), min(65536, MAX_LIST_BYTES - count + 1))
                            count += len(chunk)
                            if count > MAX_LIST_BYTES:
                                raise QualityFailure("git_output_limit")
                            if not chunk:
                                selector.unregister(stream)
                                stream.close()
                            elif stream is process.stdout:
                                output.extend(chunk)
                    except BlockingIOError:
                        continue
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if process.returncode not in allowed:
            raise QualityFailure("git_query_failed")
        return bytes(output)
    except (OSError, subprocess.TimeoutExpired):
        raise QualityFailure("git_query_failed") from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


def _nul_names(raw):
    if raw and not raw.endswith(b"\0"):
        raise QualityFailure("git_metadata_invalid")
    try:
        names = [item.decode("utf-8") for item in raw.split(b"\0")[:-1]]
    except UnicodeError:
        raise QualityFailure("git_metadata_invalid") from None
    if len(names) > MAX_FILES or len(names) != len(set(names)):
        raise QualityFailure("git_candidate_limit_or_duplicate")
    return names


def candidates(root):
    raw = _git(root, ["ls-files", "--cached", "--others", "--exclude-standard", "--full-name", "-z"])
    names = _nul_names(raw)
    ignored = _nul_names(_git(root, ["check-ignore", "--no-index", "--stdin", "-z"], raw, allowed=(0, 1)))
    if not set(ignored) <= set(names):
        raise QualityFailure("git_metadata_invalid")
    return names, frozenset(ignored)


def _read_public(root_fd, path):
    classify(path)
    descriptor = os.dup(root_fd)
    try:
        parts = path.split("/")
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            if index < len(parts) - 1:
                flags |= os.O_DIRECTORY
            current = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = current
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise QualityFailure("file_type_or_hardlink_denied")
        if info.st_size > MAX_FILE_BYTES:
            raise QualityFailure("file_size_limit")
        content = bytearray()
        while len(content) <= MAX_FILE_BYTES:
            chunk = os.read(descriptor, min(65536, MAX_FILE_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(descriptor)
        if len(content) > MAX_FILE_BYTES:
            raise QualityFailure("file_size_limit")
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise QualityFailure("file_changed_during_read")
        try:
            text = content.decode("utf-8")
        except UnicodeError:
            raise QualityFailure("non_utf8_or_binary") from None
        if any(ord(char) < 32 and char not in "\t\r\n" for char in text) or "\x7f" in text:
            raise QualityFailure("non_utf8_or_binary")
        return bytes(content), text
    except OSError:
        raise QualityFailure("unsafe_file_access") from None
    finally:
        os.close(descriptor)


def _syntax_domain(path, text):
    try:
        tree = ast.parse(text, filename="<public-candidate>")
    except (SyntaxError, ValueError, RecursionError):
        return [Finding("python_syntax_invalid", path)]
    if not path.startswith("src/quantharbor/domain/"):
        return []
    package = path.removeprefix("src/").split("/")[:-1]
    for node in ast.walk(tree):
        imported = []
        if isinstance(node, ast.Import):
            imported = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package) - node.level + 1] if node.level <= len(package) else []
                imported = [".".join(base + ([node.module] if node.module else []))]
            else:
                imported = [node.module or ""]
        if any(not (name == "quantharbor.domain" or name.startswith("quantharbor.domain.")
                       or name.split(".")[0] in _DOMAIN_IMPORTS) for name in imported):
            return [Finding("domain_import_boundary", path)]
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else "")
            if name in _IO_CALLS or (isinstance(node.func, ast.Name) and name in
                                     ("eval", "exec", "compile", "__import__", "input", "breakpoint")):
                return [Finding("domain_io_boundary", path)]
    return []


def _unique_json(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise QualityFailure("duplicate_json_key")
        value[key] = item
    return value


def _json(snapshot, path):
    try:
        return json.loads(snapshot[path][1], object_pairs_hook=_unique_json)
    except (KeyError, ValueError, TypeError):
        raise QualityFailure("required_json_invalid") from None


def check_baseline(snapshot):
    path = "docs/contracts/baseline-v1.json"
    findings = []
    try:
        baseline = _json(snapshot, path)
        entries = baseline["files"]
        if (type(baseline["version"]) is not int or baseline["version"] != 1
                or type(entries) is not dict or set(entries) != BASELINE_PATHS):
            raise QualityFailure("baseline_schema_or_file_set")
        for name, digest in entries.items():
            classify(name)
            if type(digest) is not str or not _HEX64.fullmatch(digest):
                raise QualityFailure("baseline_digest_invalid")
            if name not in snapshot:
                findings.append(Finding("baseline_file_missing", name))
            elif sha256(snapshot[name][0]).hexdigest() != digest:
                findings.append(Finding("baseline_hash_mismatch", name))
    except (QualityFailure, KeyError, TypeError) as failure:
        findings.append(Finding(str(failure) if isinstance(failure, QualityFailure) else "baseline_schema_invalid", path))
    return findings


def _normalized(text, *, dockerfile=False):
    # 승인된 제한 YAML/Dockerfile 형식만 허용. 일반 YAML 파서라고 주장하지 않는다.
    # Unicode whitespace/CR/TAB을 의미가 다른 ASCII 구분자로 정규화하지 않는다.
    if any(char.isspace() and char not in (" ", "\n") for char in text):
        raise QualityFailure("control_whitespace_invalid")
    normalized = []
    for line in text.split("\n"):
        if dockerfile and re.match(r"^ *# *(?:syntax|escape|check) *=", line, re.IGNORECASE):
            raise QualityFailure("docker_parser_directive_denied")
        if not line.strip(" ") or line.lstrip(" ").startswith("#"):
            continue
        if not dockerfile:
            # 이 두 단일 YAML scalar의 ASCII tag 주석만 허용한다.
            # run/block shell 명령과 Docker 명령의 inline #는 제거하지 않는다.
            match = re.fullmatch(
                r"(      - uses: actions/(?:checkout|setup-python)@[0-9a-f]{40}) +#[ -~]*", line)
            if match:
                line = match.group(1)
        normalized.append(line.rstrip(" "))
    return tuple(normalized)


def expected_dockerfile(lock):
    return f'''FROM {lock["python"]["image"]}
WORKDIR /app
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY src/ /app/src/
COPY tests/product/ /app/tests/product/
COPY config/runtime.synthetic.toml /app/config/runtime.synthetic.toml
COPY config/runtime-lock.json /app/config/runtime-lock.json
COPY pyproject.toml /app/pyproject.toml
USER 10001:10001
CMD ["python", "-m", "quantharbor", "status"]'''


def expected_compose(lock):
    return f'''services:
  app:
    build:
      context: ..
      dockerfile: containers/Dockerfile.synthetic
      network: none
    platform: {lock["platform"]}
    network_mode: none
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    pids_limit: 64
    mem_limit: 128m
    cpus: 1
    tmpfs:
      - /tmp:size=16777216,mode=1777
    restart: "no"
  db:
    image: {lock["postgres"]["image"]}
    platform: {lock["platform"]}
    user: "999:999"
    network_mode: none
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    pids_limit: 128
    mem_limit: 256m
    cpus: 1
    environment:
      POSTGRES_USER: qh_synthetic
      POSTGRES_DB: qh_synthetic
      POSTGRES_PASSWORD: synthetic-only-not-a-credential
      PGDATA: /var/lib/postgresql/18/docker
    command: [postgres, -c, "listen_addresses=", -c, "max_connections=10", -c, "shared_buffers=16MB"]
    tmpfs:
      - /var/lib/postgresql:size=134217728,uid=999,gid=999,mode=0700
      - /var/run/postgresql:size=1048576,uid=999,gid=999,mode=0700
      - /tmp:size=16777216,mode=1777
    restart: "no"'''


def expected_ci(lock, checkout, setup):
    return f'''name: QuantHarbor synthetic quality
on:
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: qh-synthetic-quality
  cancel-in-progress: false
jobs:
  quality:
    runs-on: ubuntu-24.04-arm
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@{checkout}
        with:
          persist-credentials: false
          fetch-depth: 1
          submodules: false
      - uses: actions/setup-python@{setup}
        with:
          python-version: '{lock["python"]["version"]}'
          architecture: arm64
      - name: Public candidate checks
        run: python3.13 -I -S scripts/check_quality.py
      - name: Product and quality unit tests
        env:
          PYTHONPATH: src
        run: |
          python3.13 -m unittest discover -s tests/product -v
          python3.13 -m unittest discover -s tests/quality -v
      - name: Fetch pinned synthetic images
        run: |
          docker pull {lock["python"]["image"]}
          docker pull {lock["postgres"]["image"]}
      - name: Foundation and isolated research
        env:
          PYTHONPATH: src
        run: |
          python3.13 scripts/check_foundation.py
          python3.13 scripts/check_isolation.py'''


def check_runtime(snapshot):
    findings = []
    path = "config/runtime-lock.json"
    try:
        lock = _json(snapshot, path)
        if (type(lock["schema_version"]) is not int or lock["schema_version"] != 1
                or lock["platform"] != "linux/arm64" or lock["python_packages"] != []
                or type(lock["python_packages"]) is not list):
            raise QualityFailure("runtime_lock_policy")
        for product in ("python", "postgres"):
            item = lock[product]
            if (not re.fullmatch(product + r"@sha256:[0-9a-f]{64}", item["image"])
                    or not re.fullmatch(r"[0-9a-f]{40}", item["source_revision"])
                    or type(item["license"]) is not str or not item["license"]):
                raise QualityFailure("runtime_lock_pin_or_license")
        if (not re.fullmatch(r"3\.13\.[0-9]+", lock["python"]["version"])
                or not re.fullmatch(r"18\.[0-9]+", lock["postgres"]["version"])
                or not _HEX64.fullmatch(lock["python"]["source_sha256"])):
            raise QualityFailure("runtime_lock_version_or_source")
        project = tomllib.loads(snapshot["pyproject.toml"][1])
        if (project["project"]["dependencies"] != [] or type(project["project"]["dependencies"]) is not list
                or project["project"].get("optional-dependencies", {}) != {} or "build-system" in project
                or "dependencies" in project["project"].get("dynamic", [])
                or project["project"]["requires-python"] != ">=3.13,<3.14"):
            raise QualityFailure("dependency_policy_changed")
        inventory_path = lock["inventory"]
        classify(inventory_path)
        if not re.fullmatch(r"docs/evidence/[A-Za-z0-9_.-]+\.json", inventory_path):
            raise QualityFailure("inventory_path_invalid")
        inventory = _json(snapshot, inventory_path)
        if (inventory["all_dpkg_packages_copyright_readable"] is not True
                or not _HEX64.fullmatch(inventory["python_license_sha256"])):
            raise QualityFailure("inventory_notice_missing")
        for product in ("python", "postgres"):
            item = inventory["images"][product]
            notices = item["license_notice_sha256"]
            if (item["image"] != lock[product]["image"] or type(item["packages"]) is not list
                    or not item["packages"] or not all(type(value) is str and "\t" in value for value in item["packages"])
                    or type(notices) is not list or not notices
                    or not all(type(value) is str and re.fullmatch(r"[0-9a-f]{64}  /usr/(?:share|local)/[^\r\n]+", value)
                               for value in notices)):
                raise QualityFailure("inventory_image_or_notice_mismatch")
        comparisons = (("containers/Dockerfile.synthetic", expected_dockerfile(lock)),
                       ("containers/compose.synthetic.yaml", expected_compose(lock)))
        for name, expected in comparisons:
            try:
                dockerfile = name == "containers/Dockerfile.synthetic"
                if _normalized(snapshot[name][1], dockerfile=dockerfile) != _normalized(expected, dockerfile=dockerfile):
                    findings.append(Finding("container_definition_drift", name))
            except QualityFailure as failure:
                findings.append(Finding(str(failure), name))
        ci_path = "config/ci/quality.workflow.example.yml"
        ci = snapshot[ci_path][1]
        actions = re.findall(r"^      - uses: ([A-Za-z0-9_/-]+)@([0-9a-f]{40})(?:\s|$)", ci, re.MULTILINE)
        try:
            if (tuple(actions) != CI_ACTIONS
                    or _normalized(ci) != _normalized(expected_ci(lock, CI_ACTIONS[0][1], CI_ACTIONS[1][1]))):
                findings.append(Finding("inactive_ci_policy_drift", ci_path))
        except QualityFailure as failure:
            findings.append(Finding(str(failure), ci_path))
        definition = snapshot["docs/development/ci-definition.md"][1]
        if "../../config/ci/quality.workflow.example.yml" not in definition or ".github/workflows" not in definition:
            findings.append(Finding("inactive_ci_location_mismatch", "docs/development/ci-definition.md"))
    except (QualityFailure, KeyError, TypeError, ValueError, IndexError) as failure:
        findings.append(Finding(str(failure) if isinstance(failure, QualityFailure) else "runtime_metadata_invalid", path))
    return findings


def check_market_storage(snapshot):
    path = "config/market-storage-lock.json"
    try:
        if _json(snapshot, path) != MARKET_STORAGE_LOCK:
            return [Finding("market_storage_lock_drift", path)]
        dockerfile = "containers/Dockerfile.market-storage"
        if _normalized(snapshot[dockerfile][1], dockerfile=True) != _normalized(MARKET_STORAGE_DOCKERFILE, dockerfile=True):
            return [Finding("market_storage_container_drift", dockerfile)]
        requirements = "containers/requirements.market-storage.txt"
        if snapshot[requirements][1] != MARKET_STORAGE_REQUIREMENTS:
            return [Finding("market_storage_dependency_drift", requirements)]
        return []
    except (QualityFailure, KeyError, TypeError, ValueError):
        return [Finding("market_storage_metadata_invalid", path)]


def inspect_repository(root):
    findings = []
    snapshot = {}
    total = 0
    descriptor = None
    try:
        names, ignored = candidates(root)
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        for path in sorted(names):
            try:
                classify(path)
            except QualityFailure as failure:
                findings.append(Finding(str(failure)))
                continue
            if path in ignored:
                continue
            try:
                content, text = _read_public(descriptor, path)
                total += len(content)
                if total > MAX_TOTAL_BYTES:
                    raise QualityFailure("total_size_limit")
                snapshot[path] = (content, text)
                if path.endswith(".py"):
                    findings.extend(_syntax_domain(path, text))
                for reason, pattern in _SECRET_PATTERNS:
                    if any(match.group() not in _PUBLISHED_DUMMIES for match in pattern.finditer(text)):
                        findings.append(Finding(reason, path))
            except QualityFailure as failure:
                findings.append(Finding(str(failure), path))
                if str(failure) == "total_size_limit":
                    break
        findings.extend(check_baseline(snapshot))
        findings.extend(check_runtime(snapshot))
        findings.extend(check_market_storage(snapshot))
    except (QualityFailure, OSError) as failure:
        findings.append(Finding(str(failure) if isinstance(failure, QualityFailure) else "repository_access_failed"))
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return {"scope": "Q15_public_candidates_only", "result": "fail" if findings else "pass",
            "files_checked": len(snapshot), "findings": [item.public() for item in findings],
            "excludes": "ignored_private_files;git_history;complete_secret_or_vulnerability_audit;remote_CI"}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args:
        print(json.dumps({"scope": "Q15_public_candidates_only", "result": "fail", "reason": "arguments_denied"}))
        return 2
    try:
        report = inspect_repository(ROOT)
        print(json.dumps(report, ensure_ascii=True))
        return 0 if report["result"] == "pass" else 1
    except Exception:
        print(json.dumps({"scope": "Q15_public_candidates_only", "result": "fail", "reason": "check_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
