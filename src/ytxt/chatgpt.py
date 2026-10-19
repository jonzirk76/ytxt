"""Prepare editable ChatGPT drafts without submitting a message."""

import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from .storage import app_home, atomic_write, is_termux, write_json


@dataclass(frozen=True)
class Draft:
    prompt: str
    files: tuple[Path, ...]
    workspace: Path
    target: str = "app"

    @property
    def url(self) -> str:
        if self.target == "browser":
            return "https://chatgpt.com/"
        # Documented desktop links set composer text and a local workspace.
        # File references here are local context, not uploaded attachments.
        return "codex://new?" + urlencode({"prompt": self.prompt, "path": str(self.workspace)})


def prepare_draft(paths: list[Path], prompt: str, target: str = "app") -> Draft:
    if target not in ("app", "browser"):
        raise ValueError("Unknown ChatGPT target")
    selected = tuple(dict.fromkeys(path.expanduser().resolve(strict=True) for path in paths))
    if not selected:
        raise ValueError("No transcript files available for the ChatGPT draft")
    for path in selected:
        if not path.is_file() or path.suffix.lower() != ".txt":
            raise ValueError(f"ChatGPT transcript context must be a .txt file: {path}")
    workspace = Path(os.path.commonpath([str(path.parent) for path in selected]))
    if target == "browser":
        text = prompt.strip() + "\n\nUse the attached YouTube transcript files as source material."
    else:
        references = "\n".join(f"- {path}" for path in selected)
        text = prompt.strip() + "\n\nLocal transcript files to read as source material:\n" + references
    draft = Draft(text, selected, workspace, target)
    if target == "app" and len(draft.url.encode("utf-8")) > 30000:
        raise ValueError("The desktop draft link is too long; use a shorter prompt or fewer files")
    return draft


def save_draft(draft: Draft) -> Path:
    folder = app_home() / "drafts" / uuid.uuid4().hex
    atomic_write(folder / "prompt.txt", draft.prompt + "\n")
    write_json(folder / "draft.json", {
        "prompt": draft.prompt, "files": [str(path) for path in draft.files],
        "workspace": str(draft.workspace), "url": draft.url,
        "target": draft.target,
    })
    return folder


def launch_draft(draft: Draft) -> None:
    if is_termux():
        raise ValueError("Desktop-app drafts require a desktop; run this command on the computer with ChatGPT installed")
    try:
        if sys.platform == "win32":
            os.startfile(draft.url)
            return
        if sys.platform == "darwin":
            command = ["open", draft.url]
        else:
            opener = shutil.which("xdg-open")
            if not opener:
                raise OSError("xdg-open is required to launch the ChatGPT desktop app")
            query = shutil.which("xdg-mime")
            if not query:
                raise OSError("xdg-mime is required to check the desktop app's URL registration")
            handler = subprocess.run(
                [query, "query", "default", "x-scheme-handler/codex"],
                capture_output=True, text=True, timeout=10,
            )
            if handler.returncode != 0 or not handler.stdout.strip():
                raise OSError("No desktop app is registered for codex:// links; install or register the ChatGPT desktop app")
            command = [opener, draft.url]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=15)
    except subprocess.CalledProcessError as error:
        raise OSError("The ChatGPT desktop app could not be opened") from error
    except subprocess.TimeoutExpired as error:
        raise OSError("Opening the ChatGPT desktop app timed out") from error
