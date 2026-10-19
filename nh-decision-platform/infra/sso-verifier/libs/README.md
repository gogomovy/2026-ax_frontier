# 벤더 jar 넣는 곳 (저장소에 올리지 않음)

사내 SSO(INISAFE Nexess) 티켓 복호화에 쓰는 jar 를 이 폴더에 넣으면 `sso-verifier` 컨테이너가 `/app/libs` 로 읽습니다.

| 파일 | 역할 |
|---|---|
| `external_v4.2.1.00_NHBank14.jar` | `com.initech.eam.nls.TicketV3` (티켓 복호화) |
| `INICrypto_v4.2.10.jar` | `com.initech.provider.crypto.InitechProvider` (JCE) |
| `INISAFEToolSet_v1.1.1.jar` | Initech 유틸 |
| `jdom2-2.0.6.1.jar` | NC jar 의존성 |
| `log4j-api-2.24.3.jar` · `log4j-core-2.24.3.jar` | Apache Log4j 2(자바 로그 라이브러리) — `external_v4.2.1.00_NHBank14.jar` 가 `org.apache.logging.log4j.core` 를 직접 부른다. ai-driven-hub(Spring Boot 3.5.12)가 쓰던 판과 같다. Maven Central `org.apache.logging.log4j:log4j-api` · `log4j-core` |

넣은 뒤 `docker compose --profile sso up -d sso-verifier` → `curl -s http://127.0.0.1:8090/health` 가 `{"ok":true,"provider":true}` 면 준비 완료입니다(컨테이너 안에서).
