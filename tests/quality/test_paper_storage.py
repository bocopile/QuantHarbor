"""SEC-paper-vault 모의 시험. hdiutil/UI/device 변경은 절대로 실행하지 않는다."""

from contextlib import contextmanager, redirect_stdout
import io
import fcntl
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import bootstrap_paper_storage as storage


def encoded(value):
    return plistlib.dumps(value)


class ModelCommands:
    """디스크 대신 임시 합성 디렉터리만 조작하는 명령 모델. 암호화 증거가 아니다."""

    def __init__(self):
        self.calls = []
        self.active = None
        self.canary = None
        self.fail = None
        self.mutate_restore = False
        self.real_lexists = os.path.lexists

    def lexists(self, path):
        if str(path).startswith("/dev/disk"):
            return self.active is not None
        return self.real_lexists(path)

    def __call__(self, argv, cwd, password=None, timeout=None):
        self.calls.append((list(argv), password, timeout))
        if argv[1] == self.fail:
            raise storage.VaultError("command_failed")
        if argv[0] == storage.DISKUTIL:
            return encoded(self.diskinfo())
        verb = argv[1]
        if verb == "create":
            target = Path(argv[-2])  # fixed auth flag is last
            target.write_bytes(b"mock-image-not-real-encryption")
            target.chmod(0o600)
            return b""
        if verb == "isencrypted":
            return encoded({"encrypted": True})
        if verb == "info":
            return encoded({"images": [] if self.active is None else [{
                "image-path": str(self.active["image"]), "system-entities": self.active["entities"],
            }]})
        if verb == "attach":
            image = Path(argv[2])
            mount = Path(argv[argv.index("-mountpoint") + 1])
            entities = [{"dev-entry": "/dev/disk900", "content-hint": "GUID_partition_scheme"},
                        {"dev-entry": "/dev/disk900s1", "content-hint": "Apple_APFS"},
                        {"dev-entry": "/dev/disk901", "content-hint": "Apple_APFS"},
                        {"dev-entry": "/dev/disk901s1", "mount-point": str(mount)}]
            self.active = {"image": image, "mount": mount, "entities": entities}
            mount.rename(str(mount) + "-underlay")
            mount.mkdir(mode=0o700)
            if self.canary is not None:
                (mount / "data").mkdir(mode=0o700)
                (mount / "data/bootstrap-canary.bin").write_bytes(self.canary)
                (mount / "data/bootstrap-canary.bin").chmod(0o600)
            if self.mutate_restore and image.name == "restore.dmg":
                with image.open("ab") as stream:
                    stream.write(b"mock-rw-filesystem-metadata-change")
            return encoded({"system-entities": entities})
        if verb == "detach":
            mount = self.active["mount"]
            self.canary = (mount / "data/bootstrap-canary.bin").read_bytes()
            shutil.rmtree(mount)  # 모델 소유 임시 합성 fixture에 한정
            Path(str(mount) + "-underlay").rename(mount)
            self.active = None
            return b""
        raise AssertionError("unexpected_mock_command")

    def diskinfo(self):
        return {"DeviceNode": "/dev/disk901s1", "MountPoint": str(self.active["mount"]),
                "FilesystemType": "apfs", "GlobalPermissionsEnabled": True, "Writable": True,
                "VolumeName": "QHPaperVault", "VolumeUUID": "a" * 8 + "-aaaa-aaaa-aaaa-" + "a" * 12}


class VaultFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qh-vault-mock-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        # final parent has owner-only permissions; no reads of default operational location
        self.parent = self.base / "parent"
        self.parent.mkdir(mode=0o700)
        self.model = ModelCommands()
        self.vault = storage.Vault(self.parent, runner=self.model)
        self.patches = [patch.object(storage.sys, "platform", "darwin"),
                        patch.object(storage.os.path, "lexists", self.model.lexists)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def open_run(self):
        self.vault.path.mkdir(mode=0o700)
        self.vault.fd = os.open(self.vault.path, storage.DIR_FLAGS)
        self.addCleanup(os.close, self.vault.fd)
        for mount in ("mount", "restore-mount"):
            (self.vault.path / mount).mkdir(mode=0o700)
            self.vault.mounts[mount] = storage.identity((self.vault.path / mount).stat())

    def image(self, name="vault.dmg", content=b"mock-image"):
        path = self.vault.path / name
        path.write_bytes(content)
        path.chmod(0o600)
        self.vault.files[name] = storage.identity(path.stat())
        return path

    @contextmanager
    def model_mounts(self):
        # workflow tests model only the OS mount layer. Independent boundary tests below
        # exercise real validate_mount with mocked stat/device/plist results.
        def checked(binding, allow_initial_permissions=False):
            self.assertIsNotNone(self.model.active)
            self.assertEqual(binding["name"], self.model.active["image"].name)
            binding["uuid"] = self.model.diskinfo()["VolumeUUID"]
            return (self.vault.path / binding["mount"]).stat()
        with patch.object(self.vault, "validate_mount", side_effect=checked):
            yield


class WorkflowTests(VaultFixture):
    def test_full_operational_model_has_fixed_commands_and_no_password(self):
        stages = []
        self.vault.progress = stages.append
        with self.model_mounts():
            self.vault.execute()
        self.assertEqual(stages, ["create", "canary", "lock", "reopen", "backup", "restore", "complete"])
        report = json.loads((self.vault.path / "completion.json").read_bytes())
        self.assertTrue(report["all_detached"])
        self.assertEqual(report["financial_readiness"], "not_assessed")
        self.assertEqual(report["keychain_choice"], "not_enforced")
        self.assertIsNone(self.model.active)
        for argv, password, timeout in self.model.calls:
            self.assertIsNone(password)
            self.assertIn(argv[0], (storage.HDIUTIL, storage.DISKUTIL))
            self.assertTrue(0 < timeout <= 180)
            self.assertFalse({"-ov", "-force", "-stdinpass", "sudo"} & set(argv))
            if argv[1] in ("create", "attach"):
                self.assertEqual(argv[-1], "-agentpass")
        create = self.model.calls[0][0]
        for flag, value in (("-type", "UDIF"), ("-size", "256m"), ("-fs", "APFS"),
                            ("-encryption", "AES-256"), ("-mode", "0700")):
            self.assertEqual(create[create.index(flag) + 1], value)
        for path in self.vault.path.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)

    def test_synthetic_only_password_is_memory_random_nul_stdin(self):
        self.vault.synthetic = True
        with self.model_mounts():
            self.vault.execute()
        auth = [(argv, password) for argv, password, _ in self.model.calls if "-stdinpass" in argv]
        self.assertEqual(len(auth), 4)  # create, original twice, independent restore
        passwords = [password for _, password in auth]
        self.assertEqual(len(set(passwords)), 1)
        self.assertEqual(len(passwords[0]), 65)
        self.assertEqual(passwords[0][-1:], b"\0")
        self.assertIsNone(self.vault.password)
        for path in self.vault.path.iterdir():
            if path.is_file():
                self.assertNotIn(passwords[0][:-1], path.read_bytes())
        self.assertTrue(all(passwords[0][:-1].decode() not in str(argv) for argv, _ in auth))

    def test_rw_restore_image_metadata_may_change_after_verified_copy(self):
        self.model.mutate_restore = True
        with self.model_mounts():
            self.vault.execute()
        report = json.loads((self.vault.path / "completion.json").read_bytes())
        self.assertNotEqual(report["final_sha256"]["restore.dmg"], report["copy_sha256"])

    def test_busy_detach_aborts_without_backup_completion_or_force(self):
        self.model.fail = "detach"
        with self.model_mounts(), self.assertRaisesRegex(storage.VaultError, "command_failed"):
            self.vault.execute()
        self.assertIsNotNone(self.model.active)
        self.assertFalse((self.vault.path / "backup.dmg").exists())
        self.assertFalse((self.vault.path / "completion.json").exists())
        self.assertEqual(sum(argv[1] == "detach" for argv, _, _ in self.model.calls), 1)
        self.assertTrue(all("-force" not in argv for argv, _, _ in self.model.calls))

    def test_unencrypted_create_has_no_attach_or_inner_write(self):
        real = self.model.__call__
        def runner(argv, *args, **kwargs):
            if argv[1] == "isencrypted":
                return encoded({"encrypted": False})
            return real(argv, *args, **kwargs)
        self.vault.runner = runner
        with self.assertRaisesRegex(storage.VaultError, "not_encrypted"):
            self.vault.execute()
        self.assertFalse((self.vault.path / "mount/data").exists())
        self.assertFalse(any(argv[1] == "attach" for argv, _, _ in self.model.calls))

    def test_uncertain_attach_never_writes_or_detaches(self):
        self.model.fail = "attach"
        with self.assertRaises(storage.VaultError):
            self.vault.execute()
        self.assertFalse((self.vault.path / "mount/data").exists())
        self.assertFalse(any(argv[1] == "detach" for argv, _, _ in self.model.calls))

    def test_malformed_attach_output_retains_unknown_state_without_inner_write(self):
        real = self.model.__call__
        def runner(argv, *args, **kwargs):
            value = real(argv, *args, **kwargs)
            return b"malformed-synthetic-response" if argv[1] == "attach" else value
        self.vault.runner = runner
        with self.assertRaisesRegex(storage.VaultError, "invalid_plist"):
            self.vault.execute()
        self.assertIsNotNone(self.model.active)
        self.assertFalse((self.vault.path / "mount/data").exists())
        self.assertFalse(any(argv[1] == "detach" for argv, _, _ in self.model.calls))

    def test_cancelled_native_create_is_not_retried_or_cleaned(self):
        self.model.fail = "create"
        with self.assertRaises(storage.VaultError):
            self.vault.execute()
        self.assertTrue(self.vault.path.is_dir())
        self.assertFalse((self.vault.path / "completion.json").exists())
        self.assertEqual(len(self.model.calls), 1)

    def test_failures_restore_umask_and_clear_password_reference(self):
        old = os.umask(0o027)
        try:
            self.vault.synthetic = True
            self.model.fail = "create"
            with self.assertRaises(storage.VaultError):
                self.vault.execute()
            self.assertEqual(os.umask(0o027), 0o027)
            self.assertIsNone(self.vault.password)
        finally:
            os.umask(old)


