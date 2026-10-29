#!/usr/bin/env python3
"""SEC-DEC-002: 새 합성 canary 저장소만 준비한다. 실제 금융값은 읽지 않는다.

운영: python3.13 -I -S scripts/bootstrap_paper_storage.py bootstrap
별도 승인 통합: ... synthetic-integration (구현/단위시험 중 실행 금지)
"""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
HDIUTIL = "/usr/bin/hdiutil"
DISKUTIL = "/usr/sbin/diskutil"
CAPTURE_LIMIT = 256 * 1024  # stdout+stderr 합계; 초과하면 즉시 중단
IMAGE_LIMIT = 272 * 1024 * 1024  # 256MiB payload + bounded UDIF/encryption overhead
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
DEVICE = re.compile(r"/dev/disk[0-9]+(?:s[0-9]+)*\Z")
WHOLE_DEVICE = re.compile(r"/dev/disk[0-9]+\Z")
CANARY_PREFIX = b"QuantHarbor SEC-paper-vault synthetic canary v1\n"
REASONS = frozenset({
    "arguments_denied", "isolated_python_required", "macos_required", "root_denied",
    "path_boundary", "owner_or_permissions", "existing_target", "identity_changed",
    "file_boundary", "size_limit", "command_failed", "command_timeout",
    "command_output_limit", "command_cancelled", "invalid_plist", "not_encrypted", "mount_binding",
    "device_binding", "not_detached", "canary_mismatch", "copy_mismatch",
    "unexpected_failure",
})


class VaultError(Exception):
    def __init__(self, reason):
        self.reason = reason if reason in REASONS else "unexpected_failure"
        super().__init__(self.reason)


class VaultCancelled(BaseException):
    """일반 Exception 처리에 삼켜지지 않는 SIGTERM 취소."""


def cancel_sigterm(signum, frame):
    # 반복 SIGTERM은 정리/보고를 중단하지 않는다. 최외곽 scope가 이전 handler를 복원한다.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise VaultCancelled()


@contextmanager
def sigterm_cancellation():
    """CLI/main thread용. main과 runner가 중첩되어도 취소 scope는 하나다."""
    previous = signal.getsignal(signal.SIGTERM)
    if previous is cancel_sigterm:
        yield
        return
    signal.signal(signal.SIGTERM, cancel_sigterm)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def require(condition, reason):
    if not condition:
        raise VaultError(reason)


def identity(info):
    return info.st_dev, info.st_ino


def private(info, directory=False):
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
            and (directory or info.st_nlink == 1), "owner_or_permissions")


def external_path(value):
    """lexical 검사 후 각 component를 nofollow dirfd로 연다. resolve로 링크를 숨기지 않는다."""
    require(type(value) is str and value.startswith("/") and len(value) < 800
            and not any(ord(c) < 32 or ord(c) == 127 for c in value), "path_boundary")
    parts = value.split("/")[1:]
    require(bool(parts) and all(p not in ("", ".", "..") for p in parts), "path_boundary")
    path = Path(value)
    require(not path.is_relative_to(ROOT) and path != ROOT
            and not path.is_relative_to(Path("/dev")), "path_boundary")
    return path


