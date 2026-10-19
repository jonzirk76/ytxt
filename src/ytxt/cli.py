"""Command-line interface, based on the original desktop ytxt script."""

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from requests.exceptions import RequestException
from youtube_transcript_api import YouTubeTranscriptApi, YouTubeTranscriptApiException

from . import __version__


def get_video_id(url: str) -> str:
    """Accept a video ID or a supported YouTube URL; validate the extracted ID."""
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


def get_title(video_id: str) -> str:
    url = (
        "https://www.youtube.com/oembed"
        f"?url=https://www.youtube.com/watch?v={video_id}&format=json"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            title = json.load(response)["title"]
        return title if isinstance(title, str) and title.strip() else video_id
    except (OSError, ValueError, KeyError, TypeError):
        # Caption retrieval can still succeed if the optional title lookup fails.
        return video_id


def safe_filename(title: str, video_id: str) -> str:
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    # Leave room for the extension, including on filesystems with byte limits.
    title = title.encode("utf-8")[:200].decode("utf-8", errors="ignore").rstrip(" .")
    return (title or video_id) + ".txt"


def default_output_dir() -> Path:
    configured = os.environ.get("YTXT_OUTPUT_DIR")
    if configured:
        return Path(configured)
    home = Path.home()
    if os.environ.get("TERMUX_VERSION") or "com.termux" in os.environ.get("PREFIX", ""):
        downloads = home / "storage" / "downloads"
        if not downloads.is_dir():
            raise OSError(
                "Android shared Downloads is unavailable. Run termux-setup-storage "
                "and allow storage access, or choose --output-dir."
            )
        return downloads
    return home / "Downloads"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Save a YouTube video's captions as a plain text file."
    )
    parser.add_argument("url", help="YouTube video URL or video ID")
    parser.add_argument(
        "-d", "--output-dir", type=Path,
        help="destination folder (default: YTXT_OUTPUT_DIR or device Downloads folder)",
    )
    parser.add_argument(
        "-l", "--languages", nargs="+", default=["en"], metavar="CODE",
        help="caption languages, in preference order (default: en)",
    )
    parser.add_argument("--version", action="version", version=f"ytxt {__version__}")
    args = parser.parse_args(argv)

    try:
        video_id = get_video_id(args.url)
    except ValueError as error:
        parser.error(str(error))

    try:
        output_dir = args.output_dir or default_output_dir()
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=args.languages)
        title = get_title(video_id)
        output_dir = output_dir.expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / safe_filename(title, video_id)
        with output.open("w", encoding="utf-8") as file:
            for item in transcript:
                file.write(item.text + "\n")
    except (YouTubeTranscriptApiException, RequestException, OSError) as error:
        print(f"ytxt: {error}", file=sys.stderr)
        return 1

    print(f"Saved: {output}")
    return 0