class PathTests(VaultFixture):
    def test_repo_relative_url_device_and_dot_components_rejected(self):
        for path in (str(storage.ROOT / "new-vault"), "relative", "file:///tmp/a", "/tmp/../a",
                     "/private//tmp", "/tmp/a\nname", "/"):
            with self.subTest(path=path), self.assertRaises(storage.VaultError):
                storage.external_path(path)
        # A device file is never a parent directory, even though lexically absolute.
        with self.assertRaises(storage.VaultError), storage.parent_directory(Path("/dev/null")):
            pass

    def test_symlink_parent_existing_run_and_weak_permissions_rejected(self):
        link = self.base / "link"
        link.symlink_to(self.parent, target_is_directory=True)
        with self.assertRaises(OSError), storage.parent_directory(link):
            pass
        self.vault.path.mkdir(mode=0o700)
        with self.assertRaisesRegex(storage.VaultError, "existing_target"):
            self.vault.execute()
        self.parent.chmod(0o755)
        with self.assertRaisesRegex(storage.VaultError, "owner_or_permissions"), storage.parent_directory(self.parent):
            pass

    def test_existing_image_symlink_hardlink_fifo_and_mode_rejected(self):
        self.open_run()
        source = self.image("source.dmg")
        target = self.vault.path / "vault.dmg"
        target.symlink_to(source)
        with self.assertRaises(storage.VaultError):
            self.vault.file_info("vault.dmg")
        target.unlink()
        os.link(source, target)
        with self.assertRaises(storage.VaultError):
            self.vault.file_info("vault.dmg")
        target.unlink()
        os.mkfifo(target, 0o600)
        with self.assertRaises(storage.VaultError):
            self.vault.file_info("vault.dmg")
        target.unlink()
        target.write_bytes(b"mock")
        target.chmod(0o644)
        with self.assertRaises(storage.VaultError):
            self.vault.file_info("vault.dmg")

    def test_replaced_image_and_run_detected(self):
        self.open_run()
        image = self.image()
        image.rename(self.vault.path / "old.dmg")
        image.write_bytes(b"replacement")
        image.chmod(0o600)
        with self.assertRaisesRegex(storage.VaultError, "identity_changed"):
            self.vault.file_info("vault.dmg")
        self.vault.path.rename(self.parent / "old-run")
        self.vault.path.mkdir(mode=0o700)
        with self.assertRaisesRegex(storage.VaultError, "identity_changed"):
            self.vault.check_run()

    def test_missing_parent_is_not_recreated_during_check(self):
        self.open_run()
        self.parent.rename(self.base / "moved-parent")
        with self.assertRaises(storage.VaultError):
            self.vault.check_run()
        self.assertFalse(self.parent.exists())

    def test_other_repository_metadata_rejected_without_reading_git_contents(self):
        (self.parent / ".git").write_bytes(b"mock-worktree-marker-not-read")
        nested = self.parent / "nested"
        with self.assertRaisesRegex(storage.VaultError, "path_boundary"), storage.parent_directory(nested, create=True):
            pass
        self.assertFalse(nested.exists())

    def test_nonempty_unmounted_path_refuses_attach(self):
        self.open_run()
        self.image()
        (self.vault.path / "mount/occupied").write_bytes(b"synthetic")
        with self.assertRaisesRegex(storage.VaultError, "mount_binding"):
            self.vault.attach("vault.dmg", "mount")
        self.assertFalse(any(argv[1] == "attach" for argv, _, _ in self.model.calls))

    def test_wrong_owner_and_image_size_limit(self):
        with self.assertRaises(storage.VaultError):
            storage.private(SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=os.getuid() + 1,
                                            st_nlink=1))
        self.open_run()
        image = self.image()
        with image.open("r+b") as stream:
            stream.truncate(storage.IMAGE_LIMIT + 1)
        with self.assertRaisesRegex(storage.VaultError, "size_limit"):
            self.vault.digest("vault.dmg")