@contextmanager
def parent_directory(path, synthetic=False, create=False):
    """부모 내용은 열거하지 않는다. 누락된 부모만 새로 만들고 기존 메타데이터를 검사한다."""
    path = external_path(str(path))
    fd = os.open("/", DIR_FLAGS)
    try:
        current = Path("/")
        for component in path.parts[1:]:
            current /= component
            try:
                child = os.open(component, DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                require(create, "path_boundary")
                os.mkdir(component, 0o700, dir_fd=fd)
                os.fsync(fd)
                child = os.open(component, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            sticky_tmp = (synthetic and current == Path("/private/tmp")
                          and info.st_uid == 0 and info.st_mode & stat.S_ISVTX)
            require(info.st_uid in (0, os.getuid())
                    and (not info.st_mode & 0o022 or sticky_tmp), "owner_or_permissions")
            # 다른 checkout/worktree도 저장소 경계다. .git 내용은 읽지 않는다.
            try:
                os.stat(".git", dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise VaultError("path_boundary")
        # 합성 /private/tmp는 조상으로만 허용한다. 최종 부모는 항상 사용자 전용이다.
        private(os.fstat(fd), directory=True)
        yield fd
    finally:
        os.close(fd)


def absent(fd, name):
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise VaultError("existing_target")


@sigterm_cancellation()
def run_bounded(argv, cwd, password=None, timeout=30):
    """내부 고정 argv만 받는다. shell/환경 상속/임시 출력파일/무제한 communicate 없음."""
    require(argv[0] in (HDIUTIL, DISKUTIL), "arguments_denied")
    require(password is None or (type(password) is bytes and len(password) == 65
                                and password[-1:] == b"\0"), "arguments_denied")
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C",
           "HOME": pwd.getpwuid(os.getuid()).pw_dir}
    proc = None
    completed = False
    try:
        # Popen이 자식을 만든 직후 proc 대입 전에 취소되어 group을 잃지 않도록 한다.
        cancelled = False
        def defer_cancel(signum, frame):
            nonlocal cancelled
            cancelled = True
        previous_handler = signal.signal(signal.SIGTERM, defer_cancel)
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, env=env, stdin=subprocess.PIPE if password is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True, start_new_session=True)
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
        if cancelled:
            cancel_sigterm(signal.SIGTERM, None)
        if password is not None:
            try:
                proc.stdin.write(password)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                raise VaultError("command_failed") from None
        output = bytearray()
        captured = 0
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            for stream in (proc.stdout, proc.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                require(remaining > 0, "command_timeout")
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fd, 16384)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        captured += len(chunk)
                        require(captured <= CAPTURE_LIMIT, "command_output_limit")
                        if key.fileobj is proc.stdout:
                            output.extend(chunk)
            remaining = deadline - time.monotonic()
            require(remaining > 0, "command_timeout")
            try:
                code = proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise VaultError("command_timeout") from None
        require(code == 0, "command_failed")
        completed = True
        return bytes(output)
    finally:
        if proc is not None:
            # timeout/cancel 상태는 unknown이다. 디스크 해제/삭제/재시도하지 않는다.
            cleanup_cancelled = False
            def defer_cleanup_cancel(signum, frame):
                nonlocal cleanup_cancelled
                cleanup_cancelled = True
            previous_handler = signal.signal(signal.SIGTERM, defer_cleanup_cancel)
            try:
                if not completed:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if proc.poll() is None:
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        raise VaultError("command_timeout") from None
            finally:
                try:
                    for stream in (proc.stdin, proc.stdout, proc.stderr):
                        if stream is not None:
                            stream.close()
                finally:
                    signal.signal(signal.SIGTERM, previous_handler)
            # 정리 중 첫 SIGTERM도 잃지 않는다. 정리를 마친 뒤 후속 작업을 막는다.
            if cleanup_cancelled:
                cancel_sigterm(signal.SIGTERM, None)


def plist(data):
    require(len(data) <= CAPTURE_LIMIT, "command_output_limit")
    try:
        value = plistlib.loads(data)
    except Exception:
        raise VaultError("invalid_plist") from None
    require(type(value) is dict, "invalid_plist")
    return value


class Vault:
    """한 프로세스의 새 자원만 취급한다. 임의 기존 이미지/장치 재개 기능은 없다."""

    def __init__(self, parent, runner=run_bounded, synthetic=False, progress=None):
        self.parent = external_path(str(parent))
        self.runner = runner
        self.synthetic = synthetic
        self.progress = progress or (lambda stage: None)
        self.stage = "preflight"
        self.name = "qh-paper-" + uuid.uuid4().hex
        self.path = self.parent / self.name
        self.fd = None
        self.files = {}
        self.mounts = {}
        self.password = None

    def step(self, name):
        self.stage = name
        self.progress(name)

    def check_run(self):
        with parent_directory(self.parent, self.synthetic) as parent_fd:
            info = os.stat(self.name, dir_fd=parent_fd, follow_symlinks=False)
            private(info, directory=True)
            require(identity(info) == identity(os.fstat(self.fd)), "identity_changed")

    def command(self, *args, auth=False, timeout=30, diskutil=False):
        self.check_run()
        argv = [DISKUTIL if diskutil else HDIUTIL, *map(str, args)]
        if auth:
            argv.append("-stdinpass" if self.synthetic else "-agentpass")
        return self.runner(argv, self.path, password=self.password if auth and self.synthetic else None,
                           timeout=timeout)

    def file_info(self, name):
        self.check_run()
        info = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        private(info)
        require(0 < info.st_size <= IMAGE_LIMIT, "size_limit")
        if name in self.files:
            require(identity(info) == self.files[name], "identity_changed")
        return info

    @contextmanager
    def image_file(self, name):
        info = self.file_info(name)
        fd = os.open(name, FILE_FLAGS, dir_fd=self.fd)
        try:
            private(os.fstat(fd))
            require(identity(info) == identity(os.fstat(fd)), "identity_changed")
            yield fd
            require(identity(self.file_info(name)) == identity(info), "identity_changed")
        finally:
            os.close(fd)

    def encrypted(self, name):
        self.file_info(name)
        result = plist(self.command("isencrypted", self.path / name, "-plist"))
        require(result.get("encrypted") is True, "not_encrypted")
        self.file_info(name)

    def images(self):
        images = plist(self.command("info", "-plist")).get("images")
        require(type(images) is list and len(images) <= 128
                and all(type(image) is dict for image in images), "mount_binding")
        # 모든 entry를 먼저 검증한다. 누락/손상된 무관 이미지도 '닫힘' 근거가 아니다.
        for image in images:
            self.metadata_path(image.get("image-path"))
            self.entities(image)
        return images

    @staticmethod
    def metadata_path(value):
        """info의 경로 문자열만 검사한다. 다른 이미지/마운트의 파일은 열지 않는다."""
        require(type(value) is str and value.startswith("/") and len(value) < 4096
                and all(part not in ("", ".", "..") for part in value.split("/")[1:])
                and not any(ord(c) < 32 or ord(c) == 127 for c in value), "mount_binding")

    @staticmethod
    def entities(result):
        entities = result.get("system-entities")
        require(type(entities) is list and 1 <= len(entities) <= 32
                and all(type(e) is dict for e in entities), "device_binding")
        devices = [e.get("dev-entry") for e in entities]
        require(all(type(d) is str and DEVICE.fullmatch(d) for d in devices)
                and len(set(devices)) == len(devices), "device_binding")
        for entity in entities:
            if "mount-point" in entity:
                Vault.metadata_path(entity["mount-point"])
        return entities

    def closed(self, name, devices=()):
        require(not any(image.get("image-path") == str(self.path / name)
                        or any(e.get("dev-entry") in devices
                               for e in image.get("system-entities", []) if type(e) is dict)
                        for image in self.images()), "not_detached")
        require(all(not os.path.lexists(d) for d in devices), "not_detached")

    def empty_mount(self, mount):
        self.check_run()
        fd = os.open(mount, DIR_FLAGS, dir_fd=self.fd)
        try:
            info = os.fstat(fd)
            private(info, directory=True)
            require(identity(info) == self.mounts[mount] and info.st_dev == os.fstat(self.fd).st_dev
                    and not os.path.ismount(self.path / mount) and not os.listdir(fd), "mount_binding")
        finally:
            os.close(fd)

    def attach(self, name, mount, initialize=False):
        self.encrypted(name)
        self.closed(name)
        self.empty_mount(mount)
        result = plist(self.command("attach", self.path / name, "-plist", "-mountpoint",
                                    self.path / mount, "-nobrowse", "-owners", "on", "-readwrite",
                                    auth=True, timeout=180))
        entities = self.entities(result)
        roots = [e["dev-entry"] for e in entities
                 if e.get("content-hint") == "GUID_partition_scheme"
                 and WHOLE_DEVICE.fullmatch(e["dev-entry"])]
        require(len(roots) == 1, "device_binding")
        binding = {"name": name, "mount": mount, "entities": entities, "detach": roots[0]}
        if initialize:
            self.initialize_mount_permissions(binding)
        self.validate_mount(binding)
        return binding

    def initialize_mount_permissions(self, binding):
        """새 원본 첫 마운트에만 적용. 전체 결속 확인 뒤 fd로 0700을 강제한다."""
        require(self.stage == "canary" and binding["name"] == "vault.dmg"
                and binding["mount"] == "mount", "mount_binding")
        before = self.validate_mount(binding, allow_initial_permissions=True)
        fd = os.open(binding["mount"], DIR_FLAGS, dir_fd=self.fd)
        try:
            require(identity(os.fstat(fd)) == identity(before), "identity_changed")
            self.validate_mount(binding, allow_initial_permissions=True)
            os.fchmod(fd, 0o700)
            os.fsync(fd)
            private(os.fstat(fd), directory=True)
            self.validate_mount(binding)
        finally:
            os.close(fd)

    def validate_mount(self, binding, allow_initial_permissions=False):
        """attach 반환 + 현재 이미지 연결 + diskutil + 실제 dev_t를 모두 비교한다."""
        name, mount, entities = binding["name"], binding["mount"], binding["entities"]
        self.file_info(name)
        target = str(self.path / mount)
        expected = {(e["dev-entry"], e.get("mount-point")) for e in entities}
        require(sum(e.get("mount-point") == target for e in entities) == 1
                and all(e.get("mount-point") in (None, target) for e in entities), "mount_binding")
        images = self.images()
        matching = [i for i in images if i.get("image-path") == str(self.path / name)]
        require(len(matching) == 1, "mount_binding")
        actual_entities = self.entities(matching[0])
        require({(e["dev-entry"], e.get("mount-point")) for e in actual_entities} == expected,
                "mount_binding")
        expected_devices = {e["dev-entry"] for e in entities}
        for image in images:
            if image is matching[0]:
                continue
            require(not any(type(e) is dict and (e.get("dev-entry") in expected_devices
                            or e.get("mount-point") == target)
                            for e in image.get("system-entities", [])), "mount_binding")
        volume = next(e["dev-entry"] for e in entities if e.get("mount-point") == target)
        info = plist(self.command("info", "-plist", target, diskutil=True))
        require(info.get("DeviceNode") == volume and info.get("MountPoint") == target
                and info.get("FilesystemType") == "apfs" and info.get("GlobalPermissionsEnabled") is True
                and info.get("Writable") is True and info.get("VolumeName") == "QHPaperVault"
                and info.get("ReadOnlyMedia", False) is False
                and info.get("ReadOnlyVolume", False) is False, "mount_binding")
        try:
            uuid.UUID(info.get("VolumeUUID", ""))
        except (ValueError, TypeError, AttributeError):
            raise VaultError("mount_binding") from None
        if "uuid" in binding:
            require(binding["uuid"] == info["VolumeUUID"], "mount_binding")
        binding["uuid"] = info["VolumeUUID"]
        for device in expected_devices:
            node = os.lstat(device)
            require(stat.S_ISBLK(node.st_mode) and node.st_uid in (0, os.getuid()) and node.st_nlink == 1,
                    "device_binding")
        mount_info = os.lstat(target)
        if allow_initial_permissions:
            require(stat.S_ISDIR(mount_info.st_mode) and mount_info.st_uid == os.getuid()
                    and stat.S_IMODE(mount_info.st_mode) in (0o700, 0o755), "owner_or_permissions")
        else:
            private(mount_info, directory=True)
        device_info = os.lstat(volume)
        require(os.path.ismount(target) and mount_info.st_dev == device_info.st_rdev
                and mount_info.st_dev != os.fstat(self.fd).st_dev, "device_binding")
        return mount_info

    @contextmanager
    def mounted_data(self, binding, create=False):
        before = self.validate_mount(binding)
        root_fd = os.open(binding["mount"], DIR_FLAGS, dir_fd=self.fd)
        data_fd = None
        try:
            require(identity(os.fstat(root_fd)) == identity(before), "identity_changed")
            if create:
                absent(root_fd, "data")
                os.mkdir("data", 0o700, dir_fd=root_fd)
                os.fsync(root_fd)
            data_fd = os.open("data", DIR_FLAGS, dir_fd=root_fd)
            private(os.fstat(data_fd), directory=True)
            require(os.fstat(data_fd).st_dev == before.st_dev, "device_binding")
            # no writes before the full binding check, including after opening dirfds
            self.validate_mount(binding)
            yield data_fd
            self.validate_mount(binding)
        finally:
            if data_fd is not None:
                os.close(data_fd)
            os.close(root_fd)

    def write_canary(self, binding):
        canary = CANARY_PREFIX + os.urandom(32)
        with self.mounted_data(binding, create=True) as data_fd:
            write_new(data_fd, "bootstrap-canary.bin", canary)
        return sha256(canary).hexdigest()

    def read_canary(self, binding, digest):
        with self.mounted_data(binding) as data_fd:
            fd = os.open("bootstrap-canary.bin", FILE_FLAGS, dir_fd=data_fd)
            try:
                info = os.fstat(fd)
                private(info)
                require(info.st_dev == os.fstat(data_fd).st_dev
                        and info.st_size == len(CANARY_PREFIX) + 32, "file_boundary")
                content = os.read(fd, len(CANARY_PREFIX) + 33)
                require(sha256(content).hexdigest() == digest, "canary_mismatch")
            finally:
                os.close(fd)

    def detach(self, binding):
        self.validate_mount(binding)
        self.command("detach", binding["detach"], timeout=60)
        self.closed(binding["name"], tuple(e["dev-entry"] for e in binding["entities"]))
        self.empty_mount(binding["mount"])

    def digest(self, name):
        with self.image_file(name) as fd:
            result = sha256()
            total = 0
            while chunk := os.read(fd, 1024 * 1024):
                total += len(chunk)
                require(total <= IMAGE_LIMIT, "size_limit")
                result.update(chunk)
            require(total == os.fstat(fd).st_size, "copy_mismatch")
            return result.hexdigest()

    def copy_closed(self, source, target):
        self.closed(source)
        self.closed(target)
        self.encrypted(source)
        before = self.digest(source)
        absent(self.fd, target)
        with self.image_file(source) as src:
            dst = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                          0o600, dir_fd=self.fd)
            try:
                private(os.fstat(dst))
                require(identity(os.fstat(dst)) != identity(os.fstat(src)), "copy_mismatch")
                total = 0
                while chunk := os.read(src, 1024 * 1024):
                    total += len(chunk)
                    require(total <= IMAGE_LIMIT, "size_limit")
                    write_all(dst, chunk)
                os.fsync(dst)
                self.files[target] = identity(os.fstat(dst))
            finally:
                os.close(dst)
        os.fsync(self.fd)
        self.closed(source)
        self.closed(target)
        require(self.digest(source) == before == self.digest(target), "copy_mismatch")
        self.encrypted(target)
        return before

    def execute(self):
        """운영/합성 각각 단일 실행. 실패하면 새 CLI 실행으로 기존 자원을 재사용하지 않는다."""
        require(sys.platform == "darwin", "macos_required")
        require(os.getuid() != 0, "root_denied")
        old_umask = os.umask(0o077)
        try:
            with parent_directory(self.parent, self.synthetic, create=True) as parent_fd:
                absent(parent_fd, self.name)
                os.mkdir(self.name, 0o700, dir_fd=parent_fd)
                os.fsync(parent_fd)
                self.fd = os.open(self.name, DIR_FLAGS, dir_fd=parent_fd)
            self.check_run()
            for mount in ("mount", "restore-mount"):
                absent(self.fd, mount)
                os.mkdir(mount, 0o700, dir_fd=self.fd)
                self.mounts[mount] = identity(os.stat(mount, dir_fd=self.fd, follow_symlinks=False))
            os.fsync(self.fd)
            if self.synthetic:
                # 합성 전용. 파일/env/argv/로그/운영에 재사용하지 않는 일회성 메모리 값.
                self.password = os.urandom(32).hex().encode("ascii") + b"\0"
            self.step("create")
            absent(self.fd, "vault.dmg")
            self.command("create", "-size", "256m", "-type", "UDIF", "-fs", "APFS",
                         "-encryption", "AES-256", "-volname", "QHPaperVault", "-uid", os.getuid(),
                         "-gid", os.getgid(), "-mode", "0700", self.path / "vault.dmg",
                         auth=True, timeout=180)
            self.files["vault.dmg"] = identity(self.file_info("vault.dmg"))
            self.encrypted("vault.dmg")
            self.closed("vault.dmg")
            self.step("canary")
            first = self.attach("vault.dmg", "mount", initialize=True)
            canary_hash = self.write_canary(first)
            self.step("lock")
            self.detach(first)
            self.step("reopen")
            reopened = self.attach("vault.dmg", "mount")
            require(first["uuid"] == reopened["uuid"], "mount_binding")
            self.read_canary(reopened, canary_hash)
            self.detach(reopened)
            self.step("backup")
            image_hash = self.copy_closed("vault.dmg", "backup.dmg")
            self.step("restore")
            require(self.copy_closed("backup.dmg", "restore.dmg") == image_hash, "copy_mismatch")
            self.closed("vault.dmg")
            self.closed("backup.dmg")
            restored = self.attach("restore.dmg", "restore-mount")
            require(restored["uuid"] == first["uuid"], "mount_binding")
            self.closed("vault.dmg")
            self.closed("backup.dmg")
            self.read_canary(restored, canary_hash)
            self.detach(restored)
            self.step("complete")
            final_hashes = {}
            for name in ("vault.dmg", "backup.dmg", "restore.dmg"):
                self.closed(name)
                self.encrypted(name)
                final_hashes[name] = self.digest(name)
            require(final_hashes["vault.dmg"] == final_hashes["backup.dmg"] == image_hash,
                    "copy_mismatch")
            # 읽기/쓰기 mount는 파일시스템 metadata를 바꿀 수 있어 restore의 최종 hash를
            # 원본과 같다고 요구하지 않는다. 복사 시점 hash와 canary 복원을 별도로 증명한다.
            write_new(self.fd, "completion.json", json.dumps({
                "contract": "SEC-DEC-002", "scope": "synthetic_canary_storage_only",
                "authentication": "ephemeral_stdin" if self.synthetic else "native_agentpass",
                "creation_options": {"encryption": "AES-256", "filesystem": "APFS",
                                     "type": "UDIF", "size_mib": 256},
                "isencrypted": True, "canary_sha256": canary_hash, "copy_sha256": image_hash,
                "final_sha256": final_hashes,
                "lock_reopen_restore": "pass", "all_detached": True,
                "keychain_choice": "not_enforced", "financial_readiness": "not_assessed",
            }, sort_keys=True).encode("ascii") + b"\n")
        finally:
            self.password = None  # Python은 메모리 zeroization을 보장하지 않는다.
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            os.umask(old_umask)


