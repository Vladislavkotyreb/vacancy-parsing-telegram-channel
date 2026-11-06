"""Temporary deployment checks; no process, network, or service operations."""
import importlib.util
import io
import json
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

    def upgrade_candidates(self):
        module = self.root / 'new_candidate.py'
        helper = self.root / 'pdf_candidate.py'
        module.write_bytes(b'# upgraded application demo\n')
        helper.write_bytes(b'# new PDF worker\n')
        return module, helper

    def test_upgrade_preserves_original_backup_and_full_rollback(self):
        original, installed, before = self.installed(prior_module=True)
        module, helper = self.upgrade_candidates()
        backup_path = self.root / installer.BACKUP
        backups = {path.name: path.read_bytes() for path in backup_path.iterdir() if path.name.isdigit()}
        with mock.patch.object(installer, 'owner_id', return_value=123), \
                mock.patch.object(installer, 'check_upgrade') as checked, \
                mock.patch.object(installer, 'stop') as stopped, \
                mock.patch.object(installer, 'start', return_value=789):
            self.assertEqual(installer.upgrade(self.root, module, helper), 789)
        checked.assert_called_once()
        stopped.assert_called_once_with(self.root)
        updated = json.loads((backup_path / 'manifest.json').read_bytes())
        for name in installer.FILES:
            self.assertEqual(updated[name]['original'], before[name]['original'])
        self.assertEqual(updated[installer.PDF_FILE]['original'], None)
        self.assertEqual(updated['bot/application_demo.py']['installed'], installer.digest(module.read_bytes()))
        self.assertEqual(updated[installer.PDF_FILE]['installed'], installer.digest(helper.read_bytes()))
        self.assertEqual({name: (backup_path / name).read_bytes() for name in backups}, backups)
        for name in installer.FILES[:3]:
            self.assertEqual((self.root / name).read_bytes(), installed[name])
        (self.root / installer.PDF_FILE).write_bytes(b'# external worker edit\n')
        with self.assertRaisesRegex(RuntimeError, 'External edit'):
            installer.restore(self.root, updated)
        self.assertEqual((self.root / installer.PDF_FILE).read_bytes(), b'# external worker edit\n')
        (self.root / installer.PDF_FILE).write_bytes(helper.read_bytes())
        installer.restore(self.root, updated)
        for name, data in original.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assertFalse((self.root / installer.PDF_FILE).exists())

    def test_upgrade_failure_restores_previous_module_and_manifest(self):
        _, installed, _ = self.installed()
        module, helper = self.upgrade_candidates()
        manifest_path = self.root / installer.BACKUP / 'manifest.json'
        before = manifest_path.read_bytes()
        with mock.patch.object(installer, 'owner_id', return_value=123), \
                mock.patch.object(installer, 'check_upgrade'), mock.patch.object(installer, 'stop'), \
                mock.patch.object(installer, 'lock_free', return_value=True), \
                mock.patch.object(installer, 'start', side_effect=[RuntimeError('startup failed'), 456]) as started:
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                installer.upgrade(self.root, module, helper)
        self.assertEqual(started.call_count, 2)
        self.assertEqual((self.root / 'bot/application_demo.py').read_bytes(), installed['bot/application_demo.py'])
        self.assertEqual(manifest_path.read_bytes(), before)
        self.assertFalse((self.root / installer.PDF_FILE).exists())
        self.assertTrue((self.root / installer.ACTIVE).exists())

    def test_upgrade_preflight_failure_leaves_running_install_unchanged(self):
        _, installed, _ = self.installed()
        module, helper = self.upgrade_candidates()
        with mock.patch.object(installer, 'owner_id', return_value=123), \
                mock.patch.object(installer, 'check_upgrade', side_effect=RuntimeError('preflight failed')), \
                mock.patch.object(installer, 'stop') as stopped:
            with self.assertRaisesRegex(RuntimeError, 'preflight failed'):
                installer.upgrade(self.root, module, helper)
        stopped.assert_not_called()
        self.assertEqual((self.root / 'bot/application_demo.py').read_bytes(), installed['bot/application_demo.py'])
        self.assertFalse((self.root / installer.PDF_FILE).exists())

    def test_upgrade_rejects_external_edits_and_unmanaged_worker(self):
        self.installed()
        module, helper = self.upgrade_candidates()
        with mock.patch.object(installer, 'stop') as stopped:
            (self.root / installer.PDF_FILE).write_bytes(b'# someone else owns this\n')
            with self.assertRaisesRegex(RuntimeError, 'Unmanaged'):
                installer.upgrade(self.root, module, helper)
            (self.root / installer.PDF_FILE).unlink()
            (self.root / '.env').write_bytes(b'EXTERNAL=change\n')
            with self.assertRaisesRegex(RuntimeError, 'External edit'):
                installer.upgrade(self.root, module, helper)
        stopped.assert_not_called()

    def test_upgrade_requires_active_marker(self):
        self.installed()
        (self.root / installer.ACTIVE).unlink()
        module, helper = self.upgrade_candidates()
        with mock.patch.object(installer, 'stop') as stopped, self.assertRaisesRegex(RuntimeError, 'active demo'):
            installer.upgrade(self.root, module, helper)
        stopped.assert_not_called()

    def test_upgrade_preflight_stages_siblings_and_checks_exact_dependency(self):
        modules = {
            'bot/application_demo.py': b'from pathlib import Path\nfrom aiogram import Router\ndef create_demo_router(owner):\n    assert Path(__file__).with_name("application_demo_pdf.py").exists()\n    return Router()\n',
            installer.PDF_FILE: b'def extract_pdf(data):\n    return "test"\n',
        }
        class FakeRouter:
            pass
        with mock.patch.dict('sys.modules', {'pypdf': SimpleNamespace(__version__='5.9.0'), 'aiogram': SimpleNamespace(Router=FakeRouter)}):
            installer.check_upgrade(modules, 123)
        with mock.patch.dict('sys.modules', {'pypdf': SimpleNamespace(__version__='6.0.0')}), self.assertRaisesRegex(RuntimeError, 'pypdf==5.9.0'):
            installer.check_upgrade(modules, 123)

    def test_fresh_install_can_backup_and_restore_existing_pdf_helper(self):
        module, helper = self.upgrade_candidates()
        prior = b'# existing helper owned by the server\n'
        installer.write(self.root / installer.PDF_FILE, prior, 0o640)
        original, patched = installer.prepare(self.root, module, helper)
        manifest = installer.backup(self.root, original, patched)
        for name, data in patched.items():
            installer.write(self.root / name, data, manifest[name]['mode'])
        self.assertEqual((self.root / installer.PDF_FILE).read_bytes(), helper.read_bytes())
        self.assertEqual(manifest[installer.PDF_FILE]['original'], installer.digest(prior))
        installer.restore(self.root, manifest)
        self.assertEqual((self.root / installer.PDF_FILE).read_bytes(), prior)
        self.assertEqual(stat.S_IMODE((self.root / installer.PDF_FILE).stat().st_mode), 0o640)

    def test_failed_later_upgrade_preserves_previously_installed_worker(self):
        self.installed()
        module, helper = self.upgrade_candidates()
        with mock.patch.object(installer, 'owner_id', return_value=123), \
                mock.patch.object(installer, 'check_upgrade'), mock.patch.object(installer, 'stop'), \
                mock.patch.object(installer, 'lock_free', return_value=True), \
                mock.patch.object(installer, 'start', side_effect=[123, RuntimeError('failed second start'), 456]):
            installer.upgrade(self.root, module, helper)
            previous_helper = (self.root / installer.PDF_FILE).read_bytes()
            previous_manifest = (self.root / installer.BACKUP / 'manifest.json').read_bytes()
            helper.write_bytes(b'# next worker version\n')
            with self.assertRaisesRegex(RuntimeError, 'failed second start'):
                installer.upgrade(self.root, module, helper)
        self.assertEqual((self.root / installer.PDF_FILE).read_bytes(), previous_helper)
        self.assertEqual((self.root / installer.BACKUP / 'manifest.json').read_bytes(), previous_manifest)


if __name__ == '__main__':
    unittest.main()
