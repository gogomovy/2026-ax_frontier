# NC 에이전트 JS 넣는 곳 (저장소에 올리지 않음)

사내 SSO 로그인 페이지(`/sso-proxy.html`)가 `/nc/*.js` 로 읽는 벤더 스크립트입니다. api 컨테이너가 이 폴더를 `/opt/nc-js` 로 읽어 서빙합니다.

- `NexessDemonFunc.js` — `CONST_LOCAL_DEMON_ADDRESS = "https://127.0.0.1:13015"` (에이전트 주소)
- `json2.js`
- `jquery-3.5.1.js` · `jquery-3.5.1.min.js` — NexessDemonFunc.js 가 `document.write` 로 다시 읽으므로 둘 다 필요

이 폴더의 `.js` 는 `.gitignore` 로 커밋하지 않습니다.
