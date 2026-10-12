# 연결 명령과 오류 해결

최초 연결은 AI가 [브라우저 연결 절차](agent-setup.md)를 따라 진행한다. 앱 생성과 설정 클릭, 템플릿 등록은 브라우저 도구로 수행하고, 필요한 로그인과 인증만 사용자에게 요청한다.

## 브라우저 설정 실행

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <저장소>\setup.ps1 -NoBrowser
```

또는 확인한 Python으로 실행한다.

```powershell
py -3 -B -X utf8 <저장소>\scripts\kakao_me.py setup --no-browser
```

출력의 `setup_url`을 오른쪽 브라우저 또는 연결한 Chrome에서 연다. 프로세스는 설정이 끝날 때까지 유지한다. 콜백 주소는 실행 결과의 `redirect_uri`와 화면의 `앱에 등록할 콜백 주소`를 기준으로 삼는다. 저장한 주소가 있으면 호스트, 포트와 경로를 재사용한다. 최초 기본 주소는 `http://localhost:8765/callback`이며, 해당 포트가 사용 중이면 사용 가능한 포트를 자동 선택한다.

주소가 바뀌면 `callback_changed: true`와 화면의 안내가 표시된다. AI가 현재 앱에 새 주소를 추가하고 로컬 `앱 설정 저장`을 누른 뒤 로그인한다. 같은 앱의 기존 토큰과 템플릿은 유지된다. 세션마다 달라지는 `setup_url`은 로컬 화면 주소이며, 카카오 앱에는 `redirect_uri`를 등록한다. 이미 열린 설정 화면이 있으면 먼저 재사용한다.

