# minki-kakao-me

**Codex에서 카카오톡 ‘나와의 채팅’으로 텍스트·사진·링크 알림을 보내는 Windows용 스킬.**

A Windows Codex skill for KakaoTalk self notifications through Kakao's official API.

사용자가 지정한 메시지 구성을 우선하고, 따로 지정하지 않은 부분은 Codex가 작업 내용에 맞춰 선택합니다. 카카오 공식 API를 직접 호출하므로 MCP 서버를 설치할 필요가 없습니다.

## 지원하는 구성

| 항목 | 지원 범위 |
| --- | --- |
| 본문 | 최대 200자 |
| 카드 제목 | 선택 사항, 최대 100자 |
| 링크 버튼 | 0·1·2개, 각 문구와 목적지 지정 |
| 버튼 문구 | 각 1~10자 |
| 사진 | 카카오가 접근할 수 있는 이미지 URL |
| 자동 구성 | 내용에 맞춰 사진 유무와 유용한 링크 0~2개 선택 |
| 미리보기 | 실제 발송 없이 메시지 명세 검증 |
| 토큰 갱신 | 액세스 토큰 자동 갱신, 인증 거부 시 1회 재시도 |
| 중복 방지 | 논리적 전송 ID 기준 최근 100건 기록 |

자동 구성은 Codex의 문맥 판단과 스킬 지침으로 이루어집니다. Python 스크립트는 메시지 명세를 검증하고 전송합니다. 자체 이미지 검색·이미지 생성·로컬 사진 업로드 기능은 포함하지 않습니다.

## 필요한 환경

- Windows와 Python 3.10 이상
- Codex의 로컬 스킬 사용 환경
- 본인의 Kakao Developers 앱 및 카카오 계정
- 카카오 로그인과 `talk_message` 동의
- 버튼에 사용할 웹 도메인 등록
- 버튼 없는 알림을 위한 사용자 정의 템플릿 등록

실행 코드의 외부 Python 패키지 의존성은 없습니다. 인증정보 저장에 Windows DPAPI를 사용하므로 현재 구현은 Windows용입니다.

## 설치

Codex에 다음과 같이 요청할 수 있습니다.

```text
https://github.com/minkissam/minki-kakao-me 의 스킬을 설치해줘.
```

직접 설치하려면 PowerShell에서 실행합니다. `CODEX_HOME`을 별도로 지정한 경우 해당 경로를 사용합니다.

```powershell
$codexSkillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex\skills' }
$kakaoSkillPath = Join-Path $codexSkillRoot 'minki-kakao-me'
git clone https://github.com/minkissam/minki-kakao-me.git $kakaoSkillPath
```

설치 후 다음 대화 차례에서 `$minki-kakao-me`를 사용합니다. 해당 폴더가 이미 있으면 기존 소스와 변경 사항을 확인한 뒤 업데이트합니다.

## 최초 연결

1. [카카오 앱·로그인 연결 안내](references/setup.md)에 따라 앱 키와 계정을 연결합니다.
2. [템플릿 설정 안내](references/templates.md)에 따라 버튼 없는 텍스트용·이미지용 템플릿을 등록합니다.
3. 등록한 템플릿 ID와 웹 도메인을 `messaging --from-file`로 로컬에 반영합니다.
4. 메시지를 미리 본 다음 나와의 채팅으로 발송합니다.

새로 설치하는 사람은 **본인의 앱 키·계정·템플릿**을 등록해야 합니다. 저장소에는 실제 계정 설정이 포함되지 않습니다.

### 기존 kakao-me 사용자

스킬 이름은 `minki-kakao-me`이며, 내부 실행 파일은 `scripts/kakao_me.py`입니다. 기존 연결을 유지하기 위해 인증 저장 경로 `%LOCALAPPDATA%\Codex\kakao-me`와 환경변수 `KAKAO_ME_CONFIG_DIR`은 유지합니다. 스킬 폴더 이름 변경 때문에 `configure`를 다시 실행할 필요는 없습니다.

## Codex에서 사용

```text
$minki-kakao-me 나에게 hello, world라고 보내줘.

$minki-kakao-me 작업 끝났다고 버튼 없이 짧게 보내줘.

$minki-kakao-me 이 보고서로 연결되는 ‘보고서 열기’ 버튼 하나를 넣어서 보내줘.

$minki-kakao-me 사진은 빼고 ‘신청 확인’과 ‘시트 열기’ 버튼 두 개를 넣어줘.

$minki-kakao-me 이 이미지 URL을 사진으로 넣고 버튼 없이 보내줘.

$minki-kakao-me 이 결과를 나에게 보내줘. 구성은 내용에 맞게 골라줘.
```

