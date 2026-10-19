import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ytxt.storage import atomic_write, install_share_hook
from ytxt.transcripts import load_record

ROOT = Path(__file__).resolve().parents[1]


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def test_failed_atomic_replace_preserves_original_and_cleans_temporary(self):
        target = self.home / "transcript.txt"
        target.write_text("Existing transcript")
        with patch("ytxt.storage.Path.replace", side_effect=OSError("full disk")):
            with self.assertRaises(OSError):
                atomic_write(target, "Replacement")
        self.assertEqual(target.read_text(), "Existing transcript")
        self.assertEqual(list(self.home.iterdir()), [target])

    def test_corrupt_or_unsafe_history_is_ignored(self):
        target = self.home / "record.json"
        metadata = {"schema": 1, "title": "Video", "video_id": "dQw4w9WgXcQ", "downloaded_at": "date"}
        for data in (
            "not JSON", "[]", "{}",
            json.dumps({**metadata, "files": {"../notes.txt": "hash"}, "text_files": ["../notes.txt"]}),
            json.dumps({**metadata, "files": {"a.txt": "hash"}, "text_files": [["not-a-name"]]}),
        ):
            target.write_text(data)
            self.assertIsNone(load_record(target))

    def test_share_hook_backs_up_old_hook_and_quotes_arguments(self):
        target = self.home / "bin/termux-url-opener"
        target.parent.mkdir()
        target.write_text("#!/bin/sh\n# Existing unrelated hook\n")
        fake_python = self.home / "python with spaces"
        fake_python.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$YTXT_TEST_ARGS"\n')
        fake_python.chmod(0o700)
        args_file = self.home / "arguments.txt"
        with patch("ytxt.storage.Path.home", return_value=self.home), \
             patch("ytxt.storage.sys.executable", str(fake_python)), \
             patch.dict(os.environ, {"TERMUX_VERSION": "test", "PREFIX": str(self.home / "prefix")}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(install_share_hook(), target)
                install_share_hook()
        backups = list(target.parent.glob("termux-url-opener.backup.*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("Existing unrelated hook", backups[0].read_text())
        self.assertTrue(target.stat().st_mode & 0o100)
        shared = 'A title; $(touch should-not-run)\nhttps://youtu.be/dQw4w9WgXcQ'
        result = subprocess.run(["sh", str(target), shared],
                                env={**os.environ, "YTXT_TEST_ARGS": str(args_file)},
                                cwd=self.home, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args_file.read_text(), f"-m\nytxt\n--shared-text\n{shared}\n")
        self.assertFalse((self.home / "should-not-run").exists())


class InstallerTests(unittest.TestCase):
    def test_installer_initializes_folder_and_preserves_previous_command(self):
        # Exercise the real shell installer and Python setup command, replacing
        # only pip's network installation step with a pre-provisioned environment.
        with tempfile.TemporaryDirectory(prefix="ytxt installer ") as temporary:
            base = Path(temporary)
            application, commands, output = base / "app", base / "bin", base / "Downloads/ytxt"
            venv_bin = application / "venv/bin"
            venv_bin.mkdir(parents=True)
            commands.mkdir()
            (commands / "ytxt").write_text("The old standalone script")
            fake_python = venv_bin / "python"
            fake_python.write_text("#!/bin/sh\nexit 0\n")
            fake_python.chmod(0o700)
            console = venv_bin / "ytxt"
            console.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m ytxt "$@"\n')
            console.chmod(0o700)
            result = subprocess.run(
                ["sh", str(ROOT / "install.sh"), "--dev"],
                env={**os.environ, "PYTHON": sys.executable,
                     "YTXT_HOME": str(application), "YTXT_OUTPUT_DIR": str(output),
                     "YTXT_BIN_DIR": str(commands), "TERMUX_VERSION": "", "PREFIX": "",
                     "PYTHONPATH": str(ROOT / "src")},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((output / ".ytxt/history").is_dir())
            self.assertTrue((application / "templates/discussion.txt").is_file())
            self.assertTrue((application / "browser/ytxt-chatgpt.user.js").is_file())
            self.assertTrue((commands / "ytxt").is_symlink())
            backups = list(commands.glob("ytxt.backup.*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), "The old standalone script")
            self.assertIn("ytxt folder ready:", result.stdout)


if __name__ == "__main__":
    unittest.main()
