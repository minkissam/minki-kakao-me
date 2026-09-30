# 메시지 명세와 템플릿

## 메시지 JSON

```json
{
  "text": "요청하신 자료 정리가 끝났습니다.",
  "title": "자료 정리 완료",
  "type": "auto",
  "image_url": null,
  "buttons": [
    {"title": "자료 열기", "url": "https://example.com/reports/123"},
    {"title": "관련 문서", "url": "https://example.com/docs/456"}
  ]
}
```

예시 URL은 형식 설명용이다. 발송할 때 실제 자료 URL과 등록한 도메인을 사용한다.

| 항목 | 의미 |
| --- | --- |
| `text` | 본문, 최대 200자. 제목 또는 사진이 있으면 빈 문자열 가능 |
| `title` | 선택적 카드 제목, 최대 100자 |
| `type` | `auto`(기본), `text`, `feed`. `text`와 사진/별도 제목의 동시 지정은 오류 |
| `image_url` | 사진 URL. 생략 또는 `null`은 사진 없음 |
| `image_width`, `image_height` | 선택적 양의 픽셀값. 기본 피드에서만 적용. 버튼 없는 이미지의 비율은 등록한 템플릿에서 설정 |
| `buttons` | 사용자가 지정했거나 Codex가 최종 선택한 0~2개 버튼. `[]`면 반드시 0개 |
| 버튼 `title` | 문구, 1~10자 |
| 버튼 `url` | PC 웹 목적지이자 모바일 기본 목적지 |
| 버튼 `mobile_url` | 선택적 모바일 전용 URL. 생략하면 `url`과 같음 |
| `actions` | `buttons`를 생략했을 때만 사용할, Codex가 의미를 검토한 행동 후보. 중요도 순서. 자동 선택은 앞의 최대 2개 |
| `button_count` | `auto`(기본) 또는 0/1/2. 명시한 개수의 목적지가 부족하면 오류. `buttons`와 함께 쓰면 개수가 일치해야 함 |

`buttons`는 `actions`보다 우선한다. `button_count: 0` 또는 `buttons: []`가 있으면 행동 후보가 있어도 버튼을 넣지 않는다. 본문·제목·이미지가 모두 비어 있으면 오류다. 지원하지 않는 필드, 잘못된 URL, 과도한 버튼 수는 발송 전에 거절한다.

### 짧은 알림 — 자동으로 버튼 없음

```json
{"text":"요청하신 작업이 끝났습니다."}
```

### 다음 행동 한 가지 — 자동으로 버튼 1개

```json
{
  "text":"카카오 메시지 템플릿의 공식 설명입니다.",
  "actions":[{"title":"설명 열기","url":"https://developers.kakao.com/docs/ko/message-template/default"}]
}
```

### 사진을 포함하고 버튼은 명시적으로 제외

```json
{
  "title":"완성한 이미지",
  "text":"요청하신 이미지입니다.",
  "image_url":"https://example.com/images/result.png",
  "buttons":[]
}
```

## 전송 경로

- 버튼 1~2개: 공식 기본 메시지 `/v2/api/talk/memo/default/send`. 사진이나 제목이 있으면 피드, 없으면 텍스트. 콘텐츠 영역은 첫 번째 버튼의 링크를 사용한다.
- 버튼 0개: 앱에 등록한 사용자 정의 피드 `/v2/api/talk/memo/send`. 텍스트 전용 또는 이미지 포함 템플릿을 선택한다. 일반 말풍선과는 다른 카드 형태이며 앱 출처 표시는 카카오가 관리한다.
- 기본 템플릿에서 필수 링크만 제거하거나 의미 없는 URL로 숨기는 방법에 의존하지 않는다.

## 최초 버튼 없는 템플릿 등록

