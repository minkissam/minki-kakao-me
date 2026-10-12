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
MESSAGE_FIELDS = {"text", "title", "type", "buttons", "button_count", "actions", "image_url", "image_width", "image_height", "template_id"}
BUILTIN_TEMPLATES = {
    "기본 알림": {"buttons": []},
    "사진 알림": {"buttons": [], "type": "feed"},
    "링크 버튼 1개": {"button_count": 1},
    "링크 버튼 2개": {"button_count": 2},
    "사진과 버튼 1개": {"type": "feed", "button_count": 1},
    "사진과 버튼 2개": {"type": "feed", "button_count": 2},
}


class KakaoError(Exception):
    def __init__(self, code, message, status=None):
        super().__init__(message)
        self.code, self.status = str(code), status


ERROR_HELP = {
    "KOE004": "앱의 [카카오 로그인]에서 사용 설정을 ON으로 저장한 뒤 다시 로그인하세요.",
    "KOE006": "[앱 > 플랫폼 키 > REST API 키]에 설정 화면의 콜백 주소를 그대로 등록하세요. 호스트, 포트와 경로까지 일치해야 합니다.",
    "KOE008": "[앱 > 플랫폼 키]에서 REST API 키를 복사해 앱 설정에 저장하세요.",
    "KOE010": "[앱 > 플랫폼 키 > REST API 키]의 클라이언트 시크릿을 복사해 저장한 뒤 다시 로그인하세요.",
    "KOE101": "[앱 > 플랫폼 키]의 REST API 키를 다시 복사해 저장하세요.",
    "KOE205": "[카카오 로그인 > 동의항목]에서 카카오톡 메시지 전송(talk_message)을 선택 동의 또는 이용 중 동의로 저장하세요.",
    "KOE303": "앱에 등록한 콜백 주소와 로컬 redirect_uri를 일치시킨 뒤 다시 로그인하세요.",
    "KOE320": "인가 코드가 만료되었거나 사용되었습니다. 카카오 로그인을 다시 시작하세요.",
    "KOE322": "카카오 로그인을 다시 시작해 계정을 연결하세요.",
    "KOE237": "토큰 요청 한도에 도달했습니다. 잠시 후 다시 로그인하세요.",
    "invalid_grant": "카카오 로그인을 다시 시작해 계정을 연결하세요.",
    "invalid_client": "같은 앱의 REST API 키와 클라이언트 시크릿을 다시 확인해 저장하세요.",
    "access_denied": "카카오 로그인 화면에서 본인 계정으로 로그인하고 메시지 전송에 동의하세요.",
    "-3": "앱의 카카오 로그인과 talk_message 동의항목을 활성화한 뒤 다시 로그인하세요.",
    "-402": "[카카오 로그인 > 동의항목]의 talk_message 설정을 확인하고 다시 로그인해 전송에 동의하세요.",
    "-401": "카카오 로그인을 다시 시작해 계정을 연결하세요.",
    "-5": "앱 소유자 계정으로 로그인했는지 확인하세요. 다른 계정으로 실습한다면 앱의 팀 멤버로 등록하세요.",
    "-2": "현재 앱의 템플릿 ID와 TITLE, TEXT 인자를 확인하세요. 링크가 있으면 제품 링크 관리의 웹 도메인도 확인하세요.",
    "missing_buttonless_template": "설정 화면 3단계에서 텍스트 템플릿을 만들고 ID를 저장하세요. 사진을 보내려면 이미지 템플릿 ID도 등록하세요.",
    "not_configured": "setup 명령으로 설정 화면을 열어 REST API 키와 클라이언트 시크릿을 저장하세요.",
    "login_required": "설정 화면의 카카오 로그인 버튼 또는 login 명령으로 계정을 연결하세요.",
    "delivery_unknown": "나와의 채팅에서 해당 메시지를 확인하세요. 같은 요청 ID를 유지해 중복 발송을 방지하세요.",
    "network_error": "인터넷 연결과 kauth.kakao.com, kapi.kakao.com 접속을 확인한 뒤 다시 시도하세요.",
    "port_in_use": "열려 있는 설정 창을 먼저 확인하세요. setup은 사용 중인 포트를 피해 새 콜백 주소를 표시합니다. 새 주소를 카카오 앱에 등록하고 앱 설정을 저장하세요.",
    "windows_required": "Windows PowerShell에서 실행하세요. WSL에서는 Windows의 py.exe로 이 스크립트를 실행하세요.",
}


