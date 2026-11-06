#!/usr/bin/env python3
"""Install/roll back the private demo in the current bot, using its existing venv."""
import argparse
import ast
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time

FILES = ('bot/chat_main.py', '.env', 'deploy/isp/autodeploy.sh', 'bot/application_demo.py')
BACKUP = 'logs/private-application-test-backup'
ACTIVE = 'logs/private-application-test.active'
HOOK = '''    # Private application demo: temporary, owner-only.
    if os.getenv("APPLICATION_DEMO_ENABLED", "").strip() == "1":
        if settings.telegram_admin_id and settings.telegram_admin_id > 0:
            from bot.application_demo import create_demo_router
            dp.include_router(create_demo_router(settings.telegram_admin_id))
'''
GUARD = '\n# Temporary private demo: leave its server files intact.\n[ ! -e "$LOG_DIR/private-application-test.active" ] || exit 0\n'


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def read(path):
    if path.is_symlink():
        raise RuntimeError('Refusing symlink: ' + str(path))
    return path.read_bytes() if path.exists() else None


def write(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.private-test-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def insert_once(data, anchor, addition, before=False):
    if data.count(anchor) != 1:
        raise RuntimeError('Expected exactly one patch anchor')
    return data.replace(anchor, addition + anchor if before else anchor + addition, 1)


def enable_env(data):
    key = re.compile(br'^[ \t]*(?:export[ \t]+)?APPLICATION_DEMO_ENABLED[ \t]*=')
    lines, found = [], False
    for line in data.splitlines(keepends=True):
        if key.match(line):
            line = b'APPLICATION_DEMO_ENABLED=1' + (b'\r\n' if line.endswith(b'\r\n') else b'\n')
            found = True
        lines.append(line)
    result = b''.join(lines)
    return result if found else result + (b'\n' if result and not result.endswith(b'\n') else b'') + b'APPLICATION_DEMO_ENABLED=1\n'


def owner_id(root):
    from dotenv import dotenv_values
    values = dotenv_values(root / '.env')
    raw = os.environ.get('TELEGRAM_ADMIN_ID', values.get('TELEGRAM_ADMIN_ID') or '')
    if not re.fullmatch(r'[1-9][0-9]*', raw.strip()):
        raise RuntimeError('A positive TELEGRAM_ADMIN_ID is required')
    return int(raw)


def check_module(path, owner):
    try:
        source = path.read_text(encoding='utf-8')
        ast.parse(source, feature_version=8)
        compile(source, str(path), 'exec')
        spec = importlib.util.spec_from_file_location('_private_demo_candidate', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        from aiogram import Router
        if not isinstance(module.create_demo_router(owner), Router):
            raise TypeError('Expected Router')
    except Exception:
        raise RuntimeError('Demo module failed Python 3.8 syntax/import/router check') from None
    finally:
        sys.modules.pop('_private_demo_candidate', None)


def prepare(root, module_path):
    original = {name: read(root / name) for name in FILES}
    if any(original[name] is None for name in FILES[:3]):
        raise RuntimeError('Missing existing bot, .env, or autodeploy script')
    if b'APPLICATION_DEMO_ENABLED' in original[FILES[0]]:
        raise RuntimeError('Demo hook already exists')
    patched = dict(original)
    patched[FILES[0]] = insert_once(original[FILES[0]], b'    dp.include_router(router)\n', HOOK.encode(), True)
    ast.parse(patched[FILES[0]], feature_version=8)
    patched[FILES[1]] = enable_env(original[FILES[1]])
    patched[FILES[2]] = insert_once(original[FILES[2]], b'LOG_DIR="$BOT_DIR/logs"\n', GUARD.encode())
    patched[FILES[3]] = module_path.read_bytes()
    return original, patched


def backup(root, original, patched):
    directory = root / BACKUP
    directory.mkdir(mode=0o700)
    manifest = {}
    for index, name in enumerate(FILES):
        source = root / name
        mode = stat.S_IMODE(source.stat().st_mode) if source.exists() else 0o644
        filename = str(index)
        if original[name] is not None:
            write(directory / filename, original[name])
        manifest[name] = {'original': digest(original[name]), 'installed': digest(patched[name]), 'mode': mode, 'backup': filename}
    write(directory / 'manifest.json', json.dumps(manifest).encode())
    return manifest


def restore(root, manifest, partial=False, validate_only=False):
    if set(manifest) != set(FILES):
        raise RuntimeError('Unexpected backup manifest files')
    originals = {}
    for index, name in enumerate(FILES):
        item = manifest[name]
        if item['backup'] != str(index):
            raise RuntimeError('Unexpected backup path')
        allowed = {item['installed'], item['original']} if partial else {item['installed']}
        if digest(read(root / name)) not in allowed:
            raise RuntimeError('External edit detected; rollback stopped: ' + name)
        data = read(root / BACKUP / item['backup']) if item['original'] is not None else None
        if digest(data) != item['original']:
            raise RuntimeError('Backup checksum mismatch: ' + name)
        originals[name] = data
    if validate_only:
        return
    for name, data in originals.items():
        if data is None:
            (root / name).unlink(missing_ok=True)
        else:
            write(root / name, data, manifest[name]['mode'])
    (root / ACTIVE).unlink(missing_ok=True)


def lock_free(root):
    with (root / 'logs/chat-bot.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False


def verified_pid(root):
    try:
        pid = int((root / 'logs/chat-bot.pid').read_text().strip())
        args = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
        matches = any(args[i:i + 2] == [b'-m', b'bot.chat_main'] for i in range(len(args) - 1))
        if pid <= 1 or not matches or (Path('/proc') / str(pid) / 'cwd').resolve() != root:
            raise ValueError()
        return pid
    except (OSError, ValueError):
        raise RuntimeError('Cannot verify the existing bot PID/cwd/command') from None


def stop(root):
    if lock_free(root):
        return
    pid = verified_pid(root)
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if lock_free(root):
            return
        time.sleep(0.25)
    raise RuntimeError('Bot did not release its lock after TERM; no forced kill')


def start(root):
    env = dict(os.environ)
    env.pop('APPLICATION_DEMO_ENABLED', None)  # Persisted .env also works with watchdog.
    with (root / 'logs/chat-bot.log').open('ab') as output:
        process = subprocess.Popen([sys.executable, '-m', 'bot.chat_main'], cwd=str(root), env=env,
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                   close_fds=True, start_new_session=True)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and process.poll() is None:
        try:
            if verified_pid(root) == process.pid and not lock_free(root):
                time.sleep(2)
                if process.poll() is None and not lock_free(root):
                    return process.pid
        except RuntimeError:
            pass
        time.sleep(0.25)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            raise RuntimeError('New process did not stop; manual recovery required') from None
    raise RuntimeError('New bot failed the PID/lock startup check')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'rollback'))
    parser.add_argument('--module-file', type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    if sys.version_info < (3, 8) or Path(sys.prefix).resolve() != (root / '.venv').resolve():
        raise RuntimeError('Run from the bot root using .venv/bin/python (Python 3.8+)')
    if not (root / 'logs').is_dir():
        raise RuntimeError('Existing bot logs directory is required')
    sys.path.insert(0, str(root))  # The installer may be executed from /tmp.
    with (root / 'logs/bot-control.lock').open('a') as control:
        fcntl.flock(control, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'rollback':
            manifest = json.loads((root / BACKUP / 'manifest.json').read_text())
            restore(root, manifest, validate_only=True)
            stop(root)
            restore(root, manifest)
            pid = start(root)
        else:
            if not args.module_file or (root / BACKUP).exists() or (root / ACTIVE).exists():
                raise RuntimeError('Module file required; existing demo backup/marker must be preserved')
            check_module(args.module_file.resolve(), owner_id(root))
            original, patched = prepare(root, args.module_file.resolve())
            manifest = backup(root, original, patched)
            stopped = False
            try:
                write(root / ACTIVE, b'private application demo\n')
                for name, data in patched.items():
                    write(root / name, data, manifest[name]['mode'])
                stop(root)
                stopped = True
                pid = start(root)
            except Exception:
                if stopped and not lock_free(root):
                    raise RuntimeError('New process still holds the lock; guard and backup retained for recovery') from None
                restore(root, manifest, partial=True)
                if lock_free(root):
                    start(root)
                raise
    print('OK: {} complete; bot PID {}; lock held. Verify the private command in Telegram.'.format(args.action, pid))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('ERROR: ' + (str(error) if isinstance(error, RuntimeError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)
