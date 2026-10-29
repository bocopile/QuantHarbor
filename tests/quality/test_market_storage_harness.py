"""Synthetic public/private boundaries of the trusted storage verifier."""
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import check_market_storage as storage
import check_quality as quality
from test_quality import public_fixture, put, git


class StorageHarnessBoundaryTests(unittest.TestCase):
    def test_only_public_nonignored_sources_are_copied(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve() / 'repository'
            root.mkdir()
            public_fixture(root)
            put(root, 'config/runtime.synthetic.toml', '# synthetic\n')
            put(root, 'src/quantharbor/public.py', '# public fixture\n')
            put(root, 'src/quantharbor/private/canary.py', '# synthetic private canary\n')
            put(root, 'tests/product/private/tracked.py', '# synthetic tracked private canary\n')
            git(root, 'add', '-f', '--', 'tests/product/private/tracked.py')
            target = Path(d) / 'context'
            target.mkdir()
            with patch.object(storage, 'ROOT', root):
                storage.build_context(target, b'synthetic wheel')
            self.assertTrue((target / 'src/quantharbor/public.py').is_file())
            self.assertFalse((target / 'src/quantharbor/private').exists())
            self.assertFalse((target / 'tests/product/private').exists())

    def test_unignored_protected_source_is_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve() / 'repository'
            root.mkdir()
            public_fixture(root)
            put(root, 'config/runtime.synthetic.toml', '# synthetic\n')
            put(root, 'src/quantharbor/secrets/canary.py', '# synthetic private canary\n')
            target = Path(d) / 'context'
            target.mkdir()
            with patch.object(storage, 'ROOT', root):
                with self.assertRaises((storage.CheckFailure, quality.QualityFailure)):
                    storage.build_context(target, b'synthetic wheel')
            self.assertFalse((target / 'src/quantharbor/secrets').exists())

    def test_fifo_wheel_rejected_without_wait_or_docker_objects(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / storage.WHEEL
            os.mkfifo(path, 0o600)
            no_tools = Path(d) / 'empty-path'
            no_tools.mkdir()
            self.assertIsNone(shutil.which('docker', path=str(no_tools)))
            result = subprocess.run([sys.executable, '-I', '-S', str(storage.ROOT / 'scripts/check_market_storage.py'),
                                     '--wheel', str(path)], env={'PATH': str(no_tools)}, capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b'input_file_boundary', result.stdout)
            self.assertIn(b'not_created', result.stdout)
            path.unlink()
            path.write_bytes(b'synthetic invalid wheel')
            for candidate, reason in ((path, b'wheel_integrity'), (Path(d)/'wrong.whl', b'wheel_name_mismatch')):
                if candidate != path:
                    candidate.write_bytes(b'synthetic invalid wheel')
                result = subprocess.run([sys.executable, '-I', '-S', str(storage.ROOT / 'scripts/check_market_storage.py'),
                                         '--wheel', str(candidate)], env={'PATH': str(no_tools)}, capture_output=True, timeout=3)
                self.assertEqual(result.returncode, 1)
                self.assertIn(reason, result.stdout)
                self.assertIn(b'not_created', result.stdout)