카카오 [메시지 템플릿 도구](https://developers.kakao.com/tool/template-builder/app)에서 현재 연결한 앱을 선택한다. 먼저 목록을 확인해 같은 역할의 템플릿이 있으면 재사용한다.

**텍스트용 사용자 정의 피드 A형**

1. 공통 설정의 사용 목적은 **카카오톡 공유**. 카카오 공식 안내상 나에게 보내기만 사용하는 경우 이 값을 선택한다.
2. 전달 허용은 불가. 메시지 제목/본문만 ON으로 하고 이미지·버튼·헤더·프로필·소셜·아이템은 OFF로 한다.
3. 제목은 `${TITLE}`, 본문은 `${TEXT}`로 지정한다.
4. 공통 링크는 사용 안 함으로 한다. 메시지 제목/본문도 링크 없음인지 확인한다. 저장 후 템플릿 ID와 인자 목록을 확인한다.

**이미지용 사용자 정의 피드 A형**

1. 텍스트용을 복제해 별도 이름을 붙인다.
2. 이미지 ON, 이미지 1장만 남기고 사용자 인자를 `${IMAGE}`로 설정한다. 이미지 크기는 필수값을 채우고 원본 비율 유지 또는 원하는 비율을 설정한다.
3. 버튼은 OFF, 공통/본문/이미지 링크는 없음으로 유지한다. 제목·본문은 `${TITLE}`, `${TEXT}`다.
4. 저장 후 템플릿 ID와 인자 `TITLE`, `TEXT`, `IMAGE`를 확인한다.

이 과정은 템플릿 생성·수정이며 토큰 재발급은 필요하지 않다. 기존 앱의 다른 템플릿을 임의로 덮어쓰지 않는다.

## 등록 정보를 로컬에 반영

아래 JSON은 앱 키나 토큰을 포함하지 않는다. ID는 현재 앱의 실제 값으로 바꾸고, 도메인은 카카오 앱의 제품 링크 관리에서 등록을 확인한 값만 넣는다.

```json
{
  "registered_web_origins":["https://example.com"],
  "buttonless_text_template_id":"12345",
  "buttonless_image_template_id":"12346"
}
```

```text
py -3 -B -X utf8 <skill>/scripts/kakao_me.py messaging --from-file <settings.json>
py -3 -B -X utf8 <skill>/scripts/kakao_me.py messaging
```

`messaging`은 로컬 등록 정보를 반영한다. 카카오 서버에 도메인이나 템플릿을 생성하는 명령이 아니다. 부분 갱신을 지원하며 `registered_web_origins` 배열은 전체 목록으로 교체된다. 기존 목록을 먼저 읽고 필요한 도메인을 추가한다. 인증정보와 최근 전송 기록은 유지된다.

## 점검과 오류

- `missing_buttonless_template`: 요청한 사진 유무에 대응하는 템플릿을 등록한다. 임의로 버튼을 추가해 보내지 않는다.
- `missing_link`: 사용자가 명시한 버튼의 실제 목적지를 확보한다.
- `unregistered_domain`: 해당 URL의 프로토콜·호스트·포트를 제품 링크 관리에 등록하고 로컬 목록도 갱신한다. 도메인을 비교하며 경로·쿼리·프래그먼트는 그대로 보낸다.
- `conflicting_layout` / `invalid_buttons`: 명시한 옵션들이 충돌한다. 사용자의 우선 선택을 유지하면서 명세를 고친다.
- `custom_image_dimensions`: 버튼 없는 이미지는 사용자 정의 템플릿의 비율 설정을 사용한다.
- 사진 URL이 HTML 로그인 페이지이거나 접근 거부를 반환하면 사진을 보내지 않는다. 비공개 파일을 공개로 전환하는 판단은 사용자 요청 범위를 확인한다.
- 실험에서는 식별 가능한 짧은 본문과 실제 열리는 링크를 사용한다. API 성공만 확인했으면 카톡 화면·버튼 클릭·사진 표시까지 검증했다고 쓰지 않는다.

## 공식 근거 (2026-09-30 확인)

- [기본 템플릿: 버튼·콘텐츠·링크](https://developers.kakao.com/docs/ko/message-template/default)
- [사용자 정의 템플릿: 구성 요소·사용자 인자](https://developers.kakao.com/docs/ko/message-template/custom)
- [카카오톡 메시지 REST API](https://developers.kakao.com/docs/ko/kakaotalk-message/rest-api)
- [카카오 개발자 지원: 버튼 없이 발송](https://devtalk.kakao.com/t/topic/118683)
