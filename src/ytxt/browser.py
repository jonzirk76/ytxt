"""Short-lived, authenticated loopback bridge for the ChatGPT userscript."""

import base64
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlencode

from .chatgpt import Draft
from .storage import app_home, atomic_write, is_termux

MAX_FILE_BYTES = 16 * 1024 * 1024


def install_browser_helper() -> Path:
    target = app_home() / "browser/ytxt-chatgpt.user.js"
    atomic_write(target, files("ytxt").joinpath("browser/ytxt-chatgpt.user.js").read_text(encoding="utf-8"))
    return target


def browser_payload(draft: Draft) -> dict:
    attachments, size = [], 0
    for path in draft.files:
        with path.open("rb") as handle:
            data = handle.read(MAX_FILE_BYTES - size + 1)
        size += len(data)
        if size > MAX_FILE_BYTES:
            raise ValueError("Browser handoff is limited to 16 MiB of transcript files; select fewer files")
        attachments.append({"name": path.name, "data": base64.b64encode(data).decode("ascii")})
    return {"prompt": draft.prompt, "files": attachments}


class DraftServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, payload: dict):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.token = secrets.token_urlsafe(32)
        self.connected = threading.Event()
        self.finished = threading.Event()
        self.result = None
        super().__init__(("127.0.0.1", 0), DraftHandler)

    @property
    def url(self) -> str:
        # Only the random connection parameters travel in the fragment.
        # Prompt text, absolute paths, and file contents stay out of the URL.
        return "https://chatgpt.com/#ytxt=" + urlencode({
            "port": self.server_port, "token": self.token,
        })


class DraftHandler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def authorized(self) -> bool:
        expected = f"Bearer {self.server.token}"
        actual = self.headers.get("Authorization", "")
        valid = (self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
                 and secrets.compare_digest(actual.encode(), expected.encode()))
        if not valid:
            self.send_error(403)
        return valid

    def respond(self, content: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        if not self.authorized():
            return
        if self.path != "/draft":
            self.send_error(404)
            return
        if self.server.finished.is_set():
            self.send_error(410)
            return
        self.server.connected.set()
        self.respond(self.server.payload)

    def do_POST(self) -> None:
        if not self.authorized():
            return
        if self.path != "/status":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid status size")
            message = json.loads(self.rfile.read(length))
            if message.get("state") not in ("prepared", "error"):
                raise ValueError("Invalid status")
            detail = message.get("message", "")
            if not isinstance(detail, str) or len(detail) > 1000:
                raise ValueError("Invalid status message")
        except (ValueError, AttributeError):
            self.send_error(400)
            return
        self.server.result = message
        self.respond(b"{}")
        self.server.finished.set()


def open_browser_draft(draft: Draft, connect_timeout: float = 30,
                       prepare_timeout: float = 180) -> None:
    if is_termux():
        raise ValueError("Browser handoff currently requires a desktop browser")
    helper = install_browser_helper()
    server = DraftServer(browser_payload(draft))
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    worker.start()
    try:
        print("Opening ChatGPT in your default browser; waiting for the ytxt browser helper...")
        if not webbrowser.open(server.url, new=2, autoraise=True):
            raise OSError("No desktop browser could be opened")
        if not server.connected.wait(connect_timeout):
            raise OSError(
                "The browser helper did not connect. Sign in at chatgpt.com and enable "
                f"the ytxt userscript in Tampermonkey, then retry. Helper: {helper}. "
                "Use --no-chatgpt for download-only operation."
            )
        if not server.finished.wait(prepare_timeout):
            raise OSError("The browser draft timed out. Check the ytxt notice in the ChatGPT tab, then retry")
        if server.result["state"] != "prepared":
            raise OSError("Browser draft needs attention: " + server.result.get("message", "Unknown browser error"))
        print("Browser draft prefilled and files passed to the upload control. Check attachments before sending.")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
