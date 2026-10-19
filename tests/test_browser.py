import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from ytxt.browser import DraftServer, MAX_FILE_BYTES, browser_payload, install_browser_helper, open_browser_draft
from ytxt.chatgpt import prepare_draft


class BrowserPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "Caption café.txt"
        self.path.write_text("Original café transcript", encoding="utf-8")
        self.draft = prepare_draft([self.path], "Discuss this.", target="browser")

    def test_browser_context_is_attached_content_without_local_path_in_prompt(self):
        payload = browser_payload(self.draft)
        self.assertNotIn(str(self.root), payload["prompt"])
        self.assertIn("attached", payload["prompt"])
        self.assertEqual(payload["files"][0]["name"], self.path.name)
        self.assertEqual(base64.b64decode(payload["files"][0]["data"]), self.path.read_bytes())
        self.assertEqual(self.draft.url, "https://chatgpt.com/")

    def test_browser_does_not_inherit_desktop_url_length_limit(self):
        draft = prepare_draft([self.path], "a" * 40000, target="browser")
        self.assertEqual(len(browser_payload(draft)["prompt"].split("\n")[0]), 40000)

    def test_payload_limit(self):
        with self.path.open("wb") as handle:
            handle.seek(MAX_FILE_BYTES)
            handle.write(b"x")
        with self.assertRaisesRegex(ValueError, "16 MiB"):
            browser_payload(self.draft)

    def test_packaged_helper_is_installed(self):
        with patch.dict(os.environ, {"YTXT_HOME": str(self.root / "app")}):
            helper = install_browser_helper()
        text = helper.read_text()
        self.assertIn("@match        https://chatgpt.com/*", text)
        self.assertIn("@connect      127.0.0.1", text)
        self.assertIn("GM_xmlhttpRequest", text)

    def test_launcher_reports_missing_helper_and_closes_server(self):
        server = MagicMock()
        server.connected.wait.return_value = False
        with patch("ytxt.browser.is_termux", return_value=False), \
             patch("ytxt.browser.install_browser_helper", return_value=self.root / "helper.js"), \
             patch("ytxt.browser.DraftServer", return_value=server), \
             patch("ytxt.browser.threading.Thread"), \
             patch("ytxt.browser.webbrowser.open", return_value=True):
            with self.assertRaisesRegex(OSError, "helper did not connect"):
                open_browser_draft(self.draft, connect_timeout=0)
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()

    def test_launcher_accepts_prepared_status_without_submitting(self):
        server = MagicMock()
        server.connected.wait.return_value = True
        server.finished.wait.return_value = True
        server.result = {"state": "prepared"}
        server.url = "https://chatgpt.com/#ytxt=port=12345&token=example"
        with patch("ytxt.browser.is_termux", return_value=False), \
             patch("ytxt.browser.install_browser_helper"), \
             patch("ytxt.browser.DraftServer", return_value=server), \
             patch("ytxt.browser.threading.Thread"), \
             patch("ytxt.browser.webbrowser.open", return_value=True) as browser:
            open_browser_draft(self.draft)
        browser.assert_called_once_with(server.url, new=2, autoraise=True)
        server.server_close.assert_called_once()

    def test_browser_error_is_not_reported_as_success(self):
        server = MagicMock()
        server.connected.wait.return_value = True
        server.finished.wait.return_value = True
        server.result = {"state": "error", "message": "Existing draft"}
        with patch("ytxt.browser.is_termux", return_value=False), \
             patch("ytxt.browser.install_browser_helper"), \
             patch("ytxt.browser.DraftServer", return_value=server), \
             patch("ytxt.browser.threading.Thread"), \
             patch("ytxt.browser.webbrowser.open", return_value=True):
            with self.assertRaisesRegex(OSError, "Existing draft"):
                open_browser_draft(self.draft)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.server = DraftServer({"prompt": "A private question", "files": []})
        self.worker = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.worker.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)

    def request(self, method, path, body=None, authenticated=True, host=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Authorization": "Bearer " + self.server.token} if authenticated else {}
        if host:
            headers["Host"] = host
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_bound_to_loopback_and_fragment_contains_no_private_data(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        url = urlparse(self.server.url)
        self.assertEqual(url.query, "")
        self.assertNotIn("private", self.server.url)
        params = parse_qs(url.fragment.removeprefix("ytxt="))
        self.assertEqual(set(params), {"port", "token"})

    def test_unauthenticated_requests_do_not_disclose_payload(self):
        status, body, _ = self.request("GET", "/draft", authenticated=False)
        self.assertEqual(status, 403)
        self.assertNotIn(b"private", body)
        self.assertFalse(self.server.connected.is_set())

    def test_wrong_host_is_rejected_even_with_valid_token(self):
        status, _, _ = self.request("GET", "/draft", host="evil.example")
        self.assertEqual(status, 403)

    def test_authenticated_draft_and_completion(self):
        status, body, headers = self.request("GET", "/draft")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["prompt"], "A private question")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertTrue(self.server.connected.is_set())
        status, _, _ = self.request("POST", "/status", json.dumps({"state": "prepared"}))
        self.assertEqual(status, 200)
        self.assertTrue(self.server.finished.wait(1))
        status, _, _ = self.request("GET", "/draft")
        self.assertEqual(status, 410)

    def test_invalid_status_does_not_finish_job(self):
        status, _, _ = self.request("POST", "/status", json.dumps({"state": "submitted"}))
        self.assertEqual(status, 400)
        self.assertFalse(self.server.finished.is_set())

    def test_arbitrary_file_routes_are_not_served(self):
        status, _, _ = self.request("GET", "/etc/passwd")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