def write_all(fd, data):
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        require(count > 0, "file_boundary")
        view = view[count:]


def write_new(dir_fd, name, data):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=dir_fd)
    try:
        private(os.fstat(fd))
        write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(dir_fd)


class FixedParser(argparse.ArgumentParser):
    def error(self, message):
        raise VaultError("arguments_denied")


def report(stage, result, reason=None):
    value = {"stage": stage, "result": result}
    if reason:
        value.update(reason=reason, state="incomplete_or_unknown")
    print(json.dumps(value), flush=True)


@sigterm_cancellation()
def main(argv=None):
    vault = None
    try:
        require(sys.flags.isolated and sys.flags.no_site, "isolated_python_required")
        parser = FixedParser(description="SEC-DEC-002 새 암호화 합성 canary 영역 준비")
        parser.add_argument("stage", choices=("bootstrap", "synthetic-integration"))
        parser.add_argument("--parent", help="승인된 저장소 밖 새 실행 디렉터리의 부모 (절대경로)")
        args = parser.parse_args(argv)
        synthetic = args.stage == "synthetic-integration"
        default = (Path("/private/tmp") / ("qh-paper-synthetic-" + uuid.uuid4().hex) if synthetic else
                   Path(pwd.getpwuid(os.getuid()).pw_dir) / "Library/Application Support/QuantHarbor/paper")
        parent = external_path(args.parent if args.parent is not None else str(default))
        vault = Vault(parent, synthetic=synthetic, progress=lambda stage: report(stage, "started"))
        vault.execute()
        report("complete", "pass")
        return 0
    except (Exception, KeyboardInterrupt, VaultCancelled) as failure:
        reason = ("command_cancelled" if isinstance(failure, VaultCancelled) else
                  failure.reason if isinstance(failure, VaultError) else "unexpected_failure")
        report(vault.stage if vault is not None else "preflight", "fail", reason)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
