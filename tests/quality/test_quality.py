from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import check_quality as quality


def put(root, path, content):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


def git(root, *args):
    result = subprocess.run([shutil.which("git", path=os.defpath), "-c", "core.hooksPath=/dev/null", *args],
                            cwd=root, env={"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1",
                                           "GIT_CONFIG_GLOBAL": os.devnull},
                            capture_output=True, timeout=5, check=False)
    if result.returncode:
        raise AssertionError("synthetic_git_setup_failed")


def public_fixture(root):
    git(root, "init", "--quiet")
    put(root, ".gitignore", "private/\n*.local.yaml\n__pycache__/\n")
    put(root, "README.md", "synthetic public fixture\n")
    git(root, "add", "--", "README.md")
    entries = {}
    for name in quality.BASELINE_PATHS:
        content = ("synthetic contract: " + name + "\n").encode()
        put(root, name, content)
        entries[name] = sha256(content).hexdigest()
    put(root, "docs/contracts/baseline-v1.json", json.dumps({"version": 1, "files": entries}))
    lock = {"schema_version": 1, "platform": "linux/arm64", "python_packages": [],
            "python": {"image": "python@sha256:" + "a" * 64, "version": "3.13.17",
                       "source_revision": "a" * 40, "source_sha256": "a" * 64, "license": "PSF"},
            "postgres": {"image": "postgres@sha256:" + "b" * 64, "version": "18.6",
                         "source_revision": "b" * 40, "license": "PostgreSQL"},
            "inventory": "docs/evidence/synthetic-runtime.json"}
    put(root, "config/runtime-lock.json", json.dumps(lock))
    inventory = {"all_dpkg_packages_copyright_readable": True, "python_license_sha256": "c" * 64,
                 "images": {name: {"image": lock[name]["image"], "packages": ["synthetic-package\t1"],
                                   "license_notice_sha256": ["c" * 64 + "  /usr/share/doc/synthetic/copyright"]}
                            for name in ("python", "postgres")}}
    put(root, lock["inventory"], json.dumps(inventory))
    put(root, "pyproject.toml", '[project]\nname="synthetic"\nrequires-python=">=3.13,<3.14"\ndependencies=[]\n')
    put(root, "containers/Dockerfile.synthetic", quality.expected_dockerfile(lock))
    put(root, "containers/compose.synthetic.yaml", quality.expected_compose(lock))
    put(root, "config/ci/quality.workflow.example.yml", quality.expected_ci(lock, quality.CI_ACTIONS[0][1], quality.CI_ACTIONS[1][1]))
    put(root, "docs/development/ci-definition.md", "../../config/ci/quality.workflow.example.yml .github/workflows\n")
    put(root, "config/market-storage-lock.json", json.dumps(quality.MARKET_STORAGE_LOCK))
    put(root, "containers/Dockerfile.market-storage", quality.MARKET_STORAGE_DOCKERFILE)
    put(root, "containers/requirements.market-storage.txt", quality.MARKET_STORAGE_REQUIREMENTS)
    return lock


def reasons(report):
    return {item["reason"] for item in report["findings"]}


class PublicRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="qh-quality-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.lock = public_fixture(self.root)

    def test_market_storage_exact_pin_and_offline_definition(self):
        path = self.root / "config/market-storage-lock.json"
        original = path.read_text()
        value = json.loads(original)
        value["wheel_sha256"] = "a" * 64
        path.write_text(json.dumps(value))
        self.assertIn("market_storage_lock_drift", reasons(quality.inspect_repository(self.root)))
        path.write_text(original)
        put(self.root, "containers/requirements.market-storage.txt", "pyarrow>=26\n")
        self.assertIn("market_storage_dependency_drift", reasons(quality.inspect_repository(self.root)))
        put(self.root, "containers/requirements.market-storage.txt", quality.MARKET_STORAGE_REQUIREMENTS)
        put(self.root, "containers/Dockerfile.market-storage", quality.MARKET_STORAGE_DOCKERFILE.replace('"--no-index", ', ''))
        self.assertIn("market_storage_container_drift", reasons(quality.inspect_repository(self.root)))

    def test_tracked_and_untracked_public_files_pass_without_execution(self):
        marker = self.root / "must-not-exist"
        put(self.root, "scripts/untrusted.py", "raise RuntimeError('must_not_execute')\n")
        put(self.root, "src/quantharbor/domain/example.py", "from decimal import Decimal\nimport re\np=re.compile('x')\n")
        put(self.root, "config/connections.example.yaml", "api_key: CHANGE_ME\naccount: synthetic\n")
        self.assertEqual(quality.inspect_repository(self.root)["result"], "pass")
        self.assertFalse(marker.exists())

    def test_ignored_private_and_operational_files_are_never_opened(self):
        put(self.root, "private/not-public.txt", "DO_NOT_READ_SYNTHETIC_CANARY")
        put(self.root, "config/connections.local.yaml", "DO_NOT_READ_SYNTHETIC_CANARY")
        original = quality._read_public
        read_paths = []

        def read(fd, path):
            read_paths.append(path)
            self.assertFalse(path.startswith("private/") or ".local." in path)
            return original(fd, path)

        with patch.object(quality, "_read_public", side_effect=read):
            report = quality.inspect_repository(self.root)
        self.assertEqual(report["result"], "pass")
        self.assertNotIn("config/connections.local.yaml", read_paths)

    def test_standard_global_exclude_is_preserved_without_scanning_ignored_content(self):
        put(self.root, "docs/ignored-personal.md", "DO_NOT_READ_SYNTHETIC_GLOBAL_IGNORE_CANARY")
        with tempfile.TemporaryDirectory(prefix="qh-quality-synthetic-home-") as raw:
            home = Path(raw).resolve()
            put(home, "exclude", "docs/ignored-personal.md\n")
            put(home, ".gitconfig", "[core]\n\texcludesFile = " + str(home / "exclude") + "\n")
            original = quality._read_public

            def read(fd, path):
                self.assertNotEqual(path, "docs/ignored-personal.md")
                return original(fd, path)

            with patch.dict(os.environ, {"HOME": str(home), "XDG_CONFIG_HOME": str(home / "xdg")}), \
                    patch.object(quality, "_read_public", side_effect=read):
                report = quality.inspect_repository(self.root)
            self.assertEqual(report["result"], "pass")

    def test_protected_unclassified_and_tracked_ignored_names_reject_before_open(self):
        for name in ("config/account.yaml", "personal.txt", "docs/secrets.json", "docs/keys.pem", ".env",
                     "docs/.env/hidden.txt", "docs/keys/synthetic.txt", "src/quantharbor/runtime/operational.json"):
            put(self.root, name, "DO_NOT_READ_SYNTHETIC_CANARY")
        put(self.root, "private/tracked.txt", "DO_NOT_READ_SYNTHETIC_CANARY")
        git(self.root, "add", "--force", "--", "private/tracked.txt")
        blocked = {"config/account.yaml", "personal.txt", "docs/secrets.json", "docs/keys.pem", ".env",
                   "private/tracked.txt", "docs/.env/hidden.txt", "docs/keys/synthetic.txt",
                   "src/quantharbor/runtime/operational.json"}
        original = quality._read_public

        def read(fd, path):
            self.assertNotIn(path, blocked)
            return original(fd, path)

        with patch.object(quality, "_read_public", side_effect=read):
            report = quality.inspect_repository(self.root)
        self.assertTrue({"protected_path", "unclassified_candidate"} <= reasons(report))

    def test_symlink_parent_symlink_hardlink_and_escape_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="qh-quality-outside-") as raw:
            outside = Path(raw).resolve()
            put(outside, "unread.txt", "DO_NOT_READ_SYNTHETIC_CANARY")
            (self.root / "docs/alias.md").symlink_to(outside / "unread.txt")
            (self.root / "docs/alias-directory").symlink_to(outside, target_is_directory=True)
            os.link(outside / "unread.txt", self.root / "docs/hardlink.md")
            report = quality.inspect_repository(self.root)
            self.assertIn("unsafe_file_access", reasons(report))
            self.assertIn("file_type_or_hardlink_denied", reasons(report))
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                for path in ("docs/alias-directory/unread.txt", "../unread.txt", str(outside / "unread.txt")):
                    with self.subTest(path_type="synthetic"), self.assertRaises(quality.QualityFailure):
                        quality._read_public(fd, path)
            finally:
                os.close(fd)

    def test_oversize_unknown_binary_and_non_utf8_fail_without_raw_output(self):
        put(self.root, "docs/huge.txt", b"x" * (quality.MAX_FILE_BYTES + 1))
        put(self.root, "docs/invalid.txt", b"\xffSYNTHETIC_BINARY_CANARY")
        put(self.root, "docs/binary.txt", b"\x00SYNTHETIC_BINARY_CANARY")
        put(self.root, "docs/unknown.bin", b"DO_NOT_READ_SYNTHETIC_CANARY")
        report = quality.inspect_repository(self.root)
        self.assertTrue({"file_size_limit", "non_utf8_or_binary", "unsupported_file_type"} <= reasons(report))
        self.assertNotIn("SYNTHETIC_BINARY_CANARY", json.dumps(report))

    def test_nul_filename_inventory_handles_newlines_without_echoing_filename(self):
        put(self.root, "docs/name\nSYNTHETIC_PATH_CANARY.md", "public fixture")
        report = quality.inspect_repository(self.root)
        self.assertIn("unsafe_path", reasons(report))
        self.assertNotIn("SYNTHETIC_PATH_CANARY", json.dumps(report))

    def test_secret_shapes_are_detected_and_raw_values_are_never_reported(self):
        values = ["gh" + "p_" + "A" * 36, "sk-" + "proj-" + "A" * 48,
                  "xox" + "b-" + "1" * 12 + "-" + "2" * 12 + "-" + "A" * 24,
                  "-----BEGIN " + "PRIVATE KEY-----", "AK" + "IA" + "A" * 16]
        put(self.root, "docs/canaries.txt", "\n".join(values))
        report = quality.inspect_repository(self.root)
        self.assertTrue({"secret_private_key", "secret_github_token", "secret_slack_token",
                         "secret_api_token", "secret_aws_access_id"} <= reasons(report))
        for value in values:
            self.assertNotIn(value, json.dumps(report))

    def test_regex_definitions_variable_names_and_explicit_dummies_are_not_secrets(self):
        put(self.root, "docs/synthetic.example.yaml", "api_key: CHANGE_ME\nCLAUDE_CODE_OAUTH_TOKEN: dummy\n")
        put(self.root, "scripts/regex.py", 'pattern = r"gh[pousr]_[A-Za-z0-9]{36}"\n')
        self.assertEqual(quality.inspect_repository(self.root)["result"], "pass")

    def test_domain_boundary_and_syntax_are_static_checks(self):
        put(self.root, "scripts/bad_syntax.py", "def broken(:\n")
        put(self.root, "src/quantharbor/domain/io.py", "open('SYNTHETIC_MUST_NOT_OPEN')\n")
        put(self.root, "src/quantharbor/domain/imports.py", "from quantharbor.runtime import settings\n")
        put(self.root, "src/quantharbor/domain/escape.py", "from ..runtime import settings\n")
        report = quality.inspect_repository(self.root)
        self.assertTrue({"python_syntax_invalid", "domain_io_boundary", "domain_import_boundary"} <= reasons(report))

    def test_baseline_drift_and_manifest_path_attack_do_not_regenerate_or_open_targets(self):
        path = next(iter(quality.BASELINE_PATHS))
        original_manifest = (self.root / "docs/contracts/baseline-v1.json").read_bytes()
        put(self.root, path, "synthetic drift\n")
        self.assertIn("baseline_hash_mismatch", reasons(quality.inspect_repository(self.root)))
        self.assertEqual((self.root / "docs/contracts/baseline-v1.json").read_bytes(), original_manifest)
        baseline = json.loads(original_manifest)
        baseline["files"]["../private/key.pem"] = "a" * 64
        put(self.root, "docs/contracts/baseline-v1.json", json.dumps(baseline))
        self.assertIn("baseline_schema_or_file_set", reasons(quality.inspect_repository(self.root)))

    def test_dependency_changes_and_inventory_pin_or_notice_changes_fail(self):
        put(self.root, "pyproject.toml", '[project]\nrequires-python=">=3.13,<3.14"\ndependencies=["synthetic-sdk"]\n')
        self.assertIn("dependency_policy_changed", reasons(quality.inspect_repository(self.root)))
        public_fixture(self.root)
        inventory = json.loads((self.root / self.lock["inventory"]).read_text())
        inventory["images"]["python"]["image"] = "python@sha256:" + "d" * 64
        put(self.root, self.lock["inventory"], json.dumps(inventory))
        self.assertIn("inventory_image_or_notice_mismatch", reasons(quality.inspect_repository(self.root)))
        inventory["images"]["python"]["image"] = self.lock["python"]["image"]
        inventory["images"]["python"]["license_notice_sha256"] = []
        put(self.root, self.lock["inventory"], json.dumps(inventory))
        self.assertIn("inventory_image_or_notice_mismatch", reasons(quality.inspect_repository(self.root)))

    def test_pins_platform_active_ci_permissions_secrets_and_commands_fail_closed(self):
        put(self.root, "containers/Dockerfile.synthetic", quality.expected_dockerfile(self.lock).replace(
            self.lock["python"]["image"], "python:latest"))
        self.assertIn("container_definition_drift", reasons(quality.inspect_repository(self.root)))
        original = quality.expected_ci(self.lock, quality.CI_ACTIONS[0][1], quality.CI_ACTIONS[1][1])
        variants = (original.replace("contents: read", "contents: write"),
                    original.replace(quality.CI_ACTIONS[0][1], "main"),
                    original.replace(quality.CI_ACTIONS[0][1], "c" * 40),
                    original.replace(quality.CI_ACTIONS[1][1], "d" * 40),
                    original.replace("architecture: arm64", "architecture: x64"),
                    original + "\n    secrets: inherit\n",
                    original.replace("run: python3.13 -I -S scripts/check_quality.py", "run: python3.13 -I -S scripts/check_quality.py#;echo unsafe"))
        for changed in variants:
            put(self.root, "config/ci/quality.workflow.example.yml", changed)
            self.assertIn("inactive_ci_policy_drift", reasons(quality.inspect_repository(self.root)))
        put(self.root, ".github/workflows/quality.yml", original)
        self.assertIn("protected_path", reasons(quality.inspect_repository(self.root)))

    def test_cli_guard_refuses_missing_flags_before_shadow_stdlib_import(self):
        # site startup 후의 guard는 이미 실행된 startup 코드를 되돌릴 수 없다.
        # 여기서는 공격 site/PYTHONPATH 없이 script-local import 이전 거부를 검사한다.
        source = Path(quality.__file__).read_bytes()
        put(self.root, "scripts/check_quality.py", source)
        marker = self.root / "shadow-marker"
        shadow = "with open(" + repr(str(marker)) + ", 'w') as f: f.write('synthetic')\n"
        put(self.root, "scripts/ast.py", shadow)
        put(self.root, "scripts/json.py", shadow)
        for flags in ([], ["-I"], ["-S"]):
            result = subprocess.run([sys.executable, *flags, str(self.root / "scripts/check_quality.py")],
                                    cwd=self.root, env={"PATH": os.defpath, "HOME": str(self.root)},
                                    capture_output=True, text=True, timeout=5, check=False)
            with self.subTest(flags=flags):
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["reason"], "isolated_python_required")
                self.assertEqual(result.stderr, "")
                self.assertFalse(marker.exists())

    def test_isolated_cli_excludes_script_pythonpath_and_sitecustomize_code(self):
        # 실제 안전 진입 명령은 interpreter startup부터 공격 경로를 제외한다.
        put(self.root, "scripts/check_quality.py", Path(quality.__file__).read_bytes())
        with tempfile.TemporaryDirectory(prefix="qh-quality-startup-canary-") as raw:
            attacker = Path(raw).resolve()
            markers = []
            for directory, name in ((self.root / "scripts", "ast.py"), (self.root / "scripts", "json.py"),
                                    (attacker, "ast.py"), (attacker, "json.py"), (attacker, "sitecustomize.py")):
                marker = attacker / ("marker-" + str(len(markers)))
                markers.append(marker)
                content = "with open(" + repr(str(marker)) + ", 'w') as f: f.write('synthetic')\n"
                put(directory, name, content)
            result = subprocess.run([sys.executable, "-I", "-S", str(self.root / "scripts/check_quality.py")],
                                    cwd=self.root, env={"PATH": os.defpath, "HOME": str(attacker),
                                                       "PYTHONPATH": str(attacker)},
                                    capture_output=True, text=True, timeout=5, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["result"], "pass")
            self.assertEqual(result.stderr, "")
            self.assertTrue(all(not marker.exists() for marker in markers), "startup_or_shadow_canary_executed")

    def test_non_ascii_control_whitespace_and_docker_directives_fail_closed(self):
        ci = quality.expected_ci(self.lock, quality.CI_ACTIONS[0][1], quality.CI_ACTIONS[1][1])
        for space in ("\u00a0", "\u2007", "\u202f", "\t"):
            changed = ci.replace("scripts/check_quality.py", "scripts/check_quality.py" + space + "#;printf synthetic")
            put(self.root, "config/ci/quality.workflow.example.yml", changed)
            self.assertIn("control_whitespace_invalid", reasons(quality.inspect_repository(self.root)))
        put(self.root, "config/ci/quality.workflow.example.yml", ci)
        dockerfile = quality.expected_dockerfile(self.lock)
        for directive in ("# syntax=docker/dockerfile:1", "# escape=\\", "# check=skip=all"):
            put(self.root, "containers/Dockerfile.synthetic", directive + "\n" + dockerfile)
            self.assertIn("docker_parser_directive_denied", reasons(quality.inspect_repository(self.root)))

    def test_ascii_inline_comments_are_not_removed_from_execution_instructions(self):
        dockerfile = quality.expected_dockerfile(self.lock)
        put(self.root, "containers/Dockerfile.synthetic", dockerfile.replace(
            "PYTHONUNBUFFERED=1", "PYTHONUNBUFFERED=1 # ADDED=synthetic"))
        self.assertIn("container_definition_drift", reasons(quality.inspect_repository(self.root)))
        put(self.root, "containers/Dockerfile.synthetic", "# ordinary synthetic comment\n" + dockerfile)
        ci = quality.expected_ci(self.lock, quality.CI_ACTIONS[0][1], quality.CI_ACTIONS[1][1])
        put(self.root, "config/ci/quality.workflow.example.yml", ci.replace(
            "scripts/check_quality.py", "scripts/check_quality.py #;printf synthetic"))
        self.assertIn("inactive_ci_policy_drift", reasons(quality.inspect_repository(self.root)))
        put(self.root, "config/ci/quality.workflow.example.yml", "# ordinary synthetic comment\n" + ci)
        self.assertEqual(quality.inspect_repository(self.root)["result"], "pass")

    def test_cli_redacts_input_unexpected_exception_and_absolute_paths(self):
        put(self.root, "docs/secret-shape.txt", "gh" + "p_" + "A" * 36)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(quality, "ROOT", self.root), redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(quality.main([]), 1)
        self.assertNotIn(str(self.root), stdout.getvalue() + stderr.getvalue())
        self.assertNotIn("gh" + "p_" + "A" * 36, stdout.getvalue() + stderr.getvalue())
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(quality.main(["SYNTHETIC_ARGUMENT_CANARY"]), 2)
        self.assertNotIn("SYNTHETIC_ARGUMENT_CANARY", stdout.getvalue())
        stdout = io.StringIO()
        with patch.object(quality, "inspect_repository", side_effect=RuntimeError("SYNTHETIC_EXCEPTION_CANARY")), redirect_stdout(stdout):
            self.assertEqual(quality.main([]), 1)
        self.assertNotIn("SYNTHETIC_EXCEPTION_CANARY", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
