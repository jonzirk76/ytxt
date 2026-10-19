import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

from requests.exceptions import ConnectionError
from youtube_transcript_api import TranscriptsDisabled

from ytxt import __version__
from ytxt.cli import get_title, get_video_id, main, safe_filename


VIDEO_ID = "dQw4w9WgXcQ"


class VideoIdTests(unittest.TestCase):
    def test_original_supported_url_forms(self):
        for value in (
            VIDEO_ID,
            f"  {VIDEO_ID}\n",
            f"https://youtube.com/watch?v={VIDEO_ID}",
            f"https://www.youtube.com/watch?feature=shared&v={VIDEO_ID}&t=30",
            f"https://m.youtube.com/watch?v={VIDEO_ID}",
            f"https://youtu.be/{VIDEO_ID}?si=shared",
            f"https://www.youtu.be/{VIDEO_ID}",
            f"https://www.youtube.com/shorts/{VIDEO_ID}",
            f"https://www.youtube.com/live/{VIDEO_ID}",
            f"https://www.youtube.com/embed/{VIDEO_ID}",
        ):
            with self.subTest(value=value):
                self.assertEqual(get_video_id(value), VIDEO_ID)

    def test_invalid_urls_and_extracted_ids(self):
        for value in (
            "", "bad-video", "https://youtu.be/", "https://youtu.be/short",
            "https://youtube.com/watch", "https://youtube.com/watch?v=../bad",
            f"https://youtube.com.evil.example/watch?v={VIDEO_ID}",
            f"https://evil.example/watch?v={VIDEO_ID}",
            f"file://youtube.com/watch?v={VIDEO_ID}",
            f"https://youtube.com/playlist?list={VIDEO_ID}",
            "é" * 11,
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                get_video_id(value)


class TitleTests(unittest.TestCase):
    def test_oembed_title(self):
        with patch("ytxt.cli.urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value = io.BytesIO(
                b'{"title": "A useful video"}'
            )
            self.assertEqual(get_title(VIDEO_ID), "A useful video")
            self.assertEqual(request.call_args.kwargs["timeout"], 10)

    def test_title_lookup_failure_falls_back_to_id(self):
        with patch("ytxt.cli.urllib.request.urlopen", side_effect=URLError("offline")):
            self.assertEqual(get_title(VIDEO_ID), VIDEO_ID)

    def test_malformed_title_response_falls_back_to_id(self):
        for data in (b"not json", b"{}", b"[]", b'{"title": null}', b'{"title":" "}'):
            with self.subTest(data=data), patch("ytxt.cli.urllib.request.urlopen") as request:
                request.return_value.__enter__.return_value = io.BytesIO(data)
                self.assertEqual(get_title(VIDEO_ID), VIDEO_ID)

    def test_safe_unicode_filename(self):
        filename = safe_filename('  Café: "why/when?" \\ yes|no*<>\x00\n. ', VIDEO_ID)
        self.assertTrue(filename.startswith("Café"))
        for character in '<>:"/\\|?*\x00\n':
            self.assertNotIn(character, filename)
        self.assertTrue(filename.endswith(".txt"))

    def test_empty_and_long_titles(self):
        self.assertEqual(safe_filename(" . . ", VIDEO_ID), f"{VIDEO_ID}.txt")
        filename = safe_filename("😀" * 200, VIDEO_ID)
        self.assertLessEqual(len(filename.encode("utf-8")), 204)
        self.assertTrue(filename.endswith(".txt"))


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(self.stdout))
        stack.enter_context(contextlib.redirect_stderr(self.stderr))
        stack.enter_context(patch.dict(os.environ, {
            "YTXT_OUTPUT_DIR": "", "TERMUX_VERSION": "", "PREFIX": "",
        }))
        stack.enter_context(patch("ytxt.cli.Path.home", return_value=self.home))
        self.api = stack.enter_context(patch("ytxt.cli.YouTubeTranscriptApi"))
        self.api.return_value.fetch.return_value = [
            SimpleNamespace(text="First caption."),
            SimpleNamespace(text="Second caption — café."),
        ]
        self.title = stack.enter_context(patch("ytxt.cli.get_title", return_value="A video"))

    def test_original_default_destination_and_text_format(self):
        self.assertEqual(main([f"https://youtu.be/{VIDEO_ID}"]), 0)
        output = self.home / "Downloads" / "A video.txt"
        self.assertEqual(output.read_text(encoding="utf-8"),
                         "First caption.\nSecond caption — café.\n")
        self.assertEqual(self.stdout.getvalue(), f"Saved: {output}\n")
        self.api.return_value.fetch.assert_called_once_with(VIDEO_ID, languages=["en"])

    def test_phone_output_preference(self):
        target = self.home / "storage" / "downloads"
        with patch.dict(os.environ, {"YTXT_OUTPUT_DIR": str(target)}):
            self.assertEqual(main([VIDEO_ID]), 0)
        self.assertTrue((target / "A video.txt").is_file())

    def test_termux_defaults_to_shared_android_downloads(self):
        target = self.home / "storage" / "downloads"
        target.mkdir(parents=True)
        with patch.dict(os.environ, {"TERMUX_VERSION": "0.118.0"}):
            self.assertEqual(main([VIDEO_ID]), 0)
        self.assertTrue((target / "A video.txt").is_file())
        self.assertFalse((self.home / "Downloads").exists())

    def test_termux_without_storage_setup_explains_setup_before_fetching(self):
        with patch.dict(os.environ, {"PREFIX": "/data/data/com.termux/files/usr"}):
            self.assertEqual(main([VIDEO_ID]), 1)
        self.assertIn("termux-setup-storage", self.stderr.getvalue())
        self.assertFalse((self.home / "storage").exists())
        self.api.assert_not_called()

    def test_termux_can_choose_private_output_without_shared_storage(self):
        target = self.home / "private-transcripts"
        with patch.dict(os.environ, {"TERMUX_VERSION": "0.118.0"}):
            self.assertEqual(main([VIDEO_ID, "-d", str(target)]), 0)
        self.assertTrue((target / "A video.txt").is_file())

    def test_output_option_overrides_environment_and_passes_languages(self):
        target = self.home / "chosen"
        env_target = self.home / "not-chosen"
        with patch.dict(os.environ, {"YTXT_OUTPUT_DIR": str(env_target)}):
            self.assertEqual(main([VIDEO_ID, "-d", str(target), "-l", "es", "en"]), 0)
        self.assertTrue((target / "A video.txt").is_file())
        self.assertFalse(env_target.exists())
        self.api.return_value.fetch.assert_called_once_with(VIDEO_ID, languages=["es", "en"])

    def test_invalid_url_fails_before_network_requests(self):
        with self.assertRaises(SystemExit) as error:
            main(["https://youtu.be/bad"])
        self.assertEqual(error.exception.code, 2)
        self.api.assert_not_called()
        self.title.assert_not_called()

    def test_caption_failure_keeps_existing_file(self):
        target = self.home / "Downloads" / "A video.txt"
        target.parent.mkdir()
        target.write_text("Existing transcript", encoding="utf-8")
        self.api.return_value.fetch.side_effect = TranscriptsDisabled(VIDEO_ID)
        self.assertEqual(main([VIDEO_ID]), 1)
        self.assertEqual(target.read_text(encoding="utf-8"), "Existing transcript")
        self.assertIn("ytxt:", self.stderr.getvalue())
        self.assertNotIn("Saved:", self.stdout.getvalue())

    def test_network_failure_is_a_readable_error(self):
        self.api.return_value.fetch.side_effect = ConnectionError("offline")
        self.assertEqual(main([VIDEO_ID]), 1)
        self.assertIn("offline", self.stderr.getvalue())
        self.assertFalse((self.home / "Downloads").exists())

    def test_output_filesystem_error(self):
        target = self.home / "a-file"
        target.write_text("not a directory", encoding="utf-8")
        self.assertEqual(main([VIDEO_ID, "-d", str(target)]), 1)
        self.assertIn("ytxt:", self.stderr.getvalue())

    def test_version_does_not_need_network(self):
        with self.assertRaises(SystemExit) as error:
            main(["--version"])
        self.assertEqual(error.exception.code, 0)
        self.assertIn(__version__, self.stdout.getvalue())
        self.api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
