"""Command-line interface for preparing transcripts for discussion."""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from requests.exceptions import RequestException
from youtube_transcript_api import YouTubeTranscriptApi, YouTubeTranscriptApiException

from . import __version__
from .storage import atomic_write, default_output_dir, initialize, install_share_hook, template_text
from .transcripts import download, history


def get_video_id(url: str) -> str:
    url = url.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    video_id = ""
    if parsed.scheme in ("https", "http"):
        if host in ("youtu.be", "www.youtu.be"):
            video_id = parsed.path.strip("/").split("/")[0]
        elif host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            else:
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] in ("live", "shorts", "embed"):
                    video_id = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Expected a YouTube video URL or an 11-character video ID")
    return video_id


def parse_time(value: str) -> float:
    if not re.fullmatch(r"\d+(?::[0-5]?\d){0,2}(?:\.\d+)?", value):
        raise argparse.ArgumentTypeError("Use seconds, MM:SS, or HH:MM:SS")
    seconds = 0.0
    for component in value.split(":"):
        seconds = seconds * 60 + float(component)
    if seconds == float("inf"):
        raise argparse.ArgumentTypeError("Time must be finite")
    return seconds


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a positive integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ytxt", description="Prepare YouTube captions for discussion.")
    parser.add_argument("urls", nargs="*", help="YouTube URLs or video IDs")
    parser.add_argument("-d", "--output-dir", type=Path,
                        help="destination (default: device Downloads/ytxt or YTXT_OUTPUT_DIR)")
    parser.add_argument("-l", "--languages", nargs="+", default=["en"], metavar="CODE",
                        help="caption languages, in preference order (default: en)")
    parser.add_argument("--raw", action="store_true", help="one caption per line instead of paragraphs")
    parser.add_argument("--timestamps", action="store_true", help="timestamp each paragraph or caption")
    parser.add_argument("--start", type=parse_time, default=0.0, help="section start: seconds or HH:MM:SS")
    parser.add_argument("--end", type=parse_time, help="section end, exclusive: seconds or HH:MM:SS")
    parser.add_argument("--split-words", type=positive_int, metavar="N",
                        help="split into numbered parts with at most N transcript words")
    parser.add_argument("--batch", type=Path, metavar="FILE", help="read one URL or ID per line")
    parser.add_argument("--combine", type=Path, metavar="FILE.txt", help="combine successful transcripts")
    parser.add_argument("--refresh", action="store_true", help="redownload and replace saved files")
    prompt = parser.add_mutually_exclusive_group()
    prompt.add_argument("--prompt", choices=("discussion", "compare"), help="include an editable prompt")
    prompt.add_argument("--prompt-file", type=Path, help="include your own discussion request")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--init", action="store_true", help="create ytxt's folder and prompt templates")
    actions.add_argument("--history", action="store_true", help="list downloads in the output folder")
    actions.add_argument("--install-share-hook", action="store_true", help="set up Android Share to Termux")
    parser.add_argument("--shared-text", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"ytxt {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.end is not None and args.end <= args.start:
        parser.error("--end must be later than --start")
    if args.combine and args.combine.suffix.lower() != ".txt":
        parser.error("--combine must name a .txt file")
    action = args.init or args.history or args.install_share_hook
    if action and (args.urls or args.batch or args.shared_text):
        parser.error("Use setup/history actions separately from video downloads")
    if not action and not (args.urls or args.batch or args.shared_text):
        parser.error("Provide a video URL, video ID, or --batch file")
    try:
        if args.install_share_hook:
            print(f"Share hook installed: {install_share_hook()}")
            return 0
        output_dir = (args.output_dir or default_output_dir()).expanduser().resolve()
        if args.init:
            initialize(output_dir)
            print(f"ytxt folder ready: {output_dir}")
            return 0
        if args.history:
            entries = history(output_dir)
            for entry in entries:
                print(f"{entry['downloaded_at']}  {entry['video_id']}  {entry['title']}")
                for filename in entry["text_files"]:
                    print(f"  {output_dir / filename}")
            if not entries:
                print("No downloads recorded in this folder.")
            return 0
        urls = list(args.urls)
        if args.batch:
            urls.extend(line.strip() for line in args.batch.expanduser().read_text(encoding="utf-8-sig").splitlines()
                        if line.strip() and not line.lstrip().startswith("#"))
        if args.shared_text:
            shared_urls = re.findall(r"https?://[^\s<>\"']+", args.shared_text)
            urls.extend(url.rstrip(".,);]>") for url in shared_urls)
        if not urls:
            raise ValueError("No video URLs found")
        prompt = template_text(args.prompt) if args.prompt else ""
        if args.prompt_file:
            prompt = args.prompt_file.expanduser().read_text(encoding="utf-8").strip()
        options = {"languages": args.languages, "raw": args.raw, "timestamps": args.timestamps,
                   "start": args.start, "end": args.end, "split_words": args.split_words, "prompt": prompt}
        combined, seen, failures = [], set(), 0
        fetcher = lambda video_id, languages: YouTubeTranscriptApi().fetch(video_id, languages=languages)
        for url in urls:
            try:
                video_id = get_video_id(url)
                if video_id in seen:
                    continue
                seen.add(video_id)
                result = download(video_id, output_dir, options, args.refresh, fetcher)
                for path in result.files:
                    print(f"{'Already saved' if result.skipped else 'Saved'}: {path}")
                combined.extend(result.files)
            except (ValueError, YouTubeTranscriptApiException, RequestException, OSError) as error:
                print(f"ytxt: {url}: {error}", file=sys.stderr)
                failures += 1
        if args.combine and combined:
            target = args.combine.expanduser()
            if not target.is_absolute():
                target = output_dir / target
            target = target.resolve()
            saved = {output_dir / name for entry in history(output_dir) for name in entry["files"]}
            if target in saved or target in combined or ".ytxt" in target.parts:
                raise ValueError("The combined document must have its own filename outside .ytxt")
            content = "\n\n".join(path.read_text(encoding="utf-8").rstrip() for path in combined)
            atomic_write(target, content + "\n")
            print(f"Combined: {target}")
        return 1 if failures else 0
    except (ValueError, YouTubeTranscriptApiException, RequestException, OSError) as error:
        print(f"ytxt: {error}", file=sys.stderr)
        return 1