사진·자료 URL이 대화나 작업에 있으면 그 자료를 사용합니다. 자동 선택에서 열어볼 자료가 없으면 버튼을 생략합니다. 사용자가 버튼을 지정했는데 목적지가 없으면 실제 주소를 확인합니다.

## 명령줄 사용

저장소 또는 설치한 스킬 폴더에서 실행합니다.

```powershell
py -3 -B -X utf8 scripts/kakao_me.py status
py -3 -B -X utf8 scripts/kakao_me.py messaging
py -3 -B -X utf8 scripts/kakao_me.py send --message-file message.local.json --request-id report-001 --dry-run
py -3 -B -X utf8 scripts/kakao_me.py send --message-file message.local.json --request-id report-001
```

메시지 JSON 예시:

```json
{
  "text": "자료 정리가 끝났습니다.",
  "title": "작업 완료",
  "image_url": null,
  "buttons": []
}
```

전체 필드, 링크 버튼과 사진의 예시, 템플릿 등록 절차는 [메시지 명세](references/templates.md)를 참고합니다.

## 동작 기준

- 버튼에는 실제 목적지 URL을 사용하며 경로·쿼리·프래그먼트를 유지합니다. 미등록 도메인이나 누락된 링크를 다른 주소로 대체하지 않습니다.
- 버튼 0개는 사용자 정의 피드, 버튼 1~2개는 기본 텍스트/피드 템플릿으로 보냅니다. 카카오의 앱 출처 영역은 별도로 표시될 수 있습니다.
- 카카오의 표시 영역에 따라 제목·본문이 줄임 표시될 수 있습니다. 스크립트는 한도를 넘는 입력을 조용히 자르지 않습니다.
- 이미지 URL은 실제 이미지 응답이어야 합니다. 로컬 파일·로그인이 필요한 웹페이지 주소는 이미지 URL로 사용할 수 없습니다.
- `dry-run`은 네트워크 호출이나 토큰·전송 기록 변경 없이 검증합니다.
- `sent: true`, `result_code: 0`은 API 전송 성공입니다. 실제 화면 표시나 푸시 수신까지 보장하는 값은 아닙니다.
- 타임아웃·서버 오류·응답 불명은 이미 전달됐을 수 있으므로 자동 재전송하지 않습니다. 같은 알림의 재시도는 같은 request ID를 사용합니다.

## 인증정보

앱 키·시크릿·토큰은 현재 Windows 사용자용 DPAPI로 암호화해 스킬 소스와 별도 저장합니다. 프로필 파일, 실제 설정 JSON, 개인 메시지 기록은 저장소에 올리지 않습니다. 같은 Windows 사용자 권한으로 실행되는 프로그램은 DPAPI 데이터를 복호화할 수 있습니다.

스킬 설치·계정 연결만으로 모든 작업의 자동 발송을 허용하지 않습니다. 사용자가 요청한 메시지를 본인의 나와의 채팅으로 전송합니다.

## 검증

```powershell
py -3 -B -X utf8 -m unittest discover -s tests -v
```

오프라인 테스트 22개는 실제 카카오 인증이나 발송 없이 실행됩니다. 버튼 수·사진 조합, 명시 설정 우선, 목적지 보존, 미등록 도메인, 토큰 갱신, 중복 방지, 불확실한 응답 처리, DPAPI 저장과 잠금을 확인합니다. GitHub Actions에서도 Windows에서 같은 테스트를 실행합니다.

개발 중 실제 계정으로 사진 유무 × 버튼 0·1·2개인 6가지 구성의 API 발송 성공을 확인했습니다. 공개 저장소에는 해당 계정의 키·템플릿 ID·발송 기록을 포함하지 않습니다.

## 파일 구성

```text
SKILL.md                 Codex의 선택 기준과 실행 지침
agents/openai.yaml       스킬 표시 이름과 기본 요청문
scripts/kakao_me.py      공식 API·OAuth·암호화 저장·전송
references/setup.md     최초 계정 연결
references/templates.md 메시지 명세와 템플릿 등록
tests/test_kakao_me.py   오프라인 테스트
```

## 공식 참고 문서

- [카카오톡 메시지 REST API](https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api)
- [카카오 로그인 REST API](https://developers.kakao.com/docs/ko/kakaologin/rest-api)
- [기본 메시지 템플릿](https://developers.kakao.com/docs/ko/message-template/default)
- [사용자 정의 메시지 템플릿](https://developers.kakao.com/docs/ko/message-template/custom)
