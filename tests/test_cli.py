import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from requests.exceptions import ConnectionError
from youtube_transcript_api import FetchedTranscript, FetchedTranscriptSnippet, TranscriptsDisabled

from ytxt import __version__
from ytxt.cli import get_video_id, main, parse_time
from ytxt.transcripts import get_metadata, safe_filename

VIDEO_ID = "dQw4w9WgXcQ"
OTHER_ID = "abcdefghijk"


class VideoIdTests(unittest.TestCase):
    def test_original_supported_url_forms(self):
        for value in (
            VIDEO_ID, f"  {VIDEO_ID}\n", f"https://youtube.com/watch?v={VIDEO_ID}",
            f"https://www.youtube.com/watch?feature=shared&v={VIDEO_ID}&t=30",
            f"https://m.youtube.com/watch?v={VIDEO_ID}", f"https://youtu.be/{VIDEO_ID}?si=shared",
            f"https://www.youtu.be/{VIDEO_ID}", f"https://www.youtube.com/shorts/{VIDEO_ID}",
            f"https://www.youtube.com/live/{VIDEO_ID}", f"https://www.youtube.com/embed/{VIDEO_ID}",
        ):
            with self.subTest(value=value):
                self.assertEqual(get_video_id(value), VIDEO_ID)

    def test_invalid_urls_and_extracted_ids(self):
        for value in (
            "", "bad-video", "https://youtu.be/", "https://youtu.be/short",
            "https://youtube.com/watch", "https://youtube.com/watch?v=../bad",
            f"https://youtube.com.evil.example/watch?v={VIDEO_ID}",
            f"https://evil.example/watch?v={VIDEO_ID}", f"file://youtube.com/watch?v={VIDEO_ID}",
            f"https://youtube.com/playlist?list={VIDEO_ID}", "é" * 11,
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                get_video_id(value)

    def test_time_formats(self):
        for value, expected in (("90", 90), ("1:30", 90), ("01:02:03.5", 3723.5), ("0", 0)):
            self.assertEqual(parse_time(value), expected)
        for value in ("-1", "nan", "inf", "1:99", "1:2:3:4", "text"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                parse_time(value)


class MetadataTests(unittest.TestCase):
    def test_oembed_metadata(self):
        with patch("ytxt.transcripts.urllib.request.urlopen") as request:
            request.return_value.__enter__.return_value = io.BytesIO(
                b'{"title": "A useful video", "author_name": "A channel"}'
            )
            self.assertEqual(get_metadata(VIDEO_ID), {"title": "A useful video", "channel": "A channel"})
            self.assertEqual(request.call_args.kwargs["timeout"], 10)

    def test_lookup_failure_falls_back_to_id(self):
        with patch("ytxt.transcripts.urllib.request.urlopen", side_effect=URLError("offline")):
            self.assertEqual(get_metadata(VIDEO_ID)["title"], VIDEO_ID)

    def test_malformed_response_falls_back_to_id(self):
        for data in (b"not json", b"{}", b"[]", b'{"title": null}', b'{"title":" "}'):
            with self.subTest(data=data), patch("ytxt.transcripts.urllib.request.urlopen") as request:
                request.return_value.__enter__.return_value = io.BytesIO(data)
                self.assertEqual(get_metadata(VIDEO_ID)["title"], VIDEO_ID)

    def test_safe_unicode_filename_includes_id(self):
        filename = safe_filename('  Café: "why/when?" \\ yes|no*<>\x00\n. ', VIDEO_ID)
        self.assertTrue(filename.startswith("Café"))
        self.assertIn(f"[{VIDEO_ID}]", filename)
        for character in '<>:"/\\|?*\x00\n':
            self.assertNotIn(character, filename)
        self.assertTrue(filename.endswith(".txt"))

    def test_empty_and_long_titles(self):
        self.assertEqual(safe_filename(" . . ", VIDEO_ID), f"{VIDEO_ID}.txt")
        self.assertLess(len(safe_filename("😀" * 200, VIDEO_ID, ".1234567890").encode()), 220)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.output = self.home / "Downloads/ytxt"
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(contextlib.redirect_stdout(self.stdout))
        stack.enter_context(contextlib.redirect_stderr(self.stderr))
        stack.enter_context(patch.dict(os.environ, {
            "YTXT_OUTPUT_DIR": "", "TERMUX_VERSION": "", "PREFIX": "",
            "YTXT_HOME": str(self.home / "app"),
        }))
        stack.enter_context(patch("ytxt.storage.Path.home", return_value=self.home))
        self.api = stack.enter_context(patch("ytxt.cli.YouTubeTranscriptApi"))
        self.fetched = FetchedTranscript(
            [FetchedTranscriptSnippet("First caption.", 0, 3),
             FetchedTranscriptSnippet("Second caption — café.", 3, 4),
             FetchedTranscriptSnippet("Later statement.", 40, 4)],
            VIDEO_ID, "English", "en", True,
        )
        self.api.return_value.fetch.return_value = self.fetched
        self.metadata = stack.enter_context(patch("ytxt.transcripts.get_metadata",
                                                  return_value={"title": "A video", "channel": "A channel"}))

    def text_files(self, output=None):
        return sorted((output or self.output).glob("*.txt"))

    def test_default_folder_headers_paragraphs_and_original_json(self):
        self.assertEqual(main([VIDEO_ID]), 0)
        output = self.text_files()[0]
        text = output.read_text(encoding="utf-8")
        self.assertIn(f"[{VIDEO_ID}]", output.name)
        for value in ("Title: A video", "Channel: A channel", f"watch?v={VIDEO_ID}",
                      "Caption language: English (en)", "automatically generated", "Downloaded:"):
            self.assertIn(value, text)
        self.assertIn("First caption. Second caption — café.\n\nLater statement.", text)
        self.assertNotIn("[00:00:", text)
        raw = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual([c["text"] for c in raw["captions"]], [c.text for c in self.fetched])
        self.assertEqual(raw["captions"][1]["start"], 3)
        self.api.return_value.fetch.assert_called_once_with(VIDEO_ID, languages=["en"])

    def test_raw_preserves_caption_lines(self):
        self.assertEqual(main([VIDEO_ID, "--raw"]), 0)
        text = self.text_files()[0].read_text()
        self.assertIn("First caption.\nSecond caption — café.\nLater statement.", text)

    def test_termux_folder_and_output_overrides(self):
        shared = self.home / "storage/downloads"
        shared.mkdir(parents=True)
        with patch.dict(os.environ, {"TERMUX_VERSION": "test"}):
            self.assertEqual(main([VIDEO_ID]), 0)
        self.assertTrue(list((shared / "ytxt").glob("*.txt")))
        explicit = self.home / "chosen"
        with patch.dict(os.environ, {"TERMUX_VERSION": "test", "YTXT_OUTPUT_DIR": str(shared / "other")}):
            self.assertEqual(main([VIDEO_ID, "-d", str(explicit)]), 0)
        self.assertTrue(list(explicit.glob("*.txt")))
        self.assertFalse((shared / "other").exists())

    def test_termux_missing_storage_explains_setup_without_network(self):
        with patch.dict(os.environ, {"PREFIX": "/data/data/com.termux/files/usr"}):
            self.assertEqual(main([VIDEO_ID]), 1)
        self.assertIn("termux-setup-storage", self.stderr.getvalue())
        self.api.assert_not_called()
        self.assertFalse((self.home / "storage").exists())

    def test_environment_destination(self):
        target = self.home / "custom"
        with patch.dict(os.environ, {"YTXT_OUTPUT_DIR": str(target)}):
            self.assertEqual(main([VIDEO_ID]), 0)
        self.assertTrue(list(target.glob("*.txt")))

    def test_section_and_timestamp_selection(self):
        self.assertEqual(main([VIDEO_ID, "--start", "00:03", "--end", "00:07", "--timestamps"]), 0)
        text = self.text_files()[0].read_text()
        self.assertIn("[00:00:03] Second caption — café.", text)
        self.assertIn("Requested section: 00:00:03–00:00:07", text)
        self.assertNotIn("First caption.", text)
        self.assertNotIn("Later statement.", text)
        # The original full fetched transcript remains available.
        self.assertEqual(len(json.loads(self.text_files()[0].with_suffix(".json").read_text())["captions"]), 3)

    def test_section_includes_overlapping_caption(self):
        self.assertEqual(main([VIDEO_ID, "--start", "2", "--end", "3"]), 0)
        text = self.text_files()[0].read_text()
        self.assertIn("First caption.", text)
        self.assertNotIn("Second caption", text)

    def test_empty_section_does_not_create_output(self):
        self.assertEqual(main([VIDEO_ID, "--start", "1000"]), 1)
        self.assertFalse(self.output.exists())
        self.assertIn("No captions overlap", self.stderr.getvalue())

    def test_split_parts_keep_source_ranges_and_all_words(self):
        self.assertEqual(main([VIDEO_ID, "--split-words", "3"]), 0)
        paths = self.text_files()
        self.assertEqual(len(paths), 3)
        body_words = []
        for index, path in enumerate(paths, 1):
            text = path.read_text()
            self.assertIn(f"Part: {index} of 3", text)
            self.assertIn(f"watch?v={VIDEO_ID}", text)
            body = text.split("--- Transcript ---\n\n", 1)[1]
            self.assertLessEqual(len(body.split()), 3)
            body_words.extend(body.split())
        self.assertEqual(body_words, " ".join(c.text for c in self.fetched).split())

    def test_repeated_download_skips_network_and_refresh_fetches(self):
        self.assertEqual(main([VIDEO_ID]), 0)
        original = self.text_files()[0].read_text()
        self.api.reset_mock()
        self.metadata.reset_mock()
        self.assertEqual(main([VIDEO_ID]), 0)
        self.api.assert_not_called()
        self.metadata.assert_not_called()
        self.assertIn("Already saved:", self.stdout.getvalue())
        self.assertEqual(self.text_files()[0].read_text(), original)
        self.assertEqual(main([VIDEO_ID, "--refresh"]), 0)
        self.api.return_value.fetch.assert_called_once()

    def test_edited_files_require_refresh(self):
        self.assertEqual(main([VIDEO_ID]), 0)
        path = self.text_files()[0]
        path.write_text("My notes")
        self.api.reset_mock()
        self.assertEqual(main([VIDEO_ID]), 1)
        self.assertEqual(path.read_text(), "My notes")
        self.api.assert_not_called()
        self.assertEqual(main([VIDEO_ID, "--refresh"]), 0)
        self.assertNotEqual(path.read_text(), "My notes")

    def test_missing_file_is_downloaded_again(self):
        self.assertEqual(main([VIDEO_ID]), 0)
        self.text_files()[0].unlink()
        self.api.reset_mock()
        self.assertEqual(main([VIDEO_ID]), 0)
        self.api.return_value.fetch.assert_called_once()

    def test_identical_titles_and_different_options_have_separate_files(self):
        self.assertEqual(main([VIDEO_ID, OTHER_ID]), 0)
        self.assertEqual(main([VIDEO_ID, "--raw"]), 0)
        self.assertEqual(main([VIDEO_ID, "--languages", "es", "en"]), 0)
        self.assertEqual(len(self.text_files()), 4)

    def test_batch_deduplicates_and_combines(self):
        batch = self.home / "links.txt"
        batch.write_text(f"# Watch later\n\n{VIDEO_ID}\nhttps://youtu.be/{OTHER_ID}\n{VIDEO_ID}\n")
        self.assertEqual(main(["--batch", str(batch), "--combine", "comparison.txt"]), 0)
        self.assertEqual(self.api.return_value.fetch.call_count, 2)
        text = (self.output / "comparison.txt").read_text()
        self.assertEqual(text.count("--- Transcript ---"), 2)
        self.assertIn(f"watch?v={VIDEO_ID}", text)
        self.assertIn(f"watch?v={OTHER_ID}", text)

    def test_failed_batch_item_does_not_stop_other_downloads(self):
        self.api.return_value.fetch.side_effect = [TranscriptsDisabled(VIDEO_ID), self.fetched]
        self.assertEqual(main([VIDEO_ID, "bad-url", OTHER_ID, "--combine", "good.txt"]), 1)
        self.assertTrue((self.output / "good.txt").exists())
        self.assertIn("bad-url", self.stderr.getvalue())

    def test_combined_document_cannot_replace_individual_transcript(self):
        self.assertEqual(main([VIDEO_ID]), 0)
        path = self.text_files()[0]
        before = path.read_bytes()
        self.assertEqual(main([VIDEO_ID, "--combine", str(path)]), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_prompt_templates_are_editable_and_affect_history(self):
        self.assertEqual(main(["--init"]), 0)
        template = self.home / "app/templates/discussion.txt"
        template.write_text("Discuss the evidence.")
        self.assertEqual(main([VIDEO_ID, "--prompt", "discussion"]), 0)
        self.assertIn("Discussion request:\nDiscuss the evidence.", self.text_files()[0].read_text())
        template.write_text("Explore the assumptions.")
        self.assertEqual(main([VIDEO_ID, "--prompt", "discussion"]), 0)
        self.assertEqual(len(self.text_files()), 2)

    def test_custom_prompt_and_packaged_template(self):
        custom = self.home / "request.txt"
        custom.write_text("Find contradictions.")
        self.assertEqual(main([VIDEO_ID, "--prompt-file", str(custom)]), 0)
        self.assertEqual(main([OTHER_ID, "--prompt", "compare"]), 0)
        texts = "\n".join(p.read_text() for p in self.text_files())
        self.assertIn("Find contradictions.", texts)
        self.assertIn("Compare the supplied video transcripts.", texts)

    def test_shared_text_extracts_url_without_treating_title_as_arguments(self):
        self.assertEqual(main(["--shared-text", f'A title --refresh\nhttps://youtu.be/{VIDEO_ID}?si=x']), 0)
        self.api.return_value.fetch.assert_called_once_with(VIDEO_ID, languages=["en"])

    def test_history_does_not_use_network(self):
        self.assertEqual(main([VIDEO_ID]), 0)
        self.api.reset_mock()
        self.assertEqual(main(["--history"]), 0)
        self.assertIn(VIDEO_ID, self.stdout.getvalue())
        self.api.assert_not_called()

    def test_init_creates_folders_and_preserves_edited_templates(self):
        self.assertEqual(main(["--init"]), 0)
        self.assertTrue((self.output / ".ytxt/history").is_dir())
        template = self.home / "app/templates/discussion.txt"
        template.write_text("My custom request")
        self.assertEqual(main(["--init"]), 0)
        self.assertEqual(template.read_text(), "My custom request")
        self.api.assert_not_called()

    def test_network_failure_is_readable_without_creating_output(self):
        self.api.return_value.fetch.side_effect = ConnectionError("offline")
        self.assertEqual(main([VIDEO_ID]), 1)
        self.assertIn("offline", self.stderr.getvalue())
        self.assertFalse(self.output.exists())

    def test_caption_failure_keeps_existing_download(self):
        self.assertEqual(main([VIDEO_ID]), 0)
        path = self.text_files()[0]
        before = path.read_bytes()
        self.api.return_value.fetch.side_effect = TranscriptsDisabled(VIDEO_ID)
        self.assertEqual(main([VIDEO_ID, "--refresh"]), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_filesystem_error(self):
        target = self.home / "a-file"
        target.write_text("not a directory")
        self.assertEqual(main([VIDEO_ID, "-d", str(target)]), 1)
        self.assertIn("ytxt:", self.stderr.getvalue())

    def test_invalid_options_do_not_use_network(self):
        for args in ([], [VIDEO_ID, "--start", "5", "--end", "3"],
                     [VIDEO_ID, "--split-words", "0"], [VIDEO_ID, "--combine", "bad.json"]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 2)
        self.api.assert_not_called()

    def test_invalid_url_does_not_use_network(self):
        self.assertEqual(main(["https://youtu.be/bad"]), 1)
        self.api.assert_not_called()

    def test_version_does_not_use_network(self):
        with self.assertRaises(SystemExit) as error:
            main(["--version"])
        self.assertEqual(error.exception.code, 0)
        self.assertIn(__version__, self.stdout.getvalue())
        self.api.assert_not_called()

    def test_chatgpt_handoff_uses_saved_transcripts_and_editable_prompt(self):
        self.assertEqual(main([VIDEO_ID]), 0)
        self.api.reset_mock()
        with patch("ytxt.cli.launch_draft") as launch:
            self.assertEqual(main([VIDEO_ID, "--chatgpt"]), 0)
        self.api.assert_not_called()
        draft = launch.call_args.args[0]
        self.assertEqual(draft.files, tuple(self.text_files()))
        self.assertIn("Discuss the transcript", draft.prompt)
        self.assertTrue(list((self.home / "app/drafts").glob("*/prompt.txt")))

    def test_chatgpt_opens_existing_files_without_downloading(self):
        transcript = self.home / "existing.txt"
        transcript.write_text("My saved transcript")
        prompt = self.home / "question.txt"
        prompt.write_text("I want to discuss the assumptions.")
        with patch("ytxt.cli.launch_draft") as launch:
            self.assertEqual(main(["--chatgpt", "--chatgpt-file", str(transcript),
                                   "--prompt-file", str(prompt)]), 0)
        self.api.assert_not_called()
        self.assertEqual(launch.call_args.args[0].files, (transcript,))
        self.assertIn("I want to discuss the assumptions.", launch.call_args.args[0].prompt)

    def test_chatgpt_combined_document_avoids_duplicate_context(self):
        with patch("ytxt.cli.launch_draft") as launch:
            self.assertEqual(main([VIDEO_ID, OTHER_ID, "--combine", "both.txt", "--chatgpt"]), 0)
        self.assertEqual(launch.call_args.args[0].files, (self.output / "both.txt",))

    def test_missing_app_keeps_downloads_and_saved_draft(self):
        with patch("ytxt.cli.launch_draft", side_effect=OSError("No desktop app")):
            self.assertEqual(main([VIDEO_ID, "--chatgpt"]), 1)
        self.assertTrue(self.text_files())
        self.assertTrue(list((self.home / "app/drafts").glob("*/prompt.txt")))
        self.assertIn("No desktop app", self.stderr.getvalue())
        self.assertNotIn("Desktop draft requested", self.stdout.getvalue())

    def test_chatgpt_does_not_open_on_all_failed_downloads(self):
        self.api.return_value.fetch.side_effect = TranscriptsDisabled(VIDEO_ID)
        with patch("ytxt.cli.launch_draft") as launch:
            self.assertEqual(main([VIDEO_ID, "--chatgpt"]), 1)
        launch.assert_not_called()

    def test_chatgpt_cannot_be_combined_with_setup_or_history(self):
        for args in (["--init", "--chatgpt"], ["--history", "--chatgpt"],
                     ["--chatgpt-file", "something.txt"]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 2)
        self.api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