class InfoMetadataTests(VaultFixture):
    def assert_unknown(self, entry):
        with patch.object(self.vault, "command", return_value=encoded({"images": [entry]})):
            for operation in (self.vault.images, lambda: self.vault.closed("vault.dmg")):
                with self.assertRaises(storage.VaultError):
                    operation()

    def test_empty_info_entry_cannot_prove_closed(self):
        self.assert_unknown({})  # SV1: images:[{}]

    def test_required_image_path_must_be_unambiguous_absolute_string(self):
        for path in (None, "", 123, [], "relative.dmg", "/", "/tmp/../image.dmg",
                     "/tmp//image.dmg", "/tmp/image\n.dmg"):
            with self.subTest(path=path):
                entry = {"system-entities": [{"dev-entry": "/dev/disk999"}]}
                if path is not None:
                    entry["image-path"] = path
                self.assert_unknown(entry)

    def test_required_entities_must_be_nonempty_list_of_device_dicts(self):
        for entries in (None, {}, "unknown", [], [{}], ["unknown"],
                        [{"dev-entry": "/dev/disk999"}] * 33):
            with self.subTest(entries=entries):
                entry = {"image-path": "/unrelated.dmg"}
                if entries is not None:
                    entry["system-entities"] = entries
                self.assert_unknown(entry)

    def test_invalid_or_duplicate_devices_cannot_prove_closed(self):
        for devices in (("",), (123,), ("/dev/disk999;invalid",), ("/dev/rdisk999",),
                        ("/dev/disk999", "/dev/disk999")):
            with self.subTest(devices=devices):
                self.assert_unknown({"image-path": "/unrelated.dmg", "system-entities": [
                    {"dev-entry": device} for device in devices]})

    def test_present_mount_metadata_must_be_valid_path(self):
        for mount in ("", 123, [], "relative", "/tmp/../mount", "/tmp/mount\n"):
            with self.subTest(mount=mount):
                self.assert_unknown({"image-path": "/unrelated.dmg", "system-entities": [
                    {"dev-entry": "/dev/disk999", "mount-point": mount}]})

    def test_all_info_entries_validated_before_target_match(self):
        valid = {"image-path": str(self.vault.path / "vault.dmg"),
                 "system-entities": [{"dev-entry": "/dev/disk999"}]}
        with patch.object(self.vault, "command", return_value=encoded({"images": [valid, {}]})):
            with self.assertRaisesRegex(storage.VaultError, "mount_binding"):
                self.vault.closed("vault.dmg")

    def test_unknown_info_prevents_copy_and_attach(self):
        self.open_run()
        self.image()
        real = self.model.__call__
        def runner(argv, *args, **kwargs):
            return encoded({"images": [{}]}) if argv[1] == "info" else real(argv, *args, **kwargs)
        self.vault.runner = runner
        for operation in (lambda: self.vault.copy_closed("vault.dmg", "backup.dmg"),
                          lambda: self.vault.attach("vault.dmg", "mount")):
            with self.assertRaises(storage.VaultError):
                operation()
        self.assertFalse((self.vault.path / "backup.dmg").exists())
        self.assertFalse(any(argv[1] == "attach" for argv, _, _ in self.model.calls))

    def test_empty_list_and_valid_unrelated_image_allow_closed(self):
        for images in ([], [{"image-path": "/unrelated.dmg", "system-entities": [
                {"dev-entry": "/dev/disk999", "mount-point": "/Volumes/Unrelated"}]}]):
            with self.subTest(images=images), patch.object(
                    self.vault, "command", return_value=encoded({"images": images})):
                self.vault.closed("vault.dmg")


