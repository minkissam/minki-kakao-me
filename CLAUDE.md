# minki-kakao-me

이 저장소의 공통 작업 계약은 [AGENTS.md](AGENTS.md)다. 먼저 읽고 [SKILL.md](SKILL.md)와 [브라우저 연결 절차](references/agent-setup.md)를 따른다.

최초 연결은 Claude Code의 Chrome 도구로 앱 생성과 설정, 템플릿 등록을 진행한다. 브라우저 도구가 준비되지 않았으면 공식 Chrome 연결 안내를 열고 확장 프로그램 설치, `/chrome` 연결과 사이트 권한을 확인한다. 사용자에게 필요한 설치/로그인 행동만 요청한 뒤 같은 단계에서 재개한다.

실행은 저장소의 `setup.ps1` 또는 `scripts/kakao_me.py`를 사용한다. 명령 경로는 현재 체크아웃의 절대경로로 정한다. 브라우저 연결을 기다리는 동안 코드와 환경 점검을 이어 간다.
