# minki-kakao-me

**Codex와 Claude Code가 내 카카오 앱을 연결하고 카카오톡 나와의 채팅으로 알림을 보내는 Windows 스킬.**

## AI에게 이렇게 요청하세요

```text
https://github.com/minkissam/minki-kakao-me 를 가져와서 내 카카오톡 나에게 보내기를 연결해 줘.
AGENTS.md와 SKILL.md를 읽고 브라우저나 computer use로 앱 설정과 템플릿 등록까지 진행해 줘.
브라우저 연결에 필요한 확장 프로그램이나 플러그인이 있으면 설치 화면을 준비하고 필요한 행동을 알려 줘.
내가 직접 해야 하는 로그인과 인증에서만 요청하고, 끝나면 첫 메시지로 "연결 완료"를 보내 줘.
```

AI가 실행 환경과 기존 연결을 확인하고, 브라우저 도구로 카카오 앱 생성, 로그인 설정, 동의항목, 템플릿과 로컬 연결을 진행합니다. 사용자는 필요한 로그인, 추가 인증과 브라우저 권한 허용을 처리합니다.

Codex는 `AGENTS.md`, Claude Code는 `CLAUDE.md`에서 같은 [브라우저 연결 절차](references/agent-setup.md)를 읽습니다. 저장소를 로컬 작업 폴더로 열어 바로 사용할 수 있습니다.

## 연결 흐름

1. AI가 Windows, Python과 기존 연결 상태를 확인합니다.
2. 사용할 브라우저를 연결합니다. 필요한 확장 프로그램과 플러그인은 공식 설치 화면에서 준비합니다.
3. 카카오 앱을 만들거나 재사용하고, 카카오 로그인과 메시지 전송 동의를 설정합니다.
4. 로컬 브라우저 설정 화면에서 앱 키를 저장하고 카카오 계정을 연결합니다.
5. 템플릿을 연결하고 원하는 알림, 사진과 링크 버튼 구성을 선택해 첫 메시지를 보냅니다.

새 REST API 키의 클라이언트 시크릿은 기본 활성화되어 있습니다. AI가 같은 앱의 키와 시크릿을 로컬 설정 화면에 전달합니다. 같은 앱의 설정을 다시 저장하면 기존 토큰과 템플릿, 등록 도메인과 전송 기록을 유지합니다. 다른 앱으로 교체하면 기존 암호화 프로필을 백업하고 새 앱으로 연결합니다.

## 실행

Windows와 Python 3.10 이상을 사용합니다. 실행 코드의 외부 Python 패키지 의존성은 없습니다.

저장소를 가져와 PowerShell에서 실행합니다.

