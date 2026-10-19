import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from ytxt.chatgpt import launch_draft, prepare_draft, save_draft


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.transcript = self.root / "Café & questions [video-id].txt"
        self.transcript.write_text("PRIVATE TRANSCRIPT BODY")
        self.prompt = "Discuss the evidence & assumptions.\nI want to add a question."

    def test_link_preserves_prompt_and_file_paths_without_submitting(self):
        draft = prepare_draft([self.transcript, self.transcript], self.prompt)
        link = urlparse(draft.url)
        query = parse_qs(link.query)
        self.assertEqual((link.scheme, link.netloc), ("codex", "new"))
        self.assertEqual(set(query), {"prompt", "path"})
        self.assertIn(self.prompt, query["prompt"][0])
        self.assertIn(str(self.transcript), query["prompt"][0])
        self.assertEqual(query["path"], [str(self.root)])
        self.assertEqual(draft.files, (self.transcript,))
        self.assertNotIn("PRIVATE TRANSCRIPT BODY", draft.url)
        self.assertNotIn("attachments", query)
        self.assertNotIn("submit", query)

    def test_common_workspace_for_files_in_different_folders(self):
        other = self.root / "subfolder/other.txt"
        other.parent.mkdir()
        other.write_text("Another transcript")
        draft = prepare_draft([other, self.transcript], self.prompt)
        self.assertEqual(draft.workspace, self.root)
        self.assertEqual(draft.files, (other, self.transcript))

    def test_only_existing_text_files_are_accepted(self):
        invalid = self.root / "raw.json"
        invalid.write_text("{}")
        for paths in ([], [invalid], [self.root]):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                prepare_draft(paths, self.prompt)
        with self.assertRaises(FileNotFoundError):
            prepare_draft([self.root / "missing.txt"], self.prompt)

    def test_oversized_draft_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "too long"):
            prepare_draft([self.transcript], "a" * 31000)

    def test_saved_draft_keeps_prompt_manifest_and_source_unchanged(self):
        draft = prepare_draft([self.transcript], self.prompt)
        with patch.dict(os.environ, {"YTXT_HOME": str(self.root / "app")}):
            folder = save_draft(draft)
            second = save_draft(draft)
        self.assertNotEqual(folder, second)
        self.assertEqual((folder / "prompt.txt").read_text(), draft.prompt + "\n")
        manifest = json.loads((folder / "draft.json").read_text())
        self.assertEqual(manifest["files"], [str(self.transcript)])
        self.assertEqual(manifest["url"], draft.url)
        self.assertEqual(self.transcript.read_text(), "PRIVATE TRANSCRIPT BODY")

    def test_linux_uses_registered_native_handler_with_no_shell(self):
        draft = prepare_draft([self.transcript], self.prompt)
        with patch("ytxt.chatgpt.sys.platform", "linux"), \
             patch("ytxt.chatgpt.is_termux", return_value=False), \
             patch("ytxt.chatgpt.shutil.which", side_effect=lambda name: "/usr/bin/" + name), \
             patch("ytxt.chatgpt.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "chatgpt.desktop\n", "")
            launch_draft(draft)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0],
                         ["/usr/bin/xdg-mime", "query", "default", "x-scheme-handler/codex"])
        self.assertEqual(run.call_args_list[1].args[0], ["/usr/bin/xdg-open", draft.url])
        self.assertNotIn("shell", run.call_args_list[1].kwargs)

    def test_missing_native_handler_does_not_open_browser(self):
        draft = prepare_draft([self.transcript], self.prompt)
        with patch("ytxt.chatgpt.sys.platform", "linux"), \
             patch("ytxt.chatgpt.is_termux", return_value=False), \
             patch("ytxt.chatgpt.shutil.which", side_effect=lambda name: "/usr/bin/" + name), \
             patch("ytxt.chatgpt.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            with self.assertRaisesRegex(OSError, "No desktop app"):
                launch_draft(draft)
            self.assertEqual(run.call_count, 1)

    def test_missing_launcher_is_clear_error(self):
        draft = prepare_draft([self.transcript], self.prompt)
        with patch("ytxt.chatgpt.sys.platform", "linux"), \
             patch("ytxt.chatgpt.is_termux", return_value=False), \
             patch("ytxt.chatgpt.shutil.which", return_value=None):
            with self.assertRaisesRegex(OSError, "xdg-open"):
                launch_draft(draft)

    def test_launch_timeout_is_readable(self):
        draft = prepare_draft([self.transcript], self.prompt)
        with patch("ytxt.chatgpt.sys.platform", "linux"), \
             patch("ytxt.chatgpt.is_termux", return_value=False), \
             patch("ytxt.chatgpt.shutil.which", return_value="/usr/bin/tool"), \
             patch("ytxt.chatgpt.subprocess.run", side_effect=subprocess.TimeoutExpired("tool", 10)):
            with self.assertRaisesRegex(OSError, "timed out"):
                launch_draft(draft)

    def test_termux_does_not_launch_desktop_uri(self):
        draft = prepare_draft([self.transcript], self.prompt)
        with patch("ytxt.chatgpt.is_termux", return_value=True), \
             patch("ytxt.chatgpt.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "require a desktop"):
                launch_draft(draft)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
