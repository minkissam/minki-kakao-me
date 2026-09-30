"""Offline tests. No real credentials, OAuth flow, or outbound messages."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "kakao_me.py"
spec = importlib.util.spec_from_file_location("kakao_me", MODULE)
km = importlib.util.module_from_spec(spec)
spec.loader.exec_module(km)


class MemoryStore:
    def __init__(self):
        self.saved = None

    def save(self, state):
        self.saved = copy.deepcopy(state)


def state():
    return {"config": {"client_id": "dummy", "client_secret": "dummy-secret"},
            "tokens": {"access_token": "dummy-access", "expires_at": time.time() + 1000,
                       "refresh_token": "dummy-refresh", "refresh_expires_at": time.time() + 10000}}


class KakaoTests(unittest.TestCase):
    def test_unicode_and_length(self):
        self.assertEqual(len(km.make_template("🙂" * 200, "https://example.com")["text"]), 200)
        with self.assertRaises(km.KakaoError):
            km.make_template("가" * 201, "https://example.com")
        with self.assertRaises(km.KakaoError):
            km.make_template(" ", "https://example.com")

    def test_url_and_loopback_validation(self):
        with self.assertRaises(km.KakaoError):
            km.make_template("hello", "javascript:alert(1)")
        with self.assertRaises(km.KakaoError):
            km.validate_config({"client_id": "dummy", "default_url": "https://example.com", "redirect_uri": "http://example.com:8765/callback"})

    def test_refresh_preserves_optional_token(self):
        merged = km.merge_tokens({"refresh_token": "old", "refresh_expires_at": 1000}, {"access_token": "new", "expires_in": 30}, now=100)
        self.assertEqual(merged["refresh_token"], "old")
        self.assertEqual(merged["refresh_expires_at"], 1000)
        self.assertEqual(merged["expires_at"], 130)

    def test_rotation_saved(self):
        data, store = state(), MemoryStore()
        data["tokens"]["expires_at"] = 0
        with patch.object(km, "post_form", return_value={"access_token": "new", "expires_in": 100, "refresh_token": "rotated", "refresh_token_expires_in": 500}):
            self.assertEqual(km.access_token(data, store), "new")
        self.assertEqual(store.saved["tokens"]["refresh_token"], "rotated")

    def test_send_and_idempotent_replay(self):
        data, store = state(), MemoryStore()
        template = km.make_template("한국어 결과", "https://example.com")
        with patch.object(km, "post_form", return_value={"result_code": 0}) as api:
            self.assertTrue(km.send_message(data, store, template, "request-1")["sent"])
            self.assertTrue(km.send_message(data, store, template, "request-1")["duplicate_skipped"])
            self.assertEqual(api.call_count, 1)
            with self.assertRaises(km.KakaoError) as caught:
                km.send_message(data, store, km.make_template("different", "https://example.com"), "request-1")
            self.assertEqual(caught.exception.code, "request_conflict")

    def test_unknown_delivery_is_not_retried(self):
        data, store = state(), MemoryStore()
        template = km.make_template("hello", "https://example.com")
        with patch.object(km, "post_form", side_effect=km.KakaoError("delivery_unknown", "timeout")) as api:
            for _ in range(2):
                with self.assertRaises(km.KakaoError):
                    km.send_message(data, store, template, "request-unknown")
            self.assertEqual(api.call_count, 1)
        self.assertEqual(store.saved["receipts"]["request-unknown"]["status"], "unknown")

    def test_401_refresh_and_retry_once(self):
        data, store = state(), MemoryStore()
        results = [km.KakaoError("-401", "invalid", 401), {"access_token": "renewed", "expires_in": 1000}, {"result_code": 0}]
        with patch.object(km, "post_form", side_effect=results) as api:
            result = km.send_message(data, store, km.make_template("hello", "https://example.com"), "refresh-once")
            self.assertTrue(result["sent"])
            self.assertEqual(api.call_count, 3)
            self.assertEqual(api.call_args_list[1].args[0], km.TOKEN_URL)

    def test_failed_refresh_before_send_has_no_receipt(self):
        data, store = state(), MemoryStore()
        data["tokens"]["expires_at"] = 0
        with patch.object(km, "post_form", side_effect=km.KakaoError("invalid_grant", "expired", 400)):
            with self.assertRaises(km.KakaoError):
                km.send_message(data, store, km.make_template("hello", "https://example.com"), "expired")
        self.assertFalse(data.get("receipts"))

    def test_dry_run_has_no_network_or_store_write(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "absent-config"
            with patch.dict(os.environ, {"KAKAO_ME_CONFIG_DIR": str(directory)}), patch.object(km, "post_form") as api, patch.object(km, "emit") as output:
                with patch.object(km.Store, "load", return_value={"messaging": messaging()}):
                    self.assertEqual(km.main(["send", "--text", "미리보기", "--url", "https://example.com/result", "--dry-run"]), 0)
                api.assert_not_called()
                self.assertFalse(directory.exists())
                self.assertFalse(output.call_args.args[0]["sent"])

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_real_dpapi_roundtrip_and_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            store = km.Store(temp)
            value = {"dummy": "offline-test-secret-only", "unicode": "한글"}
            with store.locked():
                store.save(value)
                self.assertEqual(store.load(), value)
                with self.assertRaises(km.KakaoError):
                    with store.locked():
                        pass
            self.assertNotIn(b"offline-test-secret-only", store.path.read_bytes())


def messaging():
    return {"registered_web_origins": ["https://example.com", "https://mobile.example.com"],
            "buttonless_text_template_id": "123", "buttonless_image_template_id": "456"}


def action(label="결과 열기", path="/report#page=2"):
    return {"title": label, "url": "https://example.com" + path}


class LayoutTests(unittest.TestCase):
    def test_six_layouts_have_exact_button_counts_images_and_routes(self):
        for image in (None, "https://images.example.com/result.png"):
            for count in range(3):
                with self.subTest(image=image, count=count):
                    spec = {"text": "결과 알림", "image_url": image,
                            "buttons": [action(), action("관련 문서", "/docs")][:count]}
                    plan = km.plan_message(spec, messaging())
                    self.assertEqual(plan["preview"]["button_count"], count)
                    self.assertEqual(plan["preview"]["image_url"], image)
                    if count == 0:
                        self.assertEqual(plan["endpoint"], km.CUSTOM_SEND_URL)
                        self.assertEqual(plan["form"]["template_id"], "456" if image else "123")
                        self.assertEqual(json.loads(plan["form"]["template_args"])["TEXT"], "결과 알림")
                        self.assertNotIn("template_object", plan["form"])
                    else:
                        obj = json.loads(plan["form"]["template_object"])
                        self.assertEqual(len(obj["buttons"]), count)
                        self.assertEqual(obj["object_type"], "feed" if image else "text")
                        self.assertEqual(obj["buttons"][0]["link"]["web_url"], "https://example.com/report#page=2")
                        if image:
                            self.assertEqual(obj["content"]["image_url"], image)

    def test_auto_without_actions_never_adds_placeholder_link(self):
        plan = km.plan_message({"text": "완료"}, messaging())
        self.assertEqual(plan["preview"]["button_count"], 0)
        self.assertNotIn("https://", plan["form"]["template_args"])

    def test_explicit_empty_buttons_override_available_actions(self):
        plan = km.plan_message({"text": "완료", "buttons": [], "actions": [action()]}, messaging())
        self.assertEqual(plan["preview"]["button_count"], 0)

    def test_explicit_count_and_platform_links(self):
        first = {**action(), "mobile_url": "https://mobile.example.com/report?id=7#detail"}
        plan = km.plan_message({"text": "완료", "button_count": 1, "actions": [first, action("문서", "/docs")]}, messaging())
        obj = json.loads(plan["form"]["template_object"])
        self.assertEqual(len(obj["buttons"]), 1)
        self.assertEqual(obj["buttons"][0]["link"]["mobile_web_url"], first["mobile_url"])

    def test_missing_or_unregistered_link_is_not_replaced(self):
        for button in ({"title": "열기"}, {"title": "열기", "url": "https://example.com.evil.invalid/x"},
                       {"title": "열기", "url": "https://unregistered.example.org"}):
            with self.subTest(button=button), self.assertRaises(km.KakaoError):
                km.plan_message({"text": "완료", "buttons": [button]}, messaging())

    def test_no_silent_conflicts_or_extra_buttons(self):
        cases = [
            {"text": "hello", "buttons": [action()] * 3},
            {"text": "hello", "button_count": 2, "actions": [action()]},
            {"text": "hello", "button_count": 1, "buttons": []},
            {"text": "hello", "button_count": True},
            {"text": "hello", "type": "text", "image_url": "https://images.example.com/a.png"},
            {"text": "hello", "image_url": "C:\\picture.png"},
            {"text": "hello", "image_url": ""},
            {"text": "hello", "image_width": 640},
            {"text": "가" * 201},
            {"text": "hello", "button": []},
        ]
        for spec in cases:
            with self.subTest(spec=spec), self.assertRaises(km.KakaoError):
                km.plan_message(spec, messaging())

    def test_buttonless_template_absence_has_no_fallback(self):
        with self.assertRaises(km.KakaoError) as caught:
            km.plan_message({"text": "hello", "buttons": []}, {})
        self.assertEqual(caught.exception.code, "missing_buttonless_template")

    def test_title_only_uses_card_not_empty_text(self):
        plan = km.plan_message({"title": "완료", "buttons": [action()]}, messaging())
        self.assertEqual(json.loads(plan["form"]["template_object"])["object_type"], "feed")

    def test_custom_route_refresh_dedup_and_uncertain_delivery(self):
        plan = km.plan_message({"text": "안내", "buttons": []}, messaging())
        data, store = state(), MemoryStore()
        results = [km.KakaoError("-401", "invalid", 401), {"access_token": "new", "expires_in": 1000}, {"result_code": 0}]
        with patch.object(km, "post_form", side_effect=results) as api:
            self.assertTrue(km.send_plan(data, store, plan, "custom")["sent"])
            self.assertTrue(km.send_plan(data, store, plan, "custom")["duplicate_skipped"])
            self.assertEqual([x.args[0] for x in api.call_args_list], [km.CUSTOM_SEND_URL, km.TOKEN_URL, km.CUSTOM_SEND_URL])
        with patch.object(km, "post_form", side_effect=km.KakaoError("delivery_unknown", "timeout")) as api:
            for _ in range(2):
                with self.assertRaises(km.KakaoError):
                    km.send_plan(data, store, plan, "custom-unknown")
            self.assertEqual(api.call_count, 1)

    def test_custom_and_default_transport_errors_are_uncertain(self):
        for endpoint in km.SEND_ENDPOINTS:
            for response in (io.BytesIO(b"not-json"),
                             urllib.error.HTTPError(endpoint, 503, "service unavailable", {}, io.BytesIO(b'{"code":-1}'))):
                with self.subTest(endpoint=endpoint, response=type(response).__name__):
                    if isinstance(response, urllib.error.HTTPError):
                        setup = {"side_effect": response}
                    else:
                        response.status = 200
                        setup = {"return_value": response}
                    with patch.object(km.urllib.request.OpenerDirector, "open", **setup), self.assertRaises(km.KakaoError) as caught:
                        km.post_form(endpoint, {})
                    self.assertEqual(caught.exception.code, "delivery_unknown")

    def test_json_dry_run_is_read_only_and_preserves_exact_input(self):
        with tempfile.TemporaryDirectory() as temp:
            message = Path(temp) / "message.json"
            message.write_text(json.dumps({"text": "원문\n둘째 줄", "buttons": []}), encoding="utf-8")
            with patch.object(km.Store, "load", return_value={"messaging": messaging()}), \
                 patch.object(km.Store, "save") as save, patch.object(km, "post_form") as api, patch.object(km, "emit") as output:
                self.assertEqual(km.main(["send", "--message-file", str(message), "--dry-run"]), 0)
                save.assert_not_called()
                api.assert_not_called()
                self.assertEqual(output.call_args.args[0]["preview"]["text"], "원문\n둘째 줄")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_messaging_update_preserves_real_encrypted_state(self):
        with tempfile.TemporaryDirectory() as temp:
            config_dir = Path(temp) / "profile"
            store = km.Store(config_dir)
            data = state()
            data["receipts"] = {"old": {"status": "sent"}}
            store.save(data)
            file = Path(temp) / "settings.json"
            file.write_text(json.dumps(messaging()), encoding="utf-8")
            with patch.dict(os.environ, {"KAKAO_ME_CONFIG_DIR": str(config_dir)}), patch.object(km, "emit"):
                self.assertEqual(km.main(["messaging", "--from-file", str(file)]), 0)
            after = store.load()
            for key in ("config", "tokens", "receipts"):
                self.assertEqual(after[key], data[key])
            self.assertEqual(after["messaging"], messaging())


if __name__ == "__main__":
    unittest.main(verbosity=2)