```powershell
git clone https://github.com/minkissam/minki-kakao-me.git
cd minki-kakao-me
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

이미 저장소가 있으면 현재 변경 사항을 확인하고 해당 폴더에서 업데이트합니다. `ExecutionPolicy Bypass`는 이 실행 프로세스에만 적용됩니다.

| 명령 | 동작 |
| --- | --- |
| `setup.ps1` | 사용 가능한 Python을 찾아 브라우저 연결 화면 실행 |
| `setup.ps1 -Check` | 환경과 현재 연결 준비 확인 |
| `setup.ps1 -NoBrowser` | 설정 서버를 실행하고 AI가 열 주소 출력 |
| `setup.ps1 -Port 8766` | 다른 포트에서 설정 실행, 등록할 콜백 주소 표시 |
| `setup.ps1 -Port 0` | 사용 가능한 포트를 자동 선택 |
| `setup.ps1 -RedirectUri 'http://127.0.0.1:18765/oauth/kakao-return'` | 호스트와 포트, 경로를 지정해 실행 |
| `kakao_me.py doctor --online` | 서버 인증과 `talk_message` 동의 확인, 필요 시 토큰 갱신 |
| `kakao_me.py templates` | 기본 선택지와 이름으로 저장한 템플릿 목록 |

설정 서버를 실행한 터미널은 연결 과정 동안 유지합니다. `설정 종료` 또는 Ctrl+C로 종료하며 진행 결과는 Windows 사용자 프로필에 저장됩니다.

콜백은 실행 결과의 `redirect_uri`를 그대로 등록합니다. 기존 주소를 재사용하고, 포트가 사용 중이면 새 포트를 선택합니다. 주소가 바뀌면 AI가 카카오 앱 등록과 로컬 저장을 갱신한 뒤 로그인합니다. 자세한 명령은 [콜백 주소 설정](references/setup.md#브라우저-설정-실행)을 참고합니다.

## 템플릿을 선택해 보내기

로컬 화면의 `전송할 템플릿`에서 다음 구성을 선택합니다.

| 선택지 | 입력 |
| --- | --- |
| 기본 알림 | 제목과 본문 |
| 사진 알림 | 제목, 본문과 사진 URL |
| 링크 버튼 1개 / 2개 | 본문과 버튼별 문구 및 링크 |
| 사진과 버튼 1개 / 2개 | 사진 URL과 버튼별 문구 및 링크 |

입력하면 미리보기의 본문과 버튼이 바뀝니다. `전송 구성 확인`으로 검증하고 `나에게 보내기`를 누릅니다. `이 구성을 내 템플릿으로 저장`에서 이름을 붙이면 제목, 본문, 사진과 버튼 링크를 다시 선택할 수 있습니다. 저장한 템플릿을 선택해 수정하거나 다른 이름으로 복제할 수 있습니다.

AI에게는 “주간 보고서 템플릿으로 이 결과를 보내 줘”라고 요청합니다. AI가 저장한 구성을 읽고 이번 본문과 필요한 링크를 반영합니다.

```powershell
py -3 -B -X utf8 scripts/kakao_me.py templates
py -3 -B -X utf8 scripts/kakao_me.py send --template '주간 보고서' --text '이번 주 보고서를 완성했습니다.' --request-id report-002 --dry-run
```

버튼 링크는 앱에 등록한 도메인을 사용합니다. 개별 카카오 템플릿도 이름과 ID로 연결할 수 있으며, AI가 해당 카드의 이미지와 버튼 개수, 인자를 맞춰 등록합니다. [템플릿 등록과 저장 형식](references/templates.md)을 참고합니다.

## 스킬로 계속 사용하기

이 폴더를 에이전트의 스킬 검색 경로에 설치하면 다음 요청으로 사용할 수 있습니다.

```text
$minki-kakao-me 작업이 끝났다고 버튼 없이 짧게 보내 줘.
$minki-kakao-me 보고서 열기 버튼 하나를 넣어서 보내 줘.
$minki-kakao-me 이 이미지 URL을 사진으로 넣고 버튼 없이 보내 줘.
```

Claude Code에서는 `/minki-kakao-me` 또는 자연어로 요청합니다. 영구 설치 위치는 에이전트의 현재 공식 스킬 안내와 작업공간 지침을 따릅니다. `CODEX_HOME`을 사용하는 환경에서는 해당 설정을 존중합니다. 기존 설치를 갱신할 때는 사용자 수정과 인증 프로필을 보존합니다.

## 지원하는 메시지

| 항목 | 지원 범위 |
| --- | --- |
| 본문 | 최대 200자 |
| 카드 제목 | 선택 사항, 최대 100자 |
| 링크 버튼 | 0~2개, 실제 목적지와 문구 지정 |
| 버튼 문구 | 1~10자 |
| 사진 | 카카오가 접근할 수 있는 이미지 URL |
| 미리보기 | 실제 발송 전 구성 검증 |
| 토큰 | 자동 갱신 |
| 전송 기록 | 요청 ID 기준 최근 100건, 같은 요청 중복 방지 |

사용자가 지정한 구성을 우선합니다. 버튼 없는 메시지는 등록한 사용자 정의 템플릿을 사용하고, 버튼 1~2개는 기본 템플릿을 사용합니다. 메시지 JSON과 템플릿의 상세 구성은 [메시지 명세](references/templates.md)를 참고합니다.

```powershell
py -3 -B -X utf8 scripts/kakao_me.py status
py -3 -B -X utf8 scripts/kakao_me.py doctor
py -3 -B -X utf8 scripts/kakao_me.py send --message-file message.local.json --request-id report-001 --dry-run
py -3 -B -X utf8 scripts/kakao_me.py send --message-file message.local.json --request-id report-001
```

```json
{"text":"자료 정리가 끝났습니다.","buttons":[]}
```

`--dry-run`은 입력 구성을 확인합니다. `sent: true`, `result_code: 0`은 카카오 API 발송 성공입니다. 타임아웃 등으로 `delivery_unknown`이 나오면 나와의 채팅을 확인하고 같은 요청 ID를 유지합니다.

## 인증정보 저장

앱 키와 시크릿, 토큰은 `%LOCALAPPDATA%\Codex\kakao-me\profile.dpapi`에 Windows DPAPI로 암호화해 저장합니다. 기존 `kakao-me` 연결도 이 경로를 유지하며 `KAKAO_ME_CONFIG_DIR`로 별도 경로를 사용할 수 있습니다. 앱을 교체할 때의 백업도 같은 개인 폴더에 암호화 상태로 저장합니다.

키와 프로필, 개인 메시지 기록은 공유 소스에 넣지 않습니다. 설치만 요청했다면 발송 준비까지 진행하고, 메시지는 사용자의 발송 요청에 따라 보냅니다.

## 파일 안내

| 파일 | 역할 |
| --- | --- |
| `AGENTS.md` / `CLAUDE.md` | 에이전트 공통 진입 지침 |
| `SKILL.md` | 연결과 메시지 구성 및 발송 계약 |
| `references/agent-setup.md` | 브라우저 연결 복구와 AI의 최초 설정 절차 |
| `references/setup.md` | 명령 사용과 오류 해결 |
| `references/templates.md` | 템플릿 등록과 메시지 JSON |
| `setup.ps1` | Python 찾기와 실행 |
| `scripts/kakao_me.py` | OAuth, 진단, 암호화 저장과 전송 |
| `scripts/kakao_setup.py` / `scripts/setup.html` | AI와 사용자가 조작하는 로컬 연결 화면 |

## 개발 확인

```powershell
py -3 -B -X utf8 -m unittest discover -s tests -v
```

기존 전송 검증과 최초 설정 검증은 임시 프로필과 가상 API 응답으로 실행합니다. GitHub Actions에서도 Windows에서 실행합니다.

## 공식 문서

- [카카오톡 메시지 REST API](https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api)
- [카카오 로그인 설정](https://developers.kakao.com/docs/ko/kakaologin/prerequisite)
- [사용자 정의 메시지 템플릿](https://developers.kakao.com/docs/ko/message-template/custom)
- [Codex 브라우저 연결](https://learn.chatgpt.com/docs/chrome-extension)
- [Claude Code Chrome 연결](https://code.claude.com/docs/en/chrome)