class MountBindingTests(VaultFixture):
    def setUp(self):
        super().setUp()
        self.open_run()
        self.image()
        raw = self.model([storage.HDIUTIL, "attach", str(self.vault.path / "vault.dmg"),
                          "-mountpoint", str(self.vault.path / "mount")], self.vault.path)
        self.binding = {"name": "vault.dmg", "mount": "mount",
                        "entities": storage.plist(raw)["system-entities"], "detach": "/dev/disk900"}
        self.disk = self.model.diskinfo()
        self.actual_stat = os.lstat
        def lstat(path, *args, **kwargs):
            if str(path).startswith("/dev/disk"):
                return SimpleNamespace(st_mode=stat.S_IFBLK | 0o600, st_uid=0, st_nlink=1, st_rdev=987654)
            if str(path) == str(self.vault.path / "mount"):
                return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=os.getuid(), st_nlink=2,
                                       st_dev=987654, st_ino=123)
            return self.actual_stat(path, *args, **kwargs)
        real = self.model.__call__
        def runner(argv, *args, **kwargs):
            if argv[0] == storage.DISKUTIL:
                return encoded(self.disk)
            return real(argv, *args, **kwargs)
        self.vault.runner = runner
        for item in (patch.object(storage.os, "lstat", side_effect=lstat),
                     patch.object(storage.os.path, "ismount", return_value=True)):
            item.start()
            self.addCleanup(item.stop)

    def test_full_mock_os_binding_passes(self):
        self.assertEqual(self.vault.validate_mount(self.binding).st_dev, 987654)

    def test_current_user_device_owner_allowed_but_other_owner_rejected(self):
        original = storage.os.lstat
        owner = os.getuid()
        def lstat(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if str(path).startswith("/dev/disk"):
                info.st_uid = owner
            return info
        with patch.object(storage.os, "lstat", side_effect=lstat):
            self.vault.validate_mount(self.binding)
            owner = os.getuid() + 10000
            with self.assertRaisesRegex(storage.VaultError, "device_binding"):
                self.vault.validate_mount(self.binding)

    def test_initial_apfs_755_is_not_accepted_for_ordinary_reads(self):
        original = storage.os.lstat
        mode = 0o755
        def lstat(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if str(path) == str(self.vault.path / "mount"):
                info.st_mode = stat.S_IFDIR | mode
            return info
        with patch.object(storage.os, "lstat", side_effect=lstat):
            with self.assertRaises(storage.VaultError):
                self.vault.validate_mount(self.binding)
            self.vault.validate_mount(self.binding, allow_initial_permissions=True)
            mode = 0o777
            with self.assertRaises(storage.VaultError):
                self.vault.validate_mount(self.binding, allow_initial_permissions=True)

    def test_wrong_mount_fs_device_permissions_writable_name_uuid_rejected(self):
        values = {"MountPoint": "/private/tmp/unrelated", "DeviceNode": "/dev/disk0s1",
                  "FilesystemType": "hfs", "GlobalPermissionsEnabled": False, "Writable": False,
                  "VolumeName": "unrelated", "VolumeUUID": "invalid", "ReadOnlyMedia": True,
                  "ReadOnlyVolume": True}
        for key, value in values.items():
            with self.subTest(field=key):
                original = self.disk.copy()
                self.disk[key] = value
                with self.assertRaisesRegex(storage.VaultError, "mount_binding"):
                    self.vault.validate_mount(self.binding)
                self.disk = original

    def test_attach_plist_and_current_mapping_must_be_exact(self):
        self.binding["entities"] = [dict(e) for e in self.binding["entities"]]
        self.binding["entities"][-1]["dev-entry"] = "/dev/disk0s1"
        with self.assertRaisesRegex(storage.VaultError, "mount_binding"):
            self.vault.validate_mount(self.binding)

    def test_unrelated_image_with_same_mount_is_rejected(self):
        previous = self.vault.images
        self.vault.images = lambda: previous() + [{"image-path": "/unrelated.dmg",
            "system-entities": [{"dev-entry": "/dev/disk999", "mount-point": str(self.vault.path / "mount")}]}]
        with self.assertRaisesRegex(storage.VaultError, "mount_binding"):
            self.vault.validate_mount(self.binding)

    def test_actual_mount_and_device_node_required(self):
        with patch.object(storage.os.path, "ismount", return_value=False), self.assertRaises(storage.VaultError):
            self.vault.validate_mount(self.binding)
        with patch.object(storage.os, "lstat", return_value=SimpleNamespace(
                st_mode=stat.S_IFLNK | 0o777, st_uid=0, st_nlink=1)), self.assertRaises(storage.VaultError):
            self.vault.validate_mount(self.binding)

    def test_actual_filesystem_device_number_must_equal_volume_block_device(self):
        real_lstat = storage.os.lstat
        def wrong_device(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if str(path) == "/dev/disk901s1":
                info.st_rdev += 1
            return info
        with patch.object(storage.os, "lstat", side_effect=wrong_device), self.assertRaisesRegex(
                storage.VaultError, "device_binding"):
            self.vault.validate_mount(self.binding)

    def test_volume_uuid_cannot_change_within_binding(self):
        self.vault.validate_mount(self.binding)
        self.disk["VolumeUUID"] = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        with self.assertRaisesRegex(storage.VaultError, "mount_binding"):
            self.vault.validate_mount(self.binding)

    def test_no_data_write_on_failed_full_mount_validation(self):
        self.disk["GlobalPermissionsEnabled"] = False
        with self.assertRaises(storage.VaultError):
            self.vault.write_canary(self.binding)
        self.assertFalse((self.vault.path / "mount/data").exists())

    def test_detached_state_requires_image_and_all_device_nodes_gone(self):
        with self.assertRaisesRegex(storage.VaultError, "not_detached"):
            self.vault.closed("vault.dmg", ("/dev/disk900",))
        self.model.active = None
        with patch.object(storage.os.path, "lexists", return_value=True), self.assertRaises(storage.VaultError):
            self.vault.closed("vault.dmg", ("/dev/disk900",))


class InitialPermissionsTests(VaultFixture):
    def test_initialize_new_mount_permissions_after_binding_before_content(self):
        self.open_run()
        self.image()
        self.vault.stage = "canary"
        with self.model_mounts():
            binding = self.vault.attach("vault.dmg", "mount")
            mount = self.vault.path / "mount"
            mount.chmod(0o755)
            self.vault.initialize_mount_permissions(binding)
            self.assertEqual(stat.S_IMODE(mount.stat().st_mode), 0o700)
            self.assertFalse((mount / "data").exists())

    def test_bad_binding_or_noninitial_target_never_chmods(self):
        self.open_run()
        self.image()
        binding = {"name": "vault.dmg", "mount": "mount"}
        with patch.object(storage.os, "fchmod") as chmod:
            with self.assertRaises(storage.VaultError):
                self.vault.initialize_mount_permissions(binding)
            self.vault.stage = "canary"
            with patch.object(self.vault, "validate_mount", side_effect=storage.VaultError("mount_binding")):
                with self.assertRaises(storage.VaultError):
                    self.vault.initialize_mount_permissions(binding)
            chmod.assert_not_called()


class BackupTests(VaultFixture):
    def test_closed_copy_no_overwrite_and_same_host_independent_inode(self):
        self.open_run()
        original = self.image()
        digest = self.vault.copy_closed("vault.dmg", "backup.dmg")
        self.assertEqual(digest, self.vault.digest("backup.dmg"))
        self.assertNotEqual(original.stat().st_ino, (self.vault.path / "backup.dmg").stat().st_ino)
        with self.assertRaisesRegex(storage.VaultError, "existing_target"):
            self.vault.copy_closed("vault.dmg", "backup.dmg")

    def test_copy_refused_for_attached_image(self):
        self.open_run()
        self.image()
        self.model.active = {"image": self.vault.path / "vault.dmg",
                             "entities": [{"dev-entry": "/dev/disk900"}]}
        with self.assertRaisesRegex(storage.VaultError, "not_detached"):
            self.vault.copy_closed("vault.dmg", "backup.dmg")
        self.assertFalse((self.vault.path / "backup.dmg").exists())

    def test_mutated_source_during_copy_fails(self):
        self.open_run()
        source = self.image()
        actual = self.vault.digest
        calls = 0
        def digest(name):
            nonlocal calls
            calls += 1
            if calls == 2:
                source.write_bytes(b"tampered-synthetic-image")
            return actual(name)
        with patch.object(self.vault, "digest", side_effect=digest), self.assertRaisesRegex(
                storage.VaultError, "copy_mismatch"):
            self.vault.copy_closed("vault.dmg", "backup.dmg")

    def test_canary_tampering_rejected_without_completion(self):
        self.open_run()
        self.image()
        with self.model_mounts():
            binding = self.vault.attach("vault.dmg", "mount")
            digest = self.vault.write_canary(binding)
            path = self.vault.path / "mount/data/bootstrap-canary.bin"
            path.write_bytes(b"x" * path.stat().st_size)
            with self.assertRaisesRegex(storage.VaultError, "canary_mismatch"):
                self.vault.read_canary(binding, digest)
        self.assertFalse((self.vault.path / "completion.json").exists())

    def test_canary_hardlink_refused_before_read(self):
        self.open_run()
        self.image()
        with self.model_mounts():
            binding = self.vault.attach("vault.dmg", "mount")
            digest = self.vault.write_canary(binding)
            path = self.vault.path / "mount/data/bootstrap-canary.bin"
            os.link(path, self.vault.path / "mock-second-link")
            with self.assertRaisesRegex(storage.VaultError, "owner_or_permissions"):
                self.vault.read_canary(binding, digest)


class ProcessAndCliTests(unittest.TestCase):
    def test_first_sigterm_during_success_cleanup_stops_following_work(self):
        real_popen = subprocess.Popen
        cancelled = []
        following_work = []
        previous = signal.getsignal(signal.SIGTERM)

        class SignalOnClose:
            def __init__(self, stream):
                self.stream = stream

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def close(self):
                if not cancelled:
                    cancelled.append(True)
                    os.kill(os.getpid(), signal.SIGTERM)
                self.stream.close()

        def popen(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            proc.stdout = SignalOnClose(proc.stdout)
            return proc

        def execute(_vault):
            self.run_python("pass")
            following_work.append(True)

        output = io.StringIO()
        with patch.object(storage.subprocess, "Popen", side_effect=popen), \
                patch.object(storage.Vault, "execute", execute), redirect_stdout(output):
            result = storage.main(["bootstrap", "--parent", "/private/tmp/mock-only"])
        self.assertEqual(result, 1)
        self.assertEqual(cancelled, [True])
        self.assertEqual(following_work, [])
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)
        self.assertEqual(json.loads(output.getvalue()), {
            "stage": "preflight", "result": "fail", "reason": "command_cancelled",
            "state": "incomplete_or_unknown"})

    def test_sigterm_cleans_actual_synthetic_process_group_and_reports_unknown(self):
        # Real Python processes only. Locks prove both descendants stopped even if an
        # orphan briefly remains a zombie. The finally also cleans up the RED run.
        with tempfile.TemporaryDirectory(prefix="qh-vault-sigterm-") as temp:
            base = Path(temp)
            ready = base / "ready.json"
            child_lock, grandchild_lock = base / "child.lock", base / "grandchild.lock"
            grandchild_code = f"""
import fcntl,json,os,signal,time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
lock = open({str(grandchild_lock)!r}, 'w')
fcntl.flock(lock, fcntl.LOCK_EX)
Path({str(ready)!r}).write_text(json.dumps([os.getppid(), os.getpid(), os.getpgrp()]))
time.sleep(30)
"""
            child_code = f"""
import fcntl,signal,subprocess,sys,time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
lock = open({str(child_lock)!r}, 'w')
fcntl.flock(lock, fcntl.LOCK_EX)
subprocess.Popen([sys.executable, '-I', '-S', '-c', {grandchild_code!r}])
print('synthetic-private-canary', flush=True)
time.sleep(30)
"""
            harness = f"""
import importlib.util,json,signal,sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('storage', {str(storage.ROOT / 'scripts/bootstrap_paper_storage.py')!r})
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)
previous = signal.getsignal(signal.SIGTERM)
storage.HDIUTIL = sys.executable
def execute(self):
    self.stage = 'create'
    storage.run_bounded([sys.executable, '-I', '-S', '-c', {child_code!r}], Path('/'), timeout=20)
storage.Vault.execute = execute
real_killpg = storage.os.killpg
def killpg(group, signum):
    real_killpg(group, signum)
    # A second actual SIGTERM during cleanup must not interrupt bounded reaping.
    storage.os.kill(storage.os.getpid(), signal.SIGTERM)
storage.os.killpg = killpg
code = storage.main(['bootstrap', '--parent', {str(base / 'unused-parent')!r}])
print(json.dumps({{'handler_restored': signal.getsignal(signal.SIGTERM) is previous}}), flush=True)
raise SystemExit(code)
"""
            proc = subprocess.Popen([sys.executable, "-I", "-S", "-c", harness],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env={"PATH": os.defpath}, start_new_session=True)
            pids = None
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        pids = json.loads(ready.read_text())
                        break
                    except (FileNotFoundError, json.JSONDecodeError):
                        self.assertIsNone(proc.poll(), "synthetic harness exited before readiness")
                        time.sleep(0.01)
                self.assertIsNotNone(pids, "synthetic descendants did not become ready")
                self.assertEqual(pids[0], pids[2])  # child owns the isolated process group
                started = time.monotonic()
                proc.send_signal(signal.SIGTERM)
                out, err = proc.communicate(timeout=8)
                elapsed = time.monotonic() - started
                self.assertLess(elapsed, 8)
                # killpg can precede scheduler/reaper completion by a few milliseconds.
                for lock_path in (child_lock, grandchild_lock):
                    with lock_path.open() as lock:
                        deadline = time.monotonic() + 2
                        while True:
                            try:
                                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                break
                            except BlockingIOError:
                                if time.monotonic() >= deadline:
                                    self.fail("synthetic descendant survived cancellation")
                                time.sleep(0.01)
                with self.assertRaises(ProcessLookupError):
                    os.kill(pids[0], 0)  # direct child was reaped
                self.assertEqual(proc.returncode, 1)
                self.assertEqual(err, b"")
                self.assertEqual([json.loads(line) for line in out.splitlines()], [
                    {"stage": "create", "result": "fail", "reason": "command_cancelled",
                     "state": "incomplete_or_unknown"}, {"handler_restored": True}])
                self.assertNotIn(b"synthetic-private-canary", out + err)
            finally:
                if pids is not None:
                    try:
                        os.killpg(pids[2], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if proc.poll() is None:
                    proc.kill()
                proc.communicate(timeout=3)

    def test_sigterm_handler_restored_after_normal_and_failed_main_and_runner(self):
        original = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, original)
        def previous(signum, frame):
            self.fail("previous SIGTERM handler ran during protected operation")
        signal.signal(signal.SIGTERM, previous)
        for failure in (None, RuntimeError("synthetic-private-canary")):
            with self.subTest(failure=failure), patch.object(
                    storage.Vault, "execute", side_effect=failure), redirect_stdout(io.StringIO()):
                self.assertEqual(storage.main(["bootstrap", "--parent", "/private/tmp/mock-only"]),
                                 0 if failure is None else 1)
            self.assertIs(signal.getsignal(signal.SIGTERM), previous)
        self.run_python("pass")
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)
        with self.assertRaises(storage.VaultError):
            self.run_python("raise SystemExit(1)")
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def run_python(self, code, **kwargs):
        # Only synthetic Python children; substituting a fixed binary in this test does
        # not expose a helper CLI for arbitrary commands.
        with patch.object(storage, "HDIUTIL", sys.executable):
            return storage.run_bounded([sys.executable, "-I", "-S", "-c", code], Path("/"), **kwargs)

    def test_bounded_capture_minimal_environment_and_no_stdin(self):
        real_popen = subprocess.Popen
        with patch.dict(os.environ, {"QH_SYNTHETIC_ENV_CANARY": "not-a-secret", "PYTHONPATH": "/invalid"}), \
                patch.object(storage.subprocess, "Popen", wraps=real_popen) as popen:
            output = self.run_python(
                "import os,sys,json; print(json.dumps({'keys': sorted(os.environ), 'stdin':sys.stdin.read()}))")
        self.assertEqual(sorted(popen.call_args.kwargs["env"]), ["HOME", "LANG", "LC_ALL", "PATH"])
        self.assertTrue(popen.call_args.kwargs["close_fds"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        result = json.loads(output)
        # macOS 런타임이 자동 삽입할 수 있는 고정 인코딩 키. 부모 환경 상속은 아니다.
        self.assertTrue(set(result["keys"]) <= {"HOME", "LANG", "LC_ALL", "PATH", "__CF_USER_TEXT_ENCODING"})
        self.assertEqual(result["stdin"], "")

    def test_synthetic_stdin_nul_passphrase_only(self):
        password = b"a" * 64 + b"\0"
        output = self.run_python("import sys; b=sys.stdin.buffer.read(); print(len(b), b[-1] == 0)", password=password)
        self.assertEqual(output, b"65 True\n")

    def test_stdout_stderr_combined_capture_is_bounded(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream), self.assertRaisesRegex(storage.VaultError, "command_output_limit"):
                self.run_python(f"import sys; sys.{stream}.buffer.write(b'x'*400000)", timeout=3)

    def test_timeout_kills_child_and_nonzero_output_is_not_exposed(self):
        with self.assertRaisesRegex(storage.VaultError, "command_timeout"):
            self.run_python("import time; time.sleep(20)", timeout=0.1)
        with self.assertRaisesRegex(storage.VaultError, "command_failed") as caught:
            self.run_python("import sys; print('synthetic-sensitive-canary'); sys.exit(1)")
        self.assertNotIn("synthetic-sensitive-canary", str(caught.exception))

    def test_cli_rejects_bad_arguments_without_echoing_values_or_mutating(self):
        script = str(storage.ROOT / "scripts/bootstrap_paper_storage.py")
        for args in (["--device", "synthetic-private-canary"], ["attach", "/dev/disk0"],
                     ["bootstrap", "--parent", str(storage.ROOT / "new-vault")]):
            result = subprocess.run([sys.executable, "-I", "-S", script, *args],
                                    capture_output=True, timeout=3, env={"PATH": os.defpath})
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["result"], "fail")
            self.assertNotIn(b"synthetic-private-canary", result.stdout + result.stderr)
            self.assertEqual(result.stderr, b"")

    def test_cli_requires_isolated_python_and_sanitizes_unexpected_exception(self):
        output = io.StringIO()
        with patch.object(storage.sys, "flags", SimpleNamespace(isolated=0, no_site=0)), redirect_stdout(output):
            self.assertEqual(storage.main(["bootstrap"]), 1)
        self.assertEqual(json.loads(output.getvalue())["reason"], "isolated_python_required")
        output = io.StringIO()
        with patch.object(storage.sys, "flags", SimpleNamespace(isolated=1, no_site=1)), \
                patch.object(storage.Vault, "execute", side_effect=RuntimeError("synthetic-private-canary")), \
                redirect_stdout(output):
            self.assertEqual(storage.main(["bootstrap", "--parent", "/private/tmp/mock-only"]), 1)
        self.assertNotIn("synthetic-private-canary", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["state"], "incomplete_or_unknown")

    def test_invalid_or_oversized_plist_and_bad_devices_fail_closed(self):
        for data in (b"bad-plist", encoded(["unexpected"]), b"x" * (storage.CAPTURE_LIMIT + 1)):
            with self.assertRaises(storage.VaultError):
                storage.plist(data)
        for entries in ([], [{"dev-entry": "/dev/disk0;evil"}],
                        [{"dev-entry": "/dev/disk1"}] * 2, [{"dev-entry": "https://invalid"}]):
            with self.assertRaises(storage.VaultError):
                storage.Vault.entities({"system-entities": entries})


if __name__ == "__main__":
    unittest.main()
