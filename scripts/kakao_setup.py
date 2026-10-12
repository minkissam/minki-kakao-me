"""Local browser setup. Secrets stay in the user's DPAPI profile."""
import http.server
import errno
import json
from pathlib import Path
import re
import secrets
import socket
import threading
import time
import urllib.parse
import webbrowser

import kakao_me as km


class SetupServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, store, redirect_uri):
        uri = urllib.parse.urlsplit(redirect_uri)
        super().__init__(("127.0.0.1", uri.port), SetupHandler)
        self.store = store
        actual_port = self.server_port
        self.redirect_uri = urllib.parse.urlunsplit((uri.scheme, f"{uri.hostname}:{actual_port}", uri.path, "", ""))
        self.callback_path = uri.path
        self.session = secrets.token_urlsafe(32)
        self.guard = threading.Lock()
        self.pending_login = None
        self.notice = None
        saved = store.load()
        delivery = saved.get("setup_delivery", {})
        self.send_id = delivery.get("request_id") or "setup-" + secrets.token_hex(16)
        self.last_text = delivery.get("text")
        self.last_signature = delivery.get("signature")
        self.delivery_unknown = saved.get("receipts", {}).get(self.send_id, {}).get("status") in ("unknown", "sending")
        self.stop_requested = False
        self.last_activity = time.monotonic()
        self.hosts = {f"localhost:{actual_port}", f"127.0.0.1:{actual_port}"}

    def status(self):
        result = km.connection_status(self.store.load())
        result.update(saved_redirect_uri=result["redirect_uri"], callback_changed=result["configured"] and result["redirect_uri"] != self.redirect_uri,
                      redirect_uri=self.redirect_uri, notice=self.notice, delivery_unknown=self.delivery_unknown,
                      last_text=self.last_text, templates=km.template_catalog(result["messaging"]))
        return result

    def action(self, route, data):
        if not isinstance(data, dict):
            raise km.KakaoError("invalid_request", "입력 값을 확인하세요.")
        if route == "/api/close":
            self.stop_requested = True
            return {"ok": True, "closed": True}
        if route == "/api/check":
            result = km.doctor(self.store, online=True)
            result["checks"] = [c for c in result["checks"] if c["name"] != "text_template"]
            result["ok"] = all(c["ok"] for c in result["checks"])
            self.notice = None
            return result
        if route == "/api/preview":
            plan = km.plan_message(data.get("message", {}), self.store.load().get("messaging", {}))
            return {"ok": True, "preview": plan["preview"]}
        with self.store.locked():
            state = self.store.load()
            if route == "/api/config":
                value = {k: data[k] for k in ("client_id", "client_secret") if k in data}
                value["redirect_uri"] = self.redirect_uri
                # An empty field preserves existing keys; a new app must supply its own secret.
                if not value.get("client_id"):
                    value.pop("client_id", None)
                changed = bool(state.get("config")) and value.get("client_id", state["config"]["client_id"]) != state["config"]["client_id"]
                if changed and not data.get("replace_app"):
                    raise km.KakaoError("app_change_confirmation", "다른 앱으로 교체하려면 앱 교체 항목을 선택하세요. 새 앱은 로그인과 템플릿 연결을 다시 진행합니다.")
                if not value.get("client_secret") and not data.get("secret_disabled"):
                    value.pop("client_secret", None)
                    if changed or not state.get("config"):
                        raise km.KakaoError("invalid_config", "같은 앱의 클라이언트 시크릿을 입력하세요. 실제로 비활성화했다면 해당 항목을 선택하세요.")
                if data.get("secret_disabled"):
                    value["client_secret"] = ""
                clean = km.validate_config({**state.get("config", {}), **value})
                if changed:
                    self.store.backup()
                km.update_config(state, clean)
                self.store.save(state)
                if changed:
                    self.send_id = "setup-" + secrets.token_hex(16)
                    self.last_text = None
                    self.last_signature = None
                    self.delivery_unknown = False
                self.pending_login = None
                self.notice = None
            elif route == "/api/login":
                if not state.get("config"):
                    raise km.KakaoError("not_configured", "앱 키를 먼저 저장하세요.")
                if state["config"]["redirect_uri"] != self.redirect_uri:
                    raise km.KakaoError("invalid_redirect", "이 설정 화면의 콜백 주소로 앱 설정을 저장하세요.")
                nonce = secrets.token_urlsafe(32)
                self.pending_login = {"state": nonce, "at": time.monotonic(), "config": dict(state["config"])}
                return {"ok": True, "authorization_url": km.authorization_url(state["config"], nonce)}
            elif route == "/api/messaging":
                clean = km.validate_messaging(data, state.get("messaging", {}))
                state.setdefault("messaging", {}).update(clean)
                self.store.save(state)
                self.notice = None
            elif route == "/api/template":
                name = data.get("name")
                if not isinstance(name, str):
                    raise km.KakaoError("invalid_messaging", "템플릿 이름을 입력하세요.")
                templates = dict(state.get("messaging", {}).get("templates", {}))
                if data.get("delete"):
                    if name not in templates:
                        raise km.KakaoError("missing_template", "삭제할 저장 템플릿을 선택하세요.")
                    del templates[name]
                else:
                    spec = km.resolve_message(data.get("message", {}), state.get("messaging", {}))
                    km.validate_messaging({"templates": {name: spec}}, state.get("messaging", {}))
                    templates[name] = spec
                clean = km.validate_messaging({"templates": templates}, state.get("messaging", {}))
                state.setdefault("messaging", {}).update(clean)
                self.store.save(state)
                self.notice = None
            elif route == "/api/send":
                if self.delivery_unknown:
                    raise km.KakaoError("delivery_unknown", "앞선 메시지의 전달 여부를 나와의 채팅에서 확인하세요.")
                if not km.connection_status(state)["authenticated"]:
                    raise km.KakaoError("setup_incomplete", "앱 저장과 카카오 로그인을 먼저 완료하세요.")
                spec = data.get("message", {"text": data.get("text", ""), "buttons": []})
                plan = km.plan_message(spec, state.get("messaging", {}))
                text = plan["preview"]["text"]
                signature = km.hashlib.sha256(json.dumps({"endpoint": plan["endpoint"], "form": plan["form"]}, sort_keys=True).encode()).hexdigest()
                if self.last_text is not None and (self.last_signature != signature if self.last_signature else self.last_text != text):
                    self.send_id = "setup-" + secrets.token_hex(16)
                self.last_text = text
                self.last_signature = signature
                state["setup_delivery"] = {"request_id": self.send_id, "text": text, "signature": signature}
                self.store.save(state)
                try:
                    result = km.send_plan(state, self.store, plan, self.send_id)
                except km.KakaoError as exc:
                    if exc.code == "delivery_unknown":
                        self.delivery_unknown = True
                    raise
                self.notice = {"ok": True, "message": "같은 메시지의 발송 기록을 확인했습니다." if result.get("duplicate_skipped") else "카카오 API 발송 성공. 나와의 채팅에서 메시지를 확인하세요."}
                return {**result, "preview": plan["preview"]}
            else:
                raise km.KakaoError("invalid_request", "설정 화면에서 다시 실행하세요.")
        return self.status()

    def callback(self, query):
        pending = self.pending_login
        if not pending or time.monotonic() - pending["at"] > 300 or not secrets.compare_digest(query.get("state", [""])[0], pending["state"]):
            raise km.KakaoError("invalid_callback", "카카오 로그인 버튼으로 다시 시작하세요. 로그인 응답은 5분 동안 유효합니다.")
        self.pending_login = None
        if "error" in query:
            code = re.sub(r"[^a-zA-Z0-9_-]", "", query.get("error_code", query["error"])[0])[:64]
            raise km.KakaoError(code, km.ERROR_HELP.get(code, "카카오 로그인 화면의 오류 코드를 확인하세요."))
        code = query.get("code", [""])[0]
        if not code:
            raise km.KakaoError("invalid_callback", "인가 코드가 없습니다. 카카오 로그인을 다시 시작하세요.")
        with self.store.locked():
            state = self.store.load()
            if state.get("config") != pending["config"]:
                raise km.KakaoError("config_changed", "앱 설정이 변경되었습니다. 카카오 로그인을 다시 시작하세요.")
            km.exchange_code(state, self.store, code)
        self.notice = None