def error_payload(exc):
    return {"ok": False, "error": exc.code, "message": str(exc), "http_status": exc.status,
            "action": ERROR_HELP.get(exc.code, "")}


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


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
            value = json.loads(dpapi(self.path.read_bytes(), decrypt=True).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError()
            return value
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

    def backup(self):
        if self.path.exists():
            destination = self.directory / ("profile-backup-" + uuid.uuid4().hex + ".dpapi")
            with destination.open("xb") as handle:
                handle.write(self.path.read_bytes())
            return destination

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
    if not isinstance(value, dict):
        raise KakaoError("invalid_config", "앱 설정은 JSON 객체로 입력하세요.")
    client_id = str(value.get("client_id", "")).strip()
    if not client_id or "본인" in client_id:
        raise KakaoError("invalid_config", "실제 REST API 키를 입력하세요.")
    uri = str(value.get("redirect_uri") or DEFAULT_REDIRECT)
    parsed = urllib.parse.urlsplit(uri)
    if (parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1")
            or not parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.path):
        raise KakaoError("invalid_redirect", "로컬 http 콜백 주소에 포트와 경로가 필요합니다.")
    default_url = str(value.get("default_url") or "").strip()
    return {"client_id": client_id, "client_secret": str(value.get("client_secret", "")).strip(),
            "redirect_uri": uri, "default_url": validate_url(default_url) if default_url else ""}


def update_config(state, value):
    """Keep same-app state; credentials and templates belong to the app key."""
    if not isinstance(value, dict):
        raise KakaoError("invalid_config", "앱 설정은 JSON 객체로 입력하세요.")
    previous = state.get("config", {})
    if previous and value.get("client_id", previous["client_id"]) != previous["client_id"] and "client_secret" not in value:
        raise KakaoError("invalid_config", "다른 앱으로 교체할 때 새 앱의 클라이언트 시크릿도 입력하세요. 실제로 비활성화했다면 빈 문자열을 지정하세요.")
    config = validate_config({**previous, **value})
    changed_app = bool(previous) and previous.get("client_id") != config["client_id"]
    if changed_app:
        state.pop("tokens", None)
        state.pop("messaging", None)
        state.pop("receipts", None)
        state.pop("setup_delivery", None)
    state["config"] = config
    return changed_app


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_form(url, data, token=None):
    headers = {"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, urllib.parse.urlencode(data).encode("utf-8"), headers)
    return api_request(request)


def get_api(url, token):
    return api_request(urllib.request.Request(url, headers={"Authorization": "Bearer " + token}))


def api_request(request):
    url = request.full_url
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
        raise KakaoError(code or "api_error", ERROR_HELP.get(code, "카카오 API가 요청을 거절했습니다. 오류 코드에 맞춰 앱 설정을 확인하세요."), status)
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


def validate_messaging(value, previous=None):
    allowed = {"registered_web_origins", "buttonless_text_template_id", "buttonless_image_template_id", "templates"}
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
        elif key == "templates":
            if not isinstance(item, dict) or len(item) > 30:
                raise KakaoError("invalid_messaging", "저장한 템플릿은 이름과 메시지 구성으로 최대 30개 등록하세요.")
            clean[key] = {}
            for name, spec in item.items():
                if not isinstance(name, str) or not name.strip() or name != name.strip() or len(name) > 40 or name in BUILTIN_TEMPLATES:
                    raise KakaoError("invalid_messaging", "템플릿 이름은 기본 이름과 다른 1~40자로 입력하세요.")
                if not isinstance(spec, dict) or set(spec) - MESSAGE_FIELDS:
                    raise KakaoError("invalid_message", "저장할 템플릿의 메시지 구성을 확인하세요.")
                clean[key][name] = spec
        else:
            if isinstance(item, bool) or not re.fullmatch(r"[1-9][0-9]*", str(item)):
                raise KakaoError("invalid_messaging", "사용자 정의 템플릿 ID는 양의 정수여야 합니다.")
            clean[key] = str(item)
    if "templates" in clean:
        settings = {"buttonless_text_template_id": "1", "buttonless_image_template_id": "1", **(previous or {}), **clean}
        for spec in clean["templates"].values():
            plan_message(spec, settings)
    return clean


def resolve_message(spec, settings):
    if not isinstance(spec, dict):
        raise KakaoError("invalid_message", "메시지는 JSON 객체로 입력하세요.")
    name = spec.get("template")
    if name is None:
        return spec
    library = {**BUILTIN_TEMPLATES, **settings.get("templates", {})}
    if not isinstance(name, str) or name not in library:
        raise KakaoError("missing_template", "templates 명령으로 이름을 확인하고 전송할 템플릿을 선택하세요.")
    merged = {**library[name], **{k: v for k, v in spec.items() if k != "template"}}
    if "buttons" in spec and "button_count" not in spec:
        merged.pop("button_count", None)
    if "actions" in spec and "buttons" not in spec:
        merged.pop("buttons", None)
    if name in BUILTIN_TEMPLATES and name.startswith("사진") and not merged.get("image_url"):
        raise KakaoError("invalid_image", "사진 템플릿에는 image_url로 실제 사진 주소를 입력하세요.")
    return merged


def template_catalog(settings):
    return [{"name": name, "builtin": name in BUILTIN_TEMPLATES, "message": spec}
            for name, spec in {**BUILTIN_TEMPLATES, **settings.get("templates", {})}.items()]


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
    spec = resolve_message(spec, settings)
    if not isinstance(spec, dict) or set(spec) - MESSAGE_FIELDS:
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
    custom_id = spec.get("template_id")
    if custom_id is not None and (isinstance(custom_id, bool) or not re.fullmatch(r"[1-9][0-9]*", str(custom_id))):
        raise KakaoError("invalid_message", "카카오 템플릿 ID는 양의 정수로 입력하세요.")
    if not buttons or custom_id:
        key = "buttonless_image_template_id" if image_url else "buttonless_text_template_id"
        template_id = custom_id or settings.get(key)
        if not template_id:
            raise KakaoError("missing_buttonless_template", "버튼 없는 메시지용 템플릿이 등록되지 않았습니다. references/templates.md의 설정 절차를 확인하세요.")
        if dimensions:
            raise KakaoError("custom_image_dimensions", "버튼 없는 이미지의 크기·비율은 카카오 사용자 정의 템플릿에서 설정합니다. 픽셀 옵션을 생략하세요.")
        args = {"TITLE": title, "TEXT": text}
        if image_url:
            args["IMAGE"] = image_url
        for index, button in enumerate(buttons, 1):
            args[f"BUTTON{index}"] = button["title"]
            for prefix, target in (("", button["link"]["web_url"]), ("MOBILE_", button["link"]["mobile_web_url"])):
                origin = url_origin(target)
                parsed = urllib.parse.urlsplit(target)
                path = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, parsed.fragment))
                args[f"{prefix}URL{index}"] = target
                args[f"{prefix}DOMAIN{index}"] = origin
                args[f"{prefix}PATH{index}"] = path
        preview["layout"] = "buttonless_image" if image_url else "buttonless_text"
        if custom_id:
            preview["layout"] = "custom"
            preview["template_id"] = str(custom_id)
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


