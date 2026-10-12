"""Focused first-connection checks with temporary profiles and fake Kakao replies."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kakao_me as km
from kakao_setup import SetupServer, create_setup_server


@unittest.skipUnless(os.name == "nt", "Windows DPAPI")
class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = km.Store(Path(self.temp.name) / "profile")
        self.server = SetupServer(self.store, "http://localhost:0/callback")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, data=None, authenticated=True):
        headers = {"Origin": self.base, "Content-Type": "application/json"}
        if authenticated:
            headers["X-Setup-Token"] = self.server.session
        request = urllib.request.Request(self.base + path,
            data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def connect(self):
        status, result = self.request("/api/config", {"client_id": "dummy", "client_secret": "dummy-secret"})
        self.assertEqual(status, 200)
        self.assertEqual(result["next_step"], "login")
        _, result = self.request("/api/login", {})
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(result["authorization_url"]).query)
        self.assertEqual(params["scope"], ["talk_message"])
        self.assertEqual(params["redirect_uri"], [self.server.redirect_uri])
        with patch.object(km, "post_form", return_value={"access_token": "dummy-access", "refresh_token": "dummy-refresh", "expires_in": 1000, "refresh_token_expires_in": 10000}):
            # A browser follows the OAuth callback back to the setup page.
            callback = self.base + self.server.callback_path + "?" + urllib.parse.urlencode({"state": params["state"][0], "code": "dummy-code"})
            with urllib.request.urlopen(callback, timeout=5) as response:
                self.assertIn("카카오톡 나에게 보내기 연결", response.read().decode())
        self.request("/api/messaging", {"buttonless_text_template_id": "12345"})
        return self.store.load()

    def test_first_connection_and_first_send_over_local_http(self):
        self.assertEqual(self.request("/api/status", authenticated=False)[0], 404)
        self.assertEqual(self.request("/api/config", {}, authenticated=False)[0], 403)
        self.connect()
        _, status = self.request("/api/status")
        self.assertTrue(status["ready_to_send_text"])
        self.assertNotIn("dummy-secret", json.dumps(status))
        with patch.object(km, "post_form", return_value={"result_code": 0}) as send:
            _, result = self.request("/api/send", {"text": "연결 완료"})
            self.assertTrue(result["sent"])
            _, result = self.request("/api/send", {"text": "연결 완료"})
            self.assertTrue(result["duplicate_skipped"])
            self.assertEqual(send.call_count, 1)
        self.assertEqual(self.request("/api/close", {})[1], {"ok": True, "closed": True})

    def test_same_app_edit_preserves_connection_and_app_swap_has_backup(self):
        before = self.connect()
        _, result = self.request("/api/config", {"client_id": "", "client_secret": ""})
        self.assertTrue(result["ready_to_send_text"])
        self.assertEqual(self.store.load()["tokens"], before["tokens"])
        self.assertEqual(self.store.load()["messaging"], before["messaging"])
        self.assertEqual(self.request("/api/config", {"client_id": "other", "client_secret": "new"})[0], 400)
        _, result = self.request("/api/config", {"client_id": "other", "client_secret": "new", "replace_app": True})
        self.assertEqual(result["next_step"], "login")
        backups = list(self.store.directory.glob("profile-backup-*.dpapi"))
        self.assertEqual(len(backups), 1)
        restored = json.loads(km.dpapi(backups[0].read_bytes(), decrypt=True))
        self.assertEqual(restored["tokens"], before["tokens"])
        self.assertNotIn("messaging", self.store.load())

    def test_cli_partial_config_and_online_consent(self):
        before = self.connect()
        file = Path(self.temp.name) / "config.local.json"
        file.write_text(json.dumps({"client_secret": "updated"}), encoding="utf-8")
        with patch.dict(os.environ, {"KAKAO_ME_CONFIG_DIR": str(self.store.directory)}), patch.object(km, "emit"):
            self.assertEqual(km.main(["configure", "--from-file", str(file)]), 0)
        self.assertEqual(self.store.load()["tokens"], before["tokens"])
        with patch.object(km, "get_api", return_value={"scopes": [{"id": "talk_message", "using": True, "agreed": True}]}):
            self.assertTrue(km.doctor(self.store, online=True)["ok"])
        with patch.object(km, "get_api", return_value={"scopes": [{"id": "talk_message", "using": True, "agreed": False}]}):
            result = km.doctor(self.store, online=True)
            self.assertFalse(result["ok"])
            self.assertIn("동의", result["checks"][-1]["action"])

    def test_unknown_send_remains_blocked_after_reopening_setup(self):
        self.connect()
        with patch.object(km, "post_form", side_effect=km.KakaoError("delivery_unknown", "timeout")) as api:
            _, result = self.request("/api/send", {"text": "연결 완료"})
            self.assertEqual(result["error"], "delivery_unknown")
            reopened = SetupServer(self.store, "http://localhost:0/callback")
            try:
                self.assertTrue(reopened.delivery_unknown)
                with self.assertRaises(km.KakaoError):
                    reopened.action("/api/send", {"text": "새 내용"})
            finally:
                reopened.server_close()
            self.assertEqual(api.call_count, 1)

    def test_changed_callback_preserves_host_path_and_connection(self):
        self.server.callback_path = "/oauth/kakao-return"
        self.server.redirect_uri = f"http://127.0.0.1:{self.server.server_port}/oauth/kakao-return"
        before = self.connect()
        reopened = create_setup_server(self.store)
        try:
            uri = urllib.parse.urlsplit(reopened.redirect_uri)
            self.assertEqual(uri.hostname, "127.0.0.1")
            self.assertEqual(uri.path, "/oauth/kakao-return")
            self.assertNotEqual(uri.port, self.server.server_port)
            self.assertTrue(reopened.status()["callback_changed"])
            with self.assertRaises(km.KakaoError):
                reopened.action("/api/login", {})
            reopened.action("/api/config", {"client_id": "", "client_secret": ""})
            self.assertFalse(reopened.status()["callback_changed"])
            self.assertEqual(self.store.load()["tokens"], before["tokens"])
            self.assertEqual(self.store.load()["messaging"], before["messaging"])
            url = reopened.action("/api/login", {})["authorization_url"]
            self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["redirect_uri"], [reopened.redirect_uri])
        finally:
            reopened.server_close()

    def test_named_templates_with_links_preview_send_and_reuse(self):
        self.connect()
        self.request("/api/messaging", {"registered_web_origins": ["https://example.com", "https://mobile.example.com"]})
        spec = {"title": "보고서", "text": "완료", "buttons": [
            {"title": "자료 열기", "url": "https://example.com/report?id=1#page=2", "mobile_url": "https://mobile.example.com/report?id=1"},
            {"title": "관련 문서", "url": "https://example.com/docs"}]}
        status, result = self.request("/api/template", {"name": "주간 보고서", "message": spec})
        self.assertEqual(status, 200)
        self.assertTrue(any(t["name"] == "주간 보고서" for t in result["templates"]))
        _, preview = self.request("/api/preview", {"message": {"template": "주간 보고서", "text": "둘째 주"}})
        self.assertEqual(preview["preview"]["button_count"], 2)
        self.assertEqual(preview["preview"]["text"], "둘째 주")
        with patch.object(km, "post_form", return_value={"result_code": 0}) as send:
            self.assertTrue(self.request("/api/send", {"message": {"template": "주간 보고서"}})[1]["sent"])
            self.assertTrue(self.request("/api/send", {"message": {"template": "주간 보고서"}})[1]["duplicate_skipped"])
            changed = {**spec, "buttons": [{"title": "새 자료", "url": "https://example.com/new"}]}
            self.assertTrue(self.request("/api/send", {"message": changed})[1]["sent"])
            self.assertEqual(send.call_count, 2)
        custom = km.plan_message({**spec, "template_id": "98765"}, self.store.load()["messaging"])
        args = json.loads(custom["form"]["template_args"])
        self.assertEqual(custom["form"]["template_id"], "98765")
        self.assertEqual(args["DOMAIN1"], "https://example.com")
        self.assertEqual(args["PATH1"], "/report?id=1#page=2")
        self.assertEqual(args["MOBILE_DOMAIN1"], "https://mobile.example.com")
        self.assertEqual(args["BUTTON2"], "관련 문서")
        with patch.dict(os.environ, {"KAKAO_ME_CONFIG_DIR": str(self.store.directory)}), patch.object(km, "emit") as output:
            self.assertEqual(km.main(["send", "--template", "주간 보고서", "--text", "셋째 주", "--dry-run"]), 0)
            self.assertEqual(output.call_args.args[0]["preview"]["button_count"], 2)
        self.assertEqual(self.request("/api/template", {"name": "주간 보고서", "delete": True})[0], 200)


if __name__ == "__main__":
    unittest.main()
