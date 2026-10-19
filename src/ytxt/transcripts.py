"""Transcript formatting, provenance, and download history."""

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .storage import atomic_write, write_json


DEFAULT_OPTIONS = {
    "languages": ["en"], "raw": False, "timestamps": False,
    "start": 0.0, "end": None, "split_words": None, "prompt": "",
}


@dataclass(frozen=True)
class Caption:
    text: str
    start: float
    duration: float


@dataclass
class Result:
    files: list[Path]
    title: str
    skipped: bool = False


def get_metadata(video_id: str) -> dict:
    url = (
        "https://www.youtube.com/oembed"
        f"?url=https://www.youtube.com/watch?v={video_id}&format=json"
    )
    fallback = {"title": video_id, "channel": "Unknown"}
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.load(response)
        for key, source in (("title", "title"), ("channel", "author_name")):
            value = data.get(source)
            if isinstance(value, str) and value.strip():
                fallback[key] = " ".join(value.split())
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return fallback


def safe_filename(title: str, video_id: str, suffix: str = "") -> str:
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    title = title.encode("utf-8")[:140].decode("utf-8", errors="ignore").rstrip(" .")
    stem = f"{title} [{video_id}]" if title and title != video_id else video_id
    return f"{stem}{suffix}.txt"


def timestamp(seconds: float) -> str:
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def split_captions(captions: list[Caption], limit: int | None) -> list[list[Caption]]:
    if limit is None:
        return [captions]
    chunks, current, count = [], [], 0
    for caption in captions:
        words = caption.text.split()
        while words:
            take = min(limit - count, len(words))
            current.append(replace(caption, text=" ".join(words[:take])))
            words = words[take:]
            count += take
            if count == limit:
                chunks.append(current)
                current, count = [], 0
    if current:
        chunks.append(current)
    return chunks


def render_body(captions: list[Caption], raw: bool, timestamps: bool) -> str:
    groups, group, count = [], [], 0
    for caption in captions:
        if group and (raw or count >= 80 or caption.start - group[0].start >= 30
                      or caption.start - (group[-1].start + group[-1].duration) > 2):
            groups.append(group)
            group, count = [], 0
        group.append(caption)
        count += len(caption.text.split())
    if group:
        groups.append(group)
    paragraphs = []
    for group in groups:
        text = group[0].text if raw else " ".join(" ".join(c.text.split()) for c in group)
        prefix = f"[{timestamp(group[0].start)}] " if timestamps else ""
        paragraphs.append(prefix + text)
    return ("\n" if raw else "\n\n").join(paragraphs)


def render_document(metadata: dict, captions: list[Caption], options: dict,
                    part: int = 1, total: int = 1) -> str:
    start = min(c.start for c in captions)
    end = max(c.start + c.duration for c in captions)
    lines = [
        f"Title: {metadata['title']}", f"Channel: {metadata['channel']}",
        f"URL: {metadata['url']}",
        f"Caption language: {metadata['language']} ({metadata['language_code']})",
        "Caption type: " + ("automatically generated" if metadata['is_generated'] else "manually created"),
        f"Downloaded: {metadata['downloaded_at']}",
        f"Caption time range: {timestamp(start)}–{timestamp(end)}",
        f"Start link: {metadata['url']}&t={int(start)}s",
    ]
    if options["start"] or options["end"] is not None:
        requested_end = timestamp(options["end"]) if options["end"] is not None else "end"
        lines.append(f"Requested section: {timestamp(options['start'])}–{requested_end}")
    if total > 1:
        lines.append(f"Part: {part} of {total}")
    if options["prompt"]:
        lines.extend(["", "Discussion request:", options["prompt"]])
    lines.extend(["", "--- Transcript ---", "",
                  render_body(captions, options["raw"], options["timestamps"])])
    return "\n".join(lines) + "\n"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_key(video_id: str, options: dict) -> str:
    return digest(json.dumps([video_id, options], sort_keys=True).encode())


def load_record(path: Path) -> dict | None:
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        if (entry.get("schema") != 1 or not isinstance(entry.get("files"), dict)
                or not entry["files"] or not isinstance(entry.get("text_files"), list)
                or not entry["text_files"]
                or not all(isinstance(entry.get(key), str)
                           for key in ("title", "video_id", "downloaded_at"))):
            return None
        if not all(isinstance(name, str) and Path(name).name == name
                   and isinstance(checksum, str) for name, checksum in entry["files"].items()):
            return None
        if not all(isinstance(name, str) and name in entry["files"] for name in entry["text_files"]):
            return None
        return entry
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def download(video_id: str, output_dir: Path, options: dict, refresh: bool, fetcher) -> Result:
    key = request_key(video_id, options)
    record_path = output_dir / ".ytxt/history" / f"{key}.json"
    entry = load_record(record_path)
    if entry and not refresh:
        changed = [name for name, checksum in entry["files"].items()
                   if (output_dir / name).is_file()
                   and digest((output_dir / name).read_bytes()) != checksum]
        if changed:
            raise ValueError("Saved files were edited; use --refresh to replace them: " + ", ".join(changed))
        if all((output_dir / name).is_file() for name in entry["files"]):
            return Result([output_dir / name for name in entry["text_files"]], entry["title"], True)

    fetched = fetcher(video_id, options["languages"])
    all_captions = [Caption(item.text, item.start, item.duration) for item in fetched]
    captions = [c for c in all_captions if c.text.strip()
                and (c.start + c.duration > options["start"]
                     or (c.duration == 0 and c.start >= options["start"]))
                and (options["end"] is None or c.start < options["end"])]
    if not captions:
        raise ValueError("No captions overlap the requested section")
    metadata = get_metadata(video_id)
    metadata.update({
        "video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}",
        "language": fetched.language, "language_code": fetched.language_code,
        "is_generated": fetched.is_generated,
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    variant = "" if options == DEFAULT_OPTIONS else f".{key[:10]}"
    base = output_dir / safe_filename(metadata["title"], video_id, variant)
    chunks = split_captions(captions, options["split_words"])
    documents = {}
    for index, chunk in enumerate(chunks, 1):
        path = base if len(chunks) == 1 else base.with_name(
            f"{base.stem}.part-{index:03}-of-{len(chunks):03}.txt"
        )
        documents[path] = render_document(metadata, chunk, options, index, len(chunks))
    raw_path = base.with_suffix(".json")
    raw_text = json.dumps({"metadata": metadata, "options": options,
                           "captions": [vars(c) for c in all_captions]},
                          ensure_ascii=False, indent=2) + "\n"
    artifacts = {**documents, raw_path: raw_text}
    # With no known history, do not overwrite an unrelated existing file.
    known = set(entry["files"]) if entry else set()
    for path in artifacts:
        if path.exists() and path.name not in known and not refresh:
            raise ValueError(f"File already exists; use --refresh to replace it: {path}")
    for path, text in artifacts.items():
        atomic_write(path, text)
    write_json(record_path, {
        "schema": 1, **metadata, "options": options,
        "text_files": [path.name for path in documents],
        "files": {path.name: digest(text.encode("utf-8")) for path, text in artifacts.items()},
    })
    return Result(list(documents), metadata["title"])


def history(output_dir: Path) -> list[dict]:
    records = [load_record(path) for path in (output_dir / ".ytxt/history").glob("*.json")]
    return sorted((entry for entry in records if entry),
                  key=lambda entry: entry.get("downloaded_at", ""), reverse=True)