def authorization_url(config, nonce):
    return AUTH_URL + "?" + urllib.parse.urlencode({"client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"], "response_type": "code", "scope": "talk_message", "state": nonce})


def exchange_code(state, store, code):
    config = state["config"]
    params = {"grant_type": "authorization_code", "client_id": config["client_id"],
              "redirect_uri": config["redirect_uri"], "code": code}
    if config.get("client_secret"):
        params["client_secret"] = config["client_secret"]
    state["tokens"] = merge_tokens({}, post_form(TOKEN_URL, params))
    store.save(state)


def connection_status(state):
    tokens = state.get("tokens", {})
    refresh_expired = bool(tokens.get("refresh_expires_at") and tokens["refresh_expires_at"] <= time.time())
    authenticated = bool(tokens.get("refresh_token")) and not refresh_expired
    configured = bool(state.get("config"))
    messaging = state.get("messaging", {})
    template = bool(messaging.get("buttonless_text_template_id"))
    next_step = "configure" if not configured else "login" if not authenticated else "text_template" if not template else "send"
    return {"ok": True, "configured": configured, "authenticated": authenticated,
            "access_token_expired": bool(tokens.get("access_token")) and tokens.get("expires_at", 0) <= time.time(),
            "refresh_token_expired": refresh_expired, "messaging": messaging,
            "redirect_uri": state.get("config", {}).get("redirect_uri", DEFAULT_REDIRECT),
            "client_secret_saved": bool(state.get("config", {}).get("client_secret")),
            "ready_to_send_text": configured and authenticated and template, "next_step": next_step}


