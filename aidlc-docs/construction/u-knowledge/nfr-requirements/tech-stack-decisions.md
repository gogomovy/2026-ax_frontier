# Tech Stack Decisions — U-KNOWLEDGE

이 선택이 모노레포 기본이다. 버전은 코드 생성 때 lockfile로 고정한다. 아래 이름은 패키지·도구이지 아직 lock된 숫자가 아니다.

---

## Core

| 기술 | 역할 |
|---|---|
| TypeScript | `apps/web`, `apps/api` |
| React + Vite | `apps/web` SPA. SSR 없음 (N1 A, NFR-1.1) |
| Fastify | `apps/api` HTTP. Next Route Handler로 API를 합치지 않음 (FR-10) |
| npm workspaces | 루트에서 `apps/web`, `apps/api` |
| i18next | Knowledge 문자열 키. 기본 `ko` |

브라우저는 웹 origin만 사용한다. Vite가 `/api`를 Fastify로 프록시한다 (N9 A).

---

## Data

| 계층 | 기술 | 역할 |
|---|---|---|
| DB | PostgreSQL | NFR-2.1 |
| 실행 (기본) | docker compose + 로컬 볼륨 | 앱은 호스트 (N7 C) |
| 접속 | `DATABASE_URL` | compose 없이 설치형 Postgres로 바꿀 수 있음 |
| ORM | Prisma | 마이그레이션 포함 (N14 A) |
| 파일 | 로컬 디스크 | `KNOWLEDGE_FILES_DIR` (기본 `data/knowledge`) |

이 단위 Prisma 스키마가 Knowledge 테이블을 연다. Identity·Metrics·Goal 테이블은 이후 단위.

---

## Extraction

| 형식 | 방법 |
|---|---|
| 텍스트 | UTF-8 파일 읽기 |
| PDF | API 프로세스 안 TypeScript PDF 텍스트 라이브러리. 구현 모듈은 코드 생성에서 하나 |
| HWP (사용자 업로드) | `HWP_EXTRACT_CMD`가 가리키는 로컬 CLI. 미설치·비0·타임아웃(30초) = 추출 실패 = 업로드 실패 |
| HWP (시드) | 원본 파일 + 추출 텍스트를 시드에 동봉. 재적재는 CLI 없이 됨 (N4 C) |

브라우저 HWP 뷰어 없음. Extraction은 UI가 직접 호출하지 않는다.

---

## Official search

| 항목 | 결정 |
|---|---|
| 방식 | 허용 호스트로 제한한 웹 검색 HTTP API (N3 A, FR-7.8) |
| 키 | `OFFICIAL_SEARCH_API_KEY` (env). 없음·4xx/5xx·타임아웃 = 빈 목록+실패 |
| URL 검증 | 응답 URL 호스트가 OfficialDomain.enabled가 아니면 버림 |
| 제공자 상품명 | 이 문서에서 고정하지 않음. 코드 생성 계획이 어댑터 구현 하나를 고른다 |
| 히트 저장 | SearchHit는 엔티티가 아님. 후보로 넣은 뒤에만 Article |

---

## Testing

| 기술 | 역할 |
|---|---|
| Vitest | `apps/api`, `apps/web` 예제 테스트 |
| fast-check | API PBT (N11 A) |
| Playwright 등 E2E | 이 단위 범위 밖 |

---

## Local run

```
apps/web  (Vite, /api 프록시)
    |
    v
apps/api  (Fastify, Prisma → PostgreSQL)
    |
    +-- Extraction (PDF lib, HWP CLI)
    +-- Official search HTTP (env 키)
    +-- files under KNOWLEDGE_FILES_DIR
```

클라우드 리소스 없음. Infrastructure Design SKIP.

---

## Secrets (커밋 금지)

- `DATABASE_URL`
- `OFFICIAL_SEARCH_API_KEY`
- `HWP_EXTRACT_CMD` (선택: 미설정이면 사용자 HWP 업로드 실패)
- `KNOWLEDGE_FILES_DIR` (미설정이면 `data/knowledge`)

OpenAI 키는 이 단위가 호출하지 않는다. 이후 Agent 단위에서 같은 env 규칙을 쓴다.

---

## Prohibited (이 단위)

| 쓰지 않음 | 이유 |
|---|---|
| Next.js Route Handler를 API로 | `apps/api` 별도 프로세스 (FR-10, N1 A) |
| 브라우저에서 HWP 렌더 | FR-7.3 |
| 이 단위 LLM 요약 | K4 B |
| 검색 실패를 성공으로 표시 | NFR-6.4 |
| 원본 파일을 git에 넣음 | N2 C gitignore |
| 인증 미들웨어 (이 단위) | N8 A. MONITOR에서 Mock 세션 |
