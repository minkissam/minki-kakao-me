"""Personal KakaoTalk sender; Windows, Python >= 3.10, no third-party packages."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import getpass
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser

AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
CUSTOM_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/send"
SEND_ENDPOINTS = (SEND_URL, CUSTOM_SEND_URL)
DEFAULT_REDIRECT = "http://localhost:8765/callback"


class KakaoError(Exception):
    def __init__(self, code, message, status=None):
        super().__init__(message)
        self.code, self.status = str(code), status


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def config_dir():
    override = os.environ.get("KAKAO_ME_CONFIG_DIR")
    if override:
        return Path(override)
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise KakaoError("windows_required", "Windows LOCALAPPDATA 경로가 필요합니다.")
    return Path(root) / "Codex" / "kakao-me"


def dpapi(data, decrypt=False):
    if os.name != "nt":
        raise KakaoError("windows_required", "이 스킬은 Windows DPAPI를 사용합니다.")

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise KakaoError("credential_store_error", "Windows 인증정보 암호화/복호화에 실패했습니다.")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel.LocalFree(target.pbData)


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else config_dir()
        self.path = self.directory / "profile.dpapi"

    def load(self):
        if not self.path.exists():
            return {}
        try:
            return json.loads(dpapi(self.path.read_bytes(), decrypt=True).decode("utf-8"))
        except (ValueError, OSError) as exc:
            raise KakaoError("credential_store_error", "저장된 설정을 읽지 못했습니다.") from exc

    def save(self, value):
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = self.directory / ("profile-" + uuid.uuid4().hex + ".tmp")
        try:
            temp.write_bytes(dpapi(json.dumps(value, ensure_ascii=False).encode("utf-8")))
            os.replace(temp, self.path)
        finally:
            if temp.exists():
                temp.unlink()

    @contextmanager
    def locked(self):
        import msvcrt
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "profile.lock").open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise KakaoError("busy", "다른 minki-kakao-me 실행이 끝난 뒤 다시 시도하세요.") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def validate_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise KakaoError("invalid_url", "링크는 인증정보 없는 http/https URL이어야 합니다.") from exc
    return url


def validate_config(value):
    client_id = str(value.get("client_id", "")).strip()
    if not client_id or "본인" in client_id:
        raise KakaoError("invalid_config", "실제 REST API 키를 입력하세요.")
    uri = str(value.get("redirect_uri") or DEFAULT_REDIRECT)
    parsed = urllib.parse.urlsplit(uri)
    if (parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1")
            or not parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.path):
        raise KakaoError("invalid_redirect", "로컬 http 콜백 주소에 포트와 경로가 필요합니다.")
    return {"client_id": client_id, "client_secret": str(value.get("client_secret", "")).strip(),
            "redirect_uri": uri, "default_url": validate_url(value.get("default_url", ""))}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_form(url, data, token=None):
    headers = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, urllib.parse.urlencode(data).encode("utf-8"), headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=25) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise KakaoError("delivery_unknown" if url in SEND_ENDPOINTS else "network_error",
                         "응답을 확인하지 못했습니다. 자동 재시도하지 않았습니다.") from exc
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
    except (ValueError, UnicodeError) as exc:
        raise KakaoError("delivery_unknown" if url in SEND_ENDPOINTS else "invalid_response",
                         "API 응답 형식을 확인하지 못했습니다.", status) from exc
    if status >= 500 and url in SEND_ENDPOINTS:
        raise KakaoError("delivery_unknown", "카카오 서버 오류로 전달 여부를 확인하지 못했습니다.", status)
    if not 200 <= status < 300:
        code = re.sub(r"[^a-zA-Z0-9_-]", "", str(result.get("error_code", result.get("code", result.get("error", "api_error")))))[:64]
        raise KakaoError(code or "api_error", "카카오 API가 요청을 거절했습니다. 설정/동의를 확인하세요.", status)
    return result


def merge_tokens(previous, response, now=None):
    now = time.time() if now is None else now
    if not response.get("access_token") or not isinstance(response.get("expires_in"), (int, float)):
        raise KakaoError("invalid_token_response", "정상 토큰 응답이 아닙니다.")
    merged = dict(previous)
    merged.update(access_token=response["access_token"], expires_at=now + response["expires_in"])
    if response.get("refresh_token"):
        merged["refresh_token"] = response["refresh_token"]
        if "refresh_token_expires_in" in response:
            merged["refresh_expires_at"] = now + response["refresh_token_expires_in"]
    return merged


def access_token(state, store, force=False):
    tokens = state.get("tokens", {})
    if not force and tokens.get("access_token") and tokens.get("expires_at", 0) > time.time() + 60:
        return tokens["access_token"]
    if not tokens.get("refresh_token") or (tokens.get("refresh_expires_at") and tokens["refresh_expires_at"] <= time.time()):
        raise KakaoError("login_required", "login 명령으로 카카오 연결이 필요합니다.")
    config = state["config"]
    params = {"grant_type": "refresh_token", "client_id": config["client_id"], "refresh_token": tokens["refresh_token"]}
    if config.get("client_secret"):
        params["client_secret"] = config["client_secret"]
    state["tokens"] = merge_tokens(tokens, post_form(TOKEN_URL, params))
    store.save(state)
    return state["tokens"]["access_token"]


def make_template(text, url, button="자세히 보기"):
    if not isinstance(text, str) or not text.strip() or len(text) > 200:
        raise KakaoError("invalid_text", "메시지는 공백이 아닌 1~200자여야 합니다.")
    if not button.strip() or len(button) > 10:
        raise KakaoError("invalid_button", "버튼 제목은 1~10자로 입력하세요.")
    return {"object_type": "text", "text": text, "link": {"web_url": validate_url(url), "mobile_web_url": url}, "button_title": button}


def url_origin(url):
    validate_url(url)
    parts = urllib.parse.urlsplit(url)
    try:
        host = parts.hostname.encode("idna").decode("ascii").lower()
        port = parts.port
    except (ValueError, UnicodeError) as exc:
        raise KakaoError("invalid_url", "URL의 호스트와 포트를 확인하세요.") from exc
    if any(c.isspace() or ord(c) < 32 for c in url) or "\\" in url:
        raise KakaoError("invalid_url", "URL에 공백이나 제어 문자를 넣을 수 없습니다.")
    if ":" in host:
        host = "[" + host + "]"
    suffix = "" if not port or (parts.scheme, port) in (("http", 80), ("https", 443)) else ":" + str(port)
    return parts.scheme.lower() + "://" + host + suffix


def validate_messaging(value):
    allowed = {"registered_web_origins", "buttonless_text_template_id", "buttonless_image_template_id"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise KakaoError("invalid_messaging", "메시지 설정의 지원하지 않는 항목을 확인하세요.")
    clean = {}
    for key, item in value.items():
        if key == "registered_web_origins":
            if not isinstance(item, list) or not all(isinstance(x, str) for x in item):
                raise KakaoError("invalid_messaging", "등록 도메인은 URL 배열이어야 합니다.")
            origins = []
            for url in item:
                parts = urllib.parse.urlsplit(url)
                if parts.path not in ("", "/") or parts.query or parts.fragment:
                    raise KakaoError("invalid_messaging", "도메인에는 경로·쿼리·프래그먼트를 넣지 마세요.")
                origins.append(url_origin(url))
            clean[key] = list(dict.fromkeys(origins))
        else:
            if isinstance(item, bool) or not re.fullmatch(r"[1-9][0-9]*", str(item)):
                raise KakaoError("invalid_messaging", "사용자 정의 템플릿 ID는 양의 정수여야 합니다.")
            clean[key] = str(item)
    return clean


def checked_link(url, mobile_url, settings):
    if not isinstance(url, str) or not isinstance(mobile_url, str):
        raise KakaoError("missing_link", "각 버튼에는 실제 목적지 URL이 필요합니다.")
    origins = settings.get("registered_web_origins", [])
    for target in (url, mobile_url):
        if url_origin(target) not in origins:
            raise KakaoError("unregistered_domain", "목적지 도메인을 카카오 앱에 등록하고 messaging 설정에 반영하세요. 임의의 기본 주소로 대체하지 않습니다.")
    return {"web_url": url, "mobile_web_url": mobile_url}


def plan_message(spec, settings):
    """Resolve explicit choices or Codex-selected actions, without network or mutation."""
    allowed = {"text", "title", "type", "buttons", "button_count", "actions", "image_url", "image_width", "image_height"}
    if not isinstance(spec, dict) or set(spec) - allowed:
        raise KakaoError("invalid_message", "메시지 JSON의 지원하지 않는 항목을 확인하세요.")
    text, title = spec.get("text", ""), spec.get("title", "")
    if not isinstance(text, str) or len(text) > 200 or not isinstance(title, str) or len(title) > 100:
        raise KakaoError("invalid_text", "본문은 최대 200자, 카드 제목은 최대 100자로 지정하세요. 자동으로 자르지 않습니다.")
    image_url = spec.get("image_url")
    if image_url is not None:
        if not isinstance(image_url, str) or not image_url:
            raise KakaoError("invalid_image", "사진을 빼려면 image_url을 null로 지정하세요.")
        url_origin(image_url)
        host = urllib.parse.urlsplit(image_url).hostname
        if host in ("localhost", "127.0.0.1", "::1") or "." not in host:
            raise KakaoError("invalid_image", "카카오가 읽을 수 있는 외부 이미지 URL이 필요합니다.")
    if not (text.strip() or title.strip() or image_url):
        raise KakaoError("invalid_text", "본문·제목·이미지 중 표시할 내용이 필요합니다.")
    dimensions = {}
    for key in ("image_width", "image_height"):
        if key in spec:
            if not image_url or type(spec[key]) is not int or not 1 <= spec[key] <= 10000:
                raise KakaoError("invalid_image", "이미지 크기는 이미지가 있을 때 양의 픽셀 값으로 지정하세요.")
            dimensions[key] = spec[key]
    count = spec.get("button_count", "auto")
    if count != "auto" and (type(count) is not int or count not in (0, 1, 2)):
        raise KakaoError("invalid_buttons", "버튼 개수는 auto, 0, 1, 2 중 하나입니다.")
    explicit = "buttons" in spec
    candidates = spec.get("buttons") if explicit else spec.get("actions", [])
    if not isinstance(candidates, list):
        raise KakaoError("invalid_buttons", "buttons/actions는 버튼 객체의 배열이어야 합니다.")
    if explicit:
        if len(candidates) > 2 or (count != "auto" and len(candidates) != count):
            raise KakaoError("invalid_buttons", "명시한 버튼 목록과 버튼 개수가 서로 일치해야 합니다(최대 2개).")
        selected = candidates
    else:
        wanted = min(2, len(candidates)) if count == "auto" else count
        if wanted > len(candidates):
            raise KakaoError("missing_link", "요청한 버튼 수만큼 목적지와 문구가 필요합니다.")
        selected = candidates[:wanted]
    buttons = []
    for item in selected:
        if not isinstance(item, dict) or set(item) - {"title", "url", "mobile_url"}:
            raise KakaoError("invalid_buttons", "버튼에는 title, url, 선택적인 mobile_url을 지정하세요.")
        label = item.get("title", "")
        if not isinstance(label, str) or not label.strip() or len(label) > 10:
            raise KakaoError("invalid_button", "버튼 문구는 1~10자로 지정하세요.")
        url = item.get("url")
        buttons.append({"title": label, "link": checked_link(url, item.get("mobile_url", url), settings)})
    mode = spec.get("type", "auto")
    if mode not in ("auto", "text", "feed"):
        raise KakaoError("invalid_message", "type은 auto, text, feed 중 하나입니다.")
    if mode == "text" and (image_url or title):
        raise KakaoError("conflicting_layout", "text 형식에는 이미지·별도 제목을 넣을 수 없습니다. feed 또는 auto를 지정하세요.")
    card = bool(image_url or title or mode == "feed")
    preview = {"layout": "feed" if card else "text", "text": text, "title": title,
               "button_count": len(buttons), "buttons": selected, "image_url": image_url,
               "selection": "explicit" if explicit else "auto_from_actions"}
    if not buttons:
        key = "buttonless_image_template_id" if image_url else "buttonless_text_template_id"
        template_id = settings.get(key)
        if not template_id:
            raise KakaoError("missing_buttonless_template", "버튼 없는 메시지용 템플릿이 등록되지 않았습니다. references/templates.md의 설정 절차를 확인하세요.")
        if dimensions:
            raise KakaoError("custom_image_dimensions", "버튼 없는 이미지의 크기·비율은 카카오 사용자 정의 템플릿에서 설정합니다. 픽셀 옵션을 생략하세요.")
        args = {"TITLE": title, "TEXT": text}
        if image_url:
            args["IMAGE"] = image_url
        preview["layout"] = "buttonless_image" if image_url else "buttonless_text"
        return {"endpoint": CUSTOM_SEND_URL, "form": {"template_id": str(template_id), "template_args": json.dumps(args, ensure_ascii=False)}, "preview": preview}
    link = buttons[0]["link"].copy()
    if card:
        content = {"title": title, "description": text, "link": link}
        if image_url:
            content.update(image_url=image_url, **dimensions)
        template = {"object_type": "feed", "content": content, "buttons": buttons}
    else:
        template = {"object_type": "text", "text": text, "link": link, "buttons": buttons}
    return {"endpoint": SEND_URL, "form": {"template_object": json.dumps(template, ensure_ascii=False)}, "preview": preview}


def send_message(state, store, template, request_id):
    return send_request(state, store, template, request_id, SEND_URL,
                        {"template_object": json.dumps(template, ensure_ascii=False)})


def send_plan(state, store, plan, request_id):
    if plan["endpoint"] == SEND_URL:
        return send_message(state, store, json.loads(plan["form"]["template_object"]), request_id)
    return send_request(state, store, {"endpoint": plan["endpoint"], "form": plan["form"]},
                        request_id, plan["endpoint"], plan["form"])


def send_request(state, store, template, request_id, endpoint, form):
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", request_id):
        raise KakaoError("invalid_request_id", "request ID는 영문·숫자·._:-로 1~120자입니다.")
    fingerprint = hashlib.sha256(json.dumps(template, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    receipts = state.setdefault("receipts", {})
    existing = receipts.get(request_id)
    if existing:
        if existing["hash"] != fingerprint:
            raise KakaoError("request_conflict", "같은 request ID에 다른 메시지가 지정되었습니다.")
        if existing["status"] == "sent":
            return {"ok": True, "sent": True, "duplicate_skipped": True, "result_code": 0, "request_id": request_id}
        raise KakaoError("delivery_unknown", "이 ID의 이전 전송 결과가 확정되지 않았습니다. 채팅을 확인하세요.")
    token = access_token(state, store)
    receipts[request_id] = {"hash": fingerprint, "status": "sending", "at": time.time()}
    while len(receipts) > 100:
        del receipts[next(iter(receipts))]
    store.save(state)
    try:
        try:
            response = post_form(endpoint, form, token)
        except KakaoError as exc:
            if exc.status != 401 or exc.code != "-401":
                raise
            token = access_token(state, store, force=True)
            response = post_form(endpoint, form, token)
        if response.get("result_code") != 0:
            raise KakaoError("delivery_unknown", "API 전송 성공을 확인하지 못했습니다.")
    except KakaoError as exc:
        if exc.code == "delivery_unknown":
            receipts[request_id]["status"] = "unknown"
        else:
            del receipts[request_id]
        store.save(state)
        raise
    receipts[request_id]["status"] = "sent"
    store.save(state)
    return {"ok": True, "sent": True, "result_code": 0, "request_id": request_id}


def login(state, store, no_browser=False):
    config = state["config"]
    uri = urllib.parse.urlsplit(config["redirect_uri"])
    expected_state, result = secrets.token_urlsafe(32), {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            valid = parsed.path == uri.path and secrets.compare_digest(query.get("state", [""])[0], expected_state)
            if not valid:
                self.send_error(400, "Invalid callback")
                return
            if "error" in query:
                result["error"] = True
            elif query.get("code"):
                result["code"] = query["code"][0]
            else:
                self.send_error(400, "Missing authorization code")
                return
            body = "카카오 인증 응답을 받았습니다. 터미널에서 연결 결과를 확인하세요.".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    auth_url = AUTH_URL + "?" + urllib.parse.urlencode({"client_id": config["client_id"], "redirect_uri": config["redirect_uri"], "response_type": "code", "scope": "talk_message", "state": expected_state})
    with http.server.HTTPServer(("127.0.0.1", uri.port), Handler) as server:
        server.timeout = 1
        emit({"step": "browser_login", "authorization_url": auth_url, "timeout_seconds": 300})
        if not no_browser:
            webbrowser.open(auth_url)
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if result.get("error"):
        raise KakaoError("consent_denied", "카카오 로그인이 취소되었거나 거절되었습니다.")
    if not result.get("code"):
        raise KakaoError("login_timeout", "5분 안에 콜백을 받지 못했습니다. 다시 login을 실행하세요.")
    params = {"grant_type": "authorization_code", "client_id": config["client_id"], "redirect_uri": config["redirect_uri"], "code": result["code"]}
    if config.get("client_secret"):
        params["client_secret"] = config["client_secret"]
    state["tokens"] = merge_tokens({}, post_form(TOKEN_URL, params))
    store.save(state)
    return {"ok": True, "authenticated": True, "message_sent": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="로컬 연결 상태만 확인")
    messaging = commands.add_parser("messaging", help="비밀정보 없는 템플릿·등록 도메인 설정; 토큰 유지")
    messaging.add_argument("--from-file", type=Path)
    configure = commands.add_parser("configure", help="대화형 또는 로컬 파일로 설정")
    configure.add_argument("--from-file", type=Path)
    auth = commands.add_parser("login", help="카카오 OAuth 연결; 메시지는 보내지 않음")
    auth.add_argument("--no-browser", action="store_true")
    send = commands.add_parser("send", help="내 채팅으로 텍스트·사진·0~2개 버튼 전송")
    content = send.add_mutually_exclusive_group(required=True)
    content.add_argument("--text")
    content.add_argument("--text-file", type=Path)
    content.add_argument("--message-file", type=Path)
    send.add_argument("--url")
    send.add_argument("--button", default=None)
    send.add_argument("--request-id", default=None)
    send.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    store = Store()
    if args.command == "status":
        state = store.load()
        tokens = state.get("tokens", {})
        emit({"ok": True, "configured": bool(state.get("config")), "authenticated": bool(tokens.get("refresh_token")),
              "access_token_expired": tokens.get("expires_at", 0) <= time.time(),
              "refresh_token_expired": tokens.get("refresh_expires_at", 0) <= time.time(), "storage": str(store.path),
              "messaging": state.get("messaging", {})})
        return 0
    if args.command == "messaging":
        if not args.from_file:
            emit({"ok": True, "messaging": store.load().get("messaging", {})})
            return 0
        changes = validate_messaging(json.loads(args.from_file.read_text(encoding="utf-8-sig")))
        with store.locked():
            state = store.load()
            state.setdefault("messaging", {}).update(changes)
            store.save(state)
        emit({"ok": True, "messaging": state["messaging"], "tokens_preserved": True})
        return 0
    if args.command == "send" and args.dry_run:
        state = store.load()
        plan = cli_plan(args, state.get("messaging", {}))
        emit({"ok": True, "sent": False, "dry_run": True, **plan})
        return 0
    with store.locked():
        state = store.load()
        if args.command == "configure":
            if args.from_file:
                config = json.loads(args.from_file.read_text(encoding="utf-8-sig"))
            else:
                config = {"client_id": getpass.getpass("REST API key: "), "client_secret": getpass.getpass("Client secret (disabled: Enter): "),
                          "default_url": input("Default link URL: ").strip(), "redirect_uri": input(f"Redirect URI [{DEFAULT_REDIRECT}]: ").strip() or DEFAULT_REDIRECT}
            store.save({"config": validate_config(config)})
            emit({"ok": True, "configured": True, "authenticated": False, "next": "login"})
            return 0
        if not state.get("config"):
            raise KakaoError("not_configured", "먼저 configure로 앱 설정을 저장하세요.")
        if args.command == "login":
            emit(login(state, store, args.no_browser))
        elif args.command == "send":
            plan = cli_plan(args, state.get("messaging", {}))
            result = send_plan(state, store, plan, args.request_id or str(uuid.uuid4()))
            emit({**result, "preview": plan["preview"]})
    return 0


def cli_plan(args, settings):
    if args.message_file:
        if args.url is not None or args.button is not None:
            raise KakaoError("conflicting_layout", "message-file의 버튼 설정과 --url/--button을 함께 지정하지 마세요.")
        spec = json.loads(args.message_file.read_text(encoding="utf-8-sig"))
    else:
        text = args.text_file.read_text(encoding="utf-8-sig") if args.text_file else args.text
        spec = {"text": text}
        if args.button is not None and not args.url:
            raise KakaoError("missing_link", "버튼 문구와 함께 --url로 실제 목적지를 지정하세요.")
        if args.url:
            spec["buttons"] = [{"title": args.button or "내용 열기", "url": args.url}]
    return plan_message(spec, settings)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KakaoError as exc:
        emit({"ok": False, "error": exc.code, "message": str(exc), "http_status": exc.status})
        sys.exit(2)
    except (OSError, ValueError) as exc:
        emit({"ok": False, "error": "local_error", "message": "로컬 설정·파일·포트를 확인하세요.", "type": type(exc).__name__})
        sys.exit(2)
