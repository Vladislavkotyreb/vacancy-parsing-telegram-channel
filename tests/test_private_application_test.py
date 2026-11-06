"""Temporary deployment checks; no process, network, or service operations."""
import importlib.util
import io
import os
from contextlib import redirect_stdout
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/private_application_test.py'
SPEC = importlib.util.spec_from_file_location('private_test_installer', SOURCE)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class PrivateApplicationInstallerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'logs').mkdir()
        self.originals = {
            'bot/chat_main.py': b'import os\n\nasync def main():\n    dp.include_router(router)\n',
            '.env': b'# keep this comment\nTELEGRAM_ADMIN_ID=123\nTELEGRAM_BOT_TOKEN=secret\nUNRELATED="keep me"\n',
            'deploy/isp/autodeploy.sh': b'#!/bin/bash\nLOG_DIR="$BOT_DIR/logs"\necho original\n',
        }
        for name, data in self.originals.items():
            installer.write(self.root / name, data, 0o640)
        self.module = self.root / 'candidate.py'
        self.module.write_bytes(b'def create_demo_router(owner):\n    return owner\n')

    def installed(self, prior_module=False):
        if prior_module:
            installer.write(self.root / 'bot/application_demo.py', b'# previous local module\n', 0o644)
        original, patched = installer.prepare(self.root, self.module)
        manifest = installer.backup(self.root, original, patched)
        for name, data in patched.items():
            installer.write(self.root / name, data, manifest[name]['mode'])
        installer.write(self.root / installer.ACTIVE, b'active\n')
        return original, patched, manifest

    def test_patch_preserves_existing_code_and_adds_guard_and_hook_once(self):
        original, patched = installer.prepare(self.root, self.module)
        self.assertEqual(original['bot/chat_main.py'], self.originals['bot/chat_main.py'])
        self.assertIn(b'APPLICATION_DEMO_ENABLED', patched['bot/chat_main.py'])
        self.assertLess(patched['bot/chat_main.py'].index(b'create_demo_router'), patched['bot/chat_main.py'].index(b'dp.include_router(router)'))
        self.assertIn(b'private-application-test.active', patched['deploy/isp/autodeploy.sh'])
        self.assertTrue(patched['deploy/isp/autodeploy.sh'].endswith(b'echo original\n'))

    def test_patch_rejects_missing_or_ambiguous_anchors(self):
        for data in (b'missing', b'anchor anchor'):
            with self.subTest(data=data), self.assertRaisesRegex(RuntimeError, 'exactly one'):
                installer.insert_once(data, b'anchor', b'addition')

    def test_env_changes_only_demo_key_and_handles_duplicates(self):
        data = b'# header\r\nTOKEN="a=b"\r\nexport APPLICATION_DEMO_ENABLED=0\r\nAPPLICATION_DEMO_ENABLED="0"\r\nOTHER=x'
        result = installer.enable_env(data)
        self.assertEqual(result, b'# header\r\nTOKEN="a=b"\r\nAPPLICATION_DEMO_ENABLED=1\r\nAPPLICATION_DEMO_ENABLED=1\r\nOTHER=x')
        self.assertEqual(installer.enable_env(b'TOKEN=secret'), b'TOKEN=secret\nAPPLICATION_DEMO_ENABLED=1\n')

    def test_backup_and_rollback_restore_exact_bytes_and_modes(self):
        original, _, manifest = self.installed(prior_module=True)
        backup = self.root / installer.BACKUP
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in backup.iterdir()))
        installer.restore(self.root, manifest)
        for name, expected in original.items():
            self.assertEqual((self.root / name).read_bytes(), expected)
            self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), manifest[name]['mode'])
        self.assertFalse((self.root / installer.ACTIVE).exists())
        self.assertTrue((backup / 'manifest.json').exists())

    def test_rollback_removes_only_new_module(self):
        _, _, manifest = self.installed()
        installer.restore(self.root, manifest)
        self.assertFalse((self.root / 'bot/application_demo.py').exists())
        self.assertEqual((self.root / '.env').read_bytes(), self.originals['.env'])

    def test_external_edit_rejects_rollback_before_any_file_changes(self):
        _, patched, manifest = self.installed()
        (self.root / '.env').write_bytes(b'UNRELATED=changed\n')
        with self.assertRaisesRegex(RuntimeError, 'External edit'):
            installer.restore(self.root, manifest)
        self.assertEqual((self.root / 'bot/chat_main.py').read_bytes(), patched['bot/chat_main.py'])
        self.assertEqual((self.root / '.env').read_bytes(), b'UNRELATED=changed\n')
        self.assertTrue((self.root / installer.ACTIVE).exists())

    def test_corrupt_backup_rejected_before_any_file_changes(self):
        _, patched, manifest = self.installed()
        (self.root / installer.BACKUP / '1').write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'checksum'):
            installer.restore(self.root, manifest, validate_only=True)
        self.assertEqual((self.root / 'bot/chat_main.py').read_bytes(), patched['bot/chat_main.py'])

    def test_partial_install_can_be_recovered(self):
        original, patched = installer.prepare(self.root, self.module)
        manifest = installer.backup(self.root, original, patched)
        installer.write(self.root / 'bot/chat_main.py', patched['bot/chat_main.py'])
        installer.restore(self.root, manifest, partial=True)
        self.assertEqual((self.root / 'bot/chat_main.py').read_bytes(), original['bot/chat_main.py'])
        self.assertFalse((self.root / 'bot/application_demo.py').exists())

    def test_owner_must_be_positive_and_uses_effective_environment(self):
        dotenv = mock.Mock(dotenv_values=mock.Mock(return_value={'TELEGRAM_ADMIN_ID': '123'}))
        with mock.patch.dict('sys.modules', {'dotenv': dotenv}), mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(installer.owner_id(self.root), 123)
            for value in ('', '0', '-12', 'abc'):
                with mock.patch.dict(os.environ, {'TELEGRAM_ADMIN_ID': value}), self.assertRaises(RuntimeError):
                    installer.owner_id(self.root)
            with mock.patch.dict(os.environ, {'TELEGRAM_ADMIN_ID': '456'}):
                self.assertEqual(installer.owner_id(self.root), 456)

    def test_external_installer_path_can_import_module_repository_dependency(self):
        (self.root / '_private_test_dependency.py').write_text('OWNER = 123\n')
        self.module.write_text('from _private_test_dependency import OWNER\nfrom aiogram import Router\ndef create_demo_router(owner):\n    assert owner == OWNER\n    return Router()\n')
        class FakeRouter:
            pass
        argv = ['/tmp/private_application_test.py', 'install', '--module-file', str(self.module)]
        with mock.patch.object(installer.sys, 'argv', argv), \
                mock.patch.object(installer.sys, 'prefix', str(self.root / '.venv')), \
                mock.patch.object(installer.sys, 'path', ['/tmp'] + list(installer.sys.path)), \
                mock.patch.object(installer.Path, 'cwd', return_value=self.root), \
                mock.patch.dict('sys.modules', {'aiogram': SimpleNamespace(Router=FakeRouter)}), \
                mock.patch.object(installer, 'owner_id', return_value=123), \
                mock.patch.object(installer, 'stop') as stopped, \
                mock.patch.object(installer, 'start', return_value=456) as started, \
                redirect_stdout(io.StringIO()) as output:
            installer.main()
            stopped.assert_called_once_with(self.root.resolve())
            started.assert_called_once_with(self.root.resolve())
            self.assertIn('install complete', output.getvalue())
        installer.sys.modules.pop('_private_test_dependency', None)


if __name__ == '__main__':
    unittest.main()