def doctor(store, online=False):
    windows = os.name == "nt"
    python_ok = sys.version_info >= (3, 10)
    checks = [{"name": "windows", "ok": windows, "action": "Windows PowerShell에서 setup.ps1을 실행하세요."},
              {"name": "python", "ok": python_ok, "version": sys.version.split()[0],
               "action": "Python 3.10 이상을 설치하세요. setup.ps1이 설치 경로를 안내합니다."}]
    if not windows or not python_ok:
        return {"ok": False, "checks": checks, "next_step": "environment"}
    state = store.load()
    result = connection_status(state)
    checks.extend([
        {"name": "app", "ok": result["configured"], "action": ERROR_HELP["not_configured"]},
        {"name": "login", "ok": result["authenticated"], "action": ERROR_HELP["login_required"]},
        {"name": "text_template", "ok": bool(state.get("messaging", {}).get("buttonless_text_template_id")),
         "action": ERROR_HELP["missing_buttonless_template"]},
    ])
    if online and result["configured"]:
        try:
            with store.locked():
                state = store.load()
                token = access_token(state, store)
                try:
                    response = get_api("https://kapi.kakao.com/v2/user/scopes?scopes=%5B%22talk_message%22%5D", token)
                except KakaoError as exc:
                    if exc.status != 401 or exc.code != "-401":
                        raise
                    response = get_api("https://kapi.kakao.com/v2/user/scopes?scopes=%5B%22talk_message%22%5D", access_token(state, store, force=True))
            granted = any(s.get("id") == "talk_message" and s.get("using") and s.get("agreed") for s in response.get("scopes", []))
            checks.append({"name": "talk_message", "ok": granted, "action": ERROR_HELP["-402"]})
        except KakaoError as exc:
            checks.append({"name": "server_login", "ok": False, **error_payload(exc)})
    result.update(ok=all(c["ok"] for c in checks), checks=checks, online=online)
    return result


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
                result["error"] = re.sub(r"[^a-zA-Z0-9_-]", "", query.get("error_code", query["error"])[0])[:64]
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

    auth_url = authorization_url(config, expected_state)
    try:
        server = http.server.HTTPServer(("127.0.0.1", uri.port), Handler)
    except OSError as exc:
        raise KakaoError("port_in_use", f"로그인 콜백 포트 {uri.port}를 열지 못했습니다.") from exc
    with server:
        server.timeout = 1
        emit({"step": "browser_login", "authorization_url": auth_url, "timeout_seconds": 300})
        if not no_browser:
            webbrowser.open(auth_url)
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if result.get("error"):
        raise KakaoError(result["error"], ERROR_HELP.get(result["error"], "카카오 로그인 화면의 오류 코드를 확인하세요."))
    if not result.get("code"):
        raise KakaoError("login_timeout", "5분 안에 콜백을 받지 못했습니다. 다시 login을 실행하세요.")
    exchange_code(state, store, result["code"])
    return {"ok": True, "authenticated": True, "message_sent": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="로컬 연결 상태만 확인")
    check = commands.add_parser("doctor", help="실행 환경과 연결 준비 확인")
    check.add_argument("--online", action="store_true", help="토큰 갱신 및 talk_message 동의 확인")
    setup = commands.add_parser("setup", help="브라우저에서 앱 연결부터 첫 발송까지 진행")
    setup.add_argument("--no-browser", action="store_true")
    setup.add_argument("--port", type=int)
    setup.add_argument("--redirect-uri", help="로컬 http 콜백 주소 (호스트, 포트와 경로)")
    messaging = commands.add_parser("messaging", help="비밀정보 없는 템플릿·등록 도메인 설정; 토큰 유지")
    messaging.add_argument("--from-file", type=Path)
    commands.add_parser("templates", help="선택 가능한 기본 템플릿과 저장한 템플릿 목록")
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
    send.add_argument("--template", help="templates 목록의 이름")
    args = parser.parse_args(argv)
    store = Store()
    if args.command == "doctor":
        result = doctor(store, args.online)
        emit(result)
        return 0 if result["ok"] else 2
    if args.command == "setup":
        if os.name != "nt":
            raise KakaoError("windows_required", ERROR_HELP["windows_required"])
        from kakao_setup import run_setup
        return run_setup(store, args.port, args.no_browser, args.redirect_uri)
    if args.command == "status":
        state = store.load()
        emit({**connection_status(state), "storage": str(store.path)})
        return 0
    if args.command == "templates":
        emit({"ok": True, "templates": template_catalog(store.load().get("messaging", {}))})
        return 0
    if args.command == "messaging":
        if not args.from_file:
            emit({"ok": True, "messaging": store.load().get("messaging", {})})
            return 0
        value = json.loads(args.from_file.read_text(encoding="utf-8-sig"))
        with store.locked():
            state = store.load()
            changes = validate_messaging(value, state.get("messaging", {}))
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
                config = {"client_id": getpass.getpass("REST API 키 (기존 값 유지: Enter): ") or state.get("config", {}).get("client_id", ""),
                          "redirect_uri": input(f"콜백 주소 [{state.get('config', {}).get('redirect_uri', DEFAULT_REDIRECT)}]: ").strip() or state.get("config", {}).get("redirect_uri", DEFAULT_REDIRECT)}
                secret = getpass.getpass("클라이언트 시크릿 (기존 값 유지: Enter, 비활성화: -): ")
                if secret:
                    config["client_secret"] = "" if secret == "-" else secret
            changed_app = update_config(state, config)
            if changed_app:
                store.backup()
            store.save(state)
            emit({**connection_status(state), "app_changed": changed_app, "next": connection_status(state)["next_step"]})
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
    if args.template:
        spec["template"] = args.template
    return plan_message(spec, settings)


if __name__ == "__main__":
    sys.modules["kakao_me"] = sys.modules[__name__]
    try:
        sys.exit(main())
    except KakaoError as exc:
        emit(error_payload(exc))
        sys.exit(2)
    except (OSError, ValueError) as exc:
        emit({"ok": False, "error": "local_error", "message": "로컬 설정·파일·포트를 확인하세요.", "type": type(exc).__name__})
        sys.exit(2)
