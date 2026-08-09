"""Защёлка одного экземпляра chat_main: pid-lock не должен блокировать сам себя."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bot import chat_main


class SingleInstanceLockTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.pid_file = Path(self._tmp.name) / "logs" / "chat-bot.pid"
        patcher = mock.patch.object(chat_main, "PID_FILE", self.pid_file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_starts_when_no_pid_file(self):
        chat_main._acquire_single_instance()
        self.assertEqual(self.pid_file.read_text().strip(), str(os.getpid()))

    def test_own_pid_in_file_does_not_block_start(self):
        """Watchdog пишет pid бота в файл раньше, чем бот доходит до захвата."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))

        chat_main._acquire_single_instance()

        self.assertEqual(self.pid_file.read_text().strip(), str(os.getpid()))

    def test_stale_pid_file_is_replaced(self):
        dead = subprocess.Popen(["sleep", "0"])
        dead.wait()

        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(dead.pid))

        chat_main._acquire_single_instance()

        self.assertEqual(self.pid_file.read_text().strip(), str(os.getpid()))

    def test_garbage_pid_file_is_replaced(self):
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text("не число")

        chat_main._acquire_single_instance()

        self.assertEqual(self.pid_file.read_text().strip(), str(os.getpid()))

    def test_live_foreign_pid_still_blocks_start(self):
        """Защёлка обязана продолжать ловить реально запущенный второй экземпляр."""
        other = subprocess.Popen(["sleep", "30"])
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)

        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(other.pid))

        with self.assertRaises(SystemExit) as ctx:
            chat_main._acquire_single_instance()

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(self.pid_file.read_text().strip(), str(other.pid))


if __name__ == "__main__":
    unittest.main()