class SetupHandler(http.server.BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass

    def trusted_host(self):
        return self.headers.get("Host") in self.server.hosts

    def respond(self, status, value, html=False):
        body = value.encode("utf-8") if html else json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8" if html else "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", f"default-src 'none'; script-src 'nonce-{self.server.session}'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.trusted_host():
            self.respond(403, {"ok": False, "message": "로컬 설정 주소를 사용하세요."})
            return
        parsed = urllib.parse.urlsplit(self.path)
        with self.server.guard:
            if parsed.path == self.server.callback_path:
                try:
                    self.server.callback(urllib.parse.parse_qs(parsed.query))
                except km.KakaoError as exc:
                    self.server.notice = km.error_payload(exc)
                except (OSError, ValueError):
                    self.server.notice = {"ok": False, "message": "연결 응답을 저장하지 못했습니다. 설정 화면에서 다시 로그인하세요."}
                self.send_response(303)
                self.send_header("Location", "/" + self.server.session)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif parsed.path == "/" + self.server.session:
                page = (Path(__file__).parent / "setup.html").read_text(encoding="utf-8")
                self.respond(200, page.replace("__SESSION__", self.server.session), html=True)
            elif parsed.path == "/api/status" and secrets.compare_digest(self.headers.get("X-Setup-Token", ""), self.server.session):
                self.respond(200, self.server.status())
            else:
                self.respond(404, {"ok": False, "message": "터미널에 표시된 설정 주소를 여세요."})
            self.server.last_activity = time.monotonic()

    def do_POST(self):
        origin = self.headers.get("Origin", "")
        if not self.trusted_host() or origin not in {"http://" + host for host in self.server.hosts} or not secrets.compare_digest(self.headers.get("X-Setup-Token", ""), self.server.session):
            self.respond(403, {"ok": False, "message": "설정 창을 다시 여세요."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise km.KakaoError("invalid_request", "설정 입력 크기를 확인하세요.")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            with self.server.guard:
                result = self.server.action(urllib.parse.urlsplit(self.path).path, data)
                self.server.last_activity = time.monotonic()
            self.respond(200, result)
        except km.KakaoError as exc:
            self.respond(400, km.error_payload(exc))
        except (ValueError, OSError, UnicodeError):
            self.respond(400, {"ok": False, "error": "local_error", "message": "입력 내용과 저장 경로를 확인하세요."})


def create_setup_server(store, port=None, redirect_uri=None):
    current = store.load().get("config", {}).get("redirect_uri", km.DEFAULT_REDIRECT)
    if redirect_uri is not None:
        if port is not None:
            raise km.KakaoError("invalid_redirect", "--port와 --redirect-uri 중 하나를 지정하세요.")
        current = km.validate_config({"client_id": "check", "redirect_uri": redirect_uri})["redirect_uri"]
    if port is not None:
        if not 0 <= port <= 65535:
            raise km.KakaoError("invalid_redirect", "포트는 0~65535로 입력하세요. 0은 사용 가능한 포트를 자동 선택합니다.")
        previous_uri = urllib.parse.urlsplit(current)
        current = f"http://{previous_uri.hostname}:{port}{previous_uri.path}"
    try:
        return SetupServer(store, current)
    except OSError as exc:
        if exc.errno in (errno.EADDRINUSE, 10048) or getattr(exc, "winerror", None) == 10048:
            uri = urllib.parse.urlsplit(current)
            try:
                return SetupServer(store, f"http://{uri.hostname}:0{uri.path}")
            except OSError:
                pass
        raise km.KakaoError("port_in_use", f"설정 포트 {urllib.parse.urlsplit(current).port}를 열지 못했습니다.") from exc


def run_setup(store, port=None, no_browser=False, redirect_uri=None):
    server = create_setup_server(store, port, redirect_uri)
    server.timeout = 1
    uri = urllib.parse.urlsplit(server.redirect_uri)
    address = f"http://{uri.hostname}:{server.server_port}/{server.session}"
    km.emit({"ok": True, "step": "setup_browser", "setup_url": address, "redirect_uri": server.redirect_uri,
             "callback_changed": server.status()["callback_changed"],
             "message": "이 주소에서 앱 연결을 진행하세요. 종료 버튼 또는 Ctrl+C로 닫습니다.", "idle_timeout_seconds": 1800})
    if not no_browser:
        webbrowser.open(address)
    try:
        while not server.stop_requested and time.monotonic() - server.last_activity < 1800:
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