호스트와 경로를 포함한 주소를 지정할 수도 있다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <저장소>\setup.ps1 -NoBrowser -RedirectUri 'http://127.0.0.1:18765/oauth/kakao-return'
py -3 -B -X utf8 <저장소>\scripts\kakao_me.py setup --no-browser --redirect-uri http://127.0.0.1:18765/oauth/kakao-return
```

`-Port 0` 또는 `--port 0`은 사용 가능한 포트를 선택한다. 포트만 지정하면 저장한 호스트와 경로를 유지한다. `Port`와 `RedirectUri` 중 하나를 지정한다. 로컬 OAuth는 같은 PC의 `localhost` 또는 `127.0.0.1`에서 실행한다.

## 앱 설정의 필수값

- 카카오 로그인 사용 설정 ON
- 카카오 로그인 동의항목: 카카오톡 메시지 전송 `talk_message`, 선택 동의 또는 이용 중 동의
- 앱 > 플랫폼 키 > REST API 키: 로컬 화면과 같은 콜백 주소
- 같은 앱의 REST API 키와 클라이언트 시크릿. 새 키는 시크릿이 기본 활성화된다.
- 버튼 없는 첫 발송: 현재 앱의 텍스트 사용자 정의 템플릿 ID

링크 버튼을 사용할 때 제품 링크 관리에 목적지 도메인을 등록한다. 사진을 사용할 때 이미지용 사용자 정의 템플릿을 추가한다. 구성은 [templates.md](templates.md)를 따른다.

## 상태 확인

```powershell
py -3 -B -X utf8 <저장소>\scripts\kakao_me.py status
py -3 -B -X utf8 <저장소>\scripts\kakao_me.py doctor
py -3 -B -X utf8 <저장소>\scripts\kakao_me.py doctor --online
```

`next_step`은 `configure`, `login`, `text_template`, `send` 순서로 남은 단계를 표시한다. `ready_to_send_text`는 저장한 연결과 텍스트 템플릿의 준비 여부다. `doctor --online`은 필요한 토큰 갱신 후 카카오 서버의 `talk_message` 동의를 확인한다. 실제 템플릿 내용과 발송 결과는 첫 발송에서 확인한다.

## 터미널이나 로컬 파일로 설정

브라우저 도구에서 입력을 진행하는 경로가 기본이다. 사용자가 터미널 설정을 선택했거나 로컬 설정 파일이 있으면 다음 명령도 사용할 수 있다.

```powershell
py -3 -B -X utf8 <저장소>\scripts\kakao_me.py configure
py -3 -B -X utf8 <저장소>\scripts\kakao_me.py configure --from-file <설정.local.json>
py -3 -B -X utf8 <저장소>\scripts\kakao_me.py login
```

로컬 설정 JSON:

```json
{
  "client_id": "본인 앱의 REST API 키",
  "client_secret": "본인 앱의 클라이언트 시크릿",
  "redirect_uri": "http://localhost:8765/callback"
}
```

같은 앱의 부분 갱신은 기존 토큰, 템플릿, 도메인과 기록을 유지한다. 입력을 생략한 시크릿은 저장한 값을 유지한다. 시크릿을 실제로 비활성화한 경우 JSON에 빈 문자열을 지정하거나 대화형 입력에서 `-`를 입력한다. 기본 URL은 선택 항목이며 과거 설정과의 호환용이다.

다른 앱 키로 교체할 때 새 앱의 시크릿도 함께 입력한다. 기존 암호화 프로필을 같은 개인 폴더에 `profile-backup-<고유값>.dpapi`로 저장하고 새 앱의 로그인과 템플릿을 다시 연결한다. 인증정보가 들어간 파일은 로컬에 보관한다.

## 오류 해결

명령의 JSON 결과에 `error`, `message`, `action`이 출력된다. 로컬 설정 화면도 오류와 해결 행동을 표시한다.

| 오류 | 복구 |
| --- | --- |
| `not_configured` | 설정 화면에서 같은 앱의 REST API 키와 시크릿 저장 |
| `login_required`, `KOE322`, `invalid_grant` | 카카오 로그인을 다시 시작 |
| `KOE004` | 카카오 로그인 사용 설정 ON |
| `KOE006`, `KOE303` | 카카오 등록 URI와 표시된 콜백 주소의 호스트, 포트, 경로 일치 |
| `KOE008`, `KOE101` | REST API 키를 다시 확인 |
| `KOE010`, `invalid_client` | 같은 앱의 REST API 키와 시크릿 확인 후 다시 로그인 |
| `KOE205`, `-3`, `-402` | talk_message 활성화 후 로그인과 전송 동의 |
| `KOE320` | 새 로그인으로 인가 코드 발급 |
| `port_in_use` | 기존 설정 창 확인. 자동 선택한 포트도 열 수 없으면 로컬 포트 접근 상태를 확인하고 다시 실행 |
| `missing_buttonless_template` | 현재 앱의 템플릿을 등록하고 해당 ID 저장 |
| `unregistered_domain` | 앱 제품 링크 관리에 등록한 도메인을 로컬 설정에도 반영 |
| `network_error` | 인터넷과 카카오 인증/API 서버 접속 확인 |
| `delivery_unknown` | 나와의 채팅에서 앞선 메시지 확인, 같은 request ID 유지 |
| `credential_store_error` | 원래 Windows 사용자 계정과 KAKAO_ME_CONFIG_DIR 확인. 원본 프로필 보존 |

브라우저 확장 프로그램과 플러그인 연결 실패는 [브라우저 도구 연결](agent-setup.md#2-브라우저-도구-연결) 절차로 해결한다. 에이전트가 공식 설치/연결 화면을 열고 필요한 행동을 요청한 뒤 중단된 단계에서 재개한다.

## 공식 문서

- [카카오 로그인 설정](https://developers.kakao.com/docs/ko/kakaologin/prerequisite)
- [카카오 로그인 오류 코드](https://developers.kakao.com/docs/ko/kakaologin/trouble-shooting)
- [동의 내역 확인](https://developers.kakao.com/docs/ko/kakaologin/rest-api#retrieve-consent-details)
- [나에게 보내기 REST API](https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api)
