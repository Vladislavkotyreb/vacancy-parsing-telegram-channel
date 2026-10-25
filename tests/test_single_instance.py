"""Один экземпляр chat_main: замок flock (сбои pid-замка 24–25.10.2026)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from bot import chat_main

REPO = Path(__file__).resolve().parent.parent


class SingleInstanceLockTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        logs = Path(self._tmp.name) / "logs"
        self.pid_file = logs / "chat-bot.pid"
        self.lock_file = logs / "chat-bot.lock"
        for name, value in (("PID_FILE", self.pid_file), ("LOCK_FILE", self.lock_file)):
            patcher = mock.patch.object(chat_main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(chat_main._release_single_instance)

    def _other_process_holding_lock(self) -> subprocess.Popen:
        code = textwrap.dedent(f"""
            import fcntl, sys, time
            h = open({str(self.lock_file)!r}, "a")
            fcntl.flock(h, fcntl.LOCK_EX)
            print("ok", flush=True)
            time.sleep(30)
        """)
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.assertEqual(proc.stdout.readline().strip(), "ok")
        return proc

    def test_starts_and_writes_pid(self):
        chat_main._acquire_single_instance()
        self.assertEqual(self.pid_file.read_text().strip(), str(os.getpid()))

    def test_running_copy_blocks_start(self):
        self._other_process_holding_lock()
        with self.assertRaises(SystemExit) as ctx:
            chat_main._acquire_single_instance()
        self.assertEqual(ctx.exception.code, 1)

    def test_killed_copy_does_not_block(self):
        """kill -9 не оставляет «залипшего» замка."""
        proc = self._other_process_holding_lock()
        proc.kill()
        proc.wait()
        chat_main._acquire_single_instance()

    def test_stale_pid_of_foreign_live_process_does_not_block(self):
        """Номер умершего бота достался чужой программе — раньше бот не поднимался."""
        other = subprocess.Popen(["sleep", "30"])
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(other.pid))
        chat_main._acquire_single_instance()
        self.assertEqual(self.pid_file.read_text().strip(), str(os.getpid()))

    def test_deleted_pid_file_does_not_allow_second_copy(self):
        """Ручной `rm -f chat-bot.pid` больше не открывает дорогу дублю."""
        self._other_process_holding_lock()
        self.pid_file.unlink(missing_ok=True)
        with self.assertRaises(SystemExit):
            chat_main._acquire_single_instance()

    def test_release_keeps_foreign_pid_file(self):
        chat_main._acquire_single_instance()
        self.pid_file.write_text("999999")
        chat_main._release_single_instance()
        self.assertEqual(self.pid_file.read_text(), "999999")


class ConcurrentStartTest(unittest.TestCase):
    def test_simultaneous_starts_leave_exactly_one(self):
        tmp = tempfile.mkdtemp()
        code = textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(REPO)!r})
            from pathlib import Path
            from bot import chat_main
            chat_main.PID_FILE = Path({tmp!r}) / "chat-bot.pid"
            chat_main.LOCK_FILE = Path({tmp!r}) / "chat-bot.lock"
            chat_main._acquire_single_instance()
            print("started", flush=True)
            time.sleep(3)
        """)
        procs = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True) for _ in range(6)]
        outputs = [p.communicate(timeout=30)[0] for p in procs]
        self.assertEqual(sum("started" in out for out in outputs), 1)


if __name__ == "__main__":
    unittest.main()
