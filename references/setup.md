# 최초 연결과 사용

## 1. 카카오 앱 설정

카카오디벨로퍼스에서 본인 앱을 만들고 카카오 로그인을 활성화한다.

- 동의항목: **카카오톡 메시지 전송 `talk_message`**를 선택 동의 또는 이용 중 동의로 설정한다.
- REST API 키의 Redirect URI: `http://localhost:8765/callback`
- 제품 링크의 웹 도메인: 메시지 버튼으로 열 주소의 도메인. 예를 들어 시트를 열려면 `https://docs.google.com`을 등록한다.
- 준비할 값: REST API 키, Client secret, 제품 링크의 기본 URL. 기본 URL은 예전 설정과의 호환을 위해 저장하며 메시지 버튼에 자동 삽입하지 않는다.
- Client secret이 활성화되어 있으면 실제 값을 입력한다. 현재 새 REST API 키에는 기본 활성화될 수 있다. 임의의 문자열을 넣지 않는다.

이 스킬은 카카오 공식 API를 직접 호출하며 MCP 서버가 필요하지 않다. 이메일·OIDC 권한은 요청하지 않는다. 앱 소유자의 개인 사용 기준이며, 다른 사람에게 서비스를 배포하면 별도 권한·운영 조건을 확인한다.

## 2. 로컬 설정

설치한 스킬의 `scripts/kakao_me.py`를 사용자 PowerShell에서 실행한다.

```powershell
py -3 -X utf8 "$env:USERPROFILE\.codex\skills\minki-kakao-me\scripts\kakao_me.py" configure
py -3 -X utf8 "$env:USERPROFILE\.codex\skills\minki-kakao-me\scripts\kakao_me.py" login
```

`configure`는 키와 시크릿을 화면에 표시하지 않고 입력받는다. 기본 링크는 실제 사용하려는 시트나 웹페이지 주소로 지정한다. `login`은 브라우저를 열고 로컬 콜백을 최대 5분 기다린다. 브라우저에서 본인의 카카오 계정으로 로그인하고 메시지 전송에 동의한다. 이 단계는 메시지를 보내지 않는다.

다른 경로에 설치했다면 명령 경로를 바꾼다. `CODEX_HOME`을 별도로 쓰는 환경에서는 그 아래 `skills` 경로를 사용한다.

Codex에 설정을 맡길 때는 아래 형식의 JSON을 로컬 파일에 직접 저장하고 **경로만** 알려준다. 실제 값을 소스 묶음에 넣지 않는다.

```json
{
  "client_id": "본인 앱의 REST API 키",
  "client_secret": "본인 앱의 Client secret, 비활성화한 경우 빈 문자열",
  "redirect_uri": "http://localhost:8765/callback",
  "default_url": "https://docs.google.com/spreadsheets/d/본인_시트_ID/edit"
}
```

스크립트는 `configure --from-file <파일>`로 가져올 수 있다. 원본 설정 JSON은 자동 삭제하지 않는다. 설정을 다시 가져오면 기존 로컬 토큰은 지워지므로 다시 로그인한다. 공유할 파일 묶음에는 원본 설정 JSON을 포함하지 않는다.

## 3. Codex에서 사용

```text
$minki-kakao-me 연결 상태 확인해줘.
$minki-kakao-me 나에게 "작업 끝났어"라고 보내줘.
이 작업이 끝나면 $minki-kakao-me로 결과를 짧게 보내줘.
```

버튼 0~2개와 사진을 선택할 수 있다. 사용자가 따로 지정하지 않으면 Codex가 내용에 맞춰 구성한다. 링크 없는 짧은 알림은 버튼을 생략한다. 버튼 없는 메시지용 템플릿 등록과 도메인 설정은 [메시지 명세와 템플릿](templates.md)을 따른다. 200자 초과 본문은 스크립트가 거절한다. 발송 전 미리보기와 실제 발송은 별도 명령이다.

## 문제 해결

| 상태 | 할 일 |
| --- | --- |
| `not_configured` | `configure` 실행 |
| `login_required` / `invalid_grant` | `login`으로 재연결 |
| 카카오 `-402` | 앱의 `talk_message` 설정 후 다시 로그인·동의 |
| 카카오 `KOE006` | 등록한 Redirect URI와 로컬 설정이 정확히 같은지 확인 |
| 카카오 `KOE010` | 활성화된 Client secret 확인 |
| 링크 도메인 오류 | 제품 링크의 웹 도메인에 URL의 출처 등록 |
| `missing_buttonless_template` | `templates.md`의 텍스트/이미지용 템플릿 등록 후 `messaging` 설정 |
| `delivery_unknown` | 나와의 채팅을 확인하고 재발송 여부 판단 |
| 포트 사용 중 | 8765를 사용하는 프로그램 확인; 포트 변경 시 카카오 등록 URI도 함께 변경 |

## 저장 방식과 검증 범위

기존 `kakao-me`에서 이름을 변경한 경우에도 인증 저장 위치는 `%LOCALAPPDATA%\Codex\kakao-me`를 유지한다. 따라서 기존 계정 연결과 메시지 전송 기록을 그대로 사용한다. `KAKAO_ME_CONFIG_DIR` 환경변수도 계속 지원한다.

Windows DPAPI는 같은 Windows 사용자 권한으로 복호화할 수 있다. 같은 계정으로 실행되는 프로그램까지 격리하는 보관소는 아니다. 설정과 토큰은 스킬 소스와 분리되어 있어 소스 묶음만 전달하면 인증정보가 따라가지 않는다.

설치 시 코드·오프라인 테스트를 검증했다. 실제 계정 로그인, 카카오 전송, 휴대전화 수신은 연결 후 별도로 확인해야 한다.

## 공식 근거 (2026-09-30 확인)

- [나에게 보내기 REST API](https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api)
- [카카오 로그인·토큰 갱신](https://developers.kakao.com/docs/ko/kakaologin/rest-api)
- [기본 텍스트 템플릿](https://developers.kakao.com/docs/ko/message-template/default)
- [Codex 스킬](https://learn.chatgpt.com/docs/build-skills)
