"""Device paths, editable templates, and atomic local writes."""

import json
import os
import shlex
import shutil
import sys
import tempfile
import uuid
from importlib.resources import files
from pathlib import Path


def is_termux() -> bool:
    return bool(os.environ.get("TERMUX_VERSION")) or "com.termux" in os.environ.get("PREFIX", "")


def app_home() -> Path:
    return Path(os.environ.get("YTXT_HOME") or Path.home() / ".local/share/ytxt").expanduser()


def default_output_dir() -> Path:
    configured = os.environ.get("YTXT_OUTPUT_DIR")
    if configured:
        return Path(configured).expanduser()
    home = Path.home()
    if is_termux():
        downloads = home / "storage/downloads"
        if not downloads.is_dir():
            raise OSError(
                "Android shared Downloads is unavailable. Run termux-setup-storage "
                "and allow storage access, or choose --output-dir."
            )
        return downloads / "ytxt"
    return home / "Downloads/ytxt"


def atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def template_text(name: str) -> str:
    path = app_home() / "templates" / f"{name}.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return files("ytxt").joinpath("templates", f"{name}.txt").read_text(encoding="utf-8").strip()


def initialize(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".ytxt/history").mkdir(parents=True, exist_ok=True)
    templates = app_home() / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    for name in ("discussion", "compare"):
        target = templates / f"{name}.txt"
        if not target.exists():
            text = files("ytxt").joinpath("templates", f"{name}.txt").read_text(encoding="utf-8")
            atomic_write(target, text)


def install_share_hook() -> Path:
    if not is_termux():
        raise ValueError("The Android Share hook is only available inside Termux")
    shell = Path(os.environ["PREFIX"]) / "bin/sh"
    target = Path.home() / "bin/termux-url-opener"
    target.parent.mkdir(parents=True, exist_ok=True)
    marker = "# ytxt share hook"
    if target.exists() and marker.encode() not in target.read_bytes():
        backup = target.with_name(f"{target.name}.backup.{uuid.uuid4().hex[:12]}")
        shutil.copy2(target, backup)
        print(f"Previous Share hook backed up to: {backup}")
    script = (
        f"#!{shell}\n{marker}\n"
        'if [ "$#" -eq 0 ]; then exit 2; fi\n'
        f"exec {shlex.quote(sys.executable)} -m ytxt --shared-text \"$1\"\n"
    )
    atomic_write(target, script, mode=0o700)
    return target
