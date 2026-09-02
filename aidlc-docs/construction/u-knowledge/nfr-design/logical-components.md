# Logical Components — U-KNOWLEDGE

런타임 프로세스: `apps/web`(Vite) → `/api` 프록시 → `apps/api`(Fastify) → PostgreSQL(compose) + 로컬 파일.  
클라우드 큐, 캐시, 로드밸런서 없음 (Infrastructure SKIP).

---

## 컴포넌트

| 컴포넌트 | 위치 | 책임 |
|---|---|---|
| KnowledgeUi | `apps/web` | 카드 2개, 업로드, 검색, 기사 확정, 원문. Extraction HTTP 없음 |
| KnowledgeCommandService | `apps/api` | registerPolicy/Decision, 기사 등록·확정/해제, 도메인 추가·삭제. temp-then-commit |
| KnowledgeQueryService | `apps/api` | 목록, getEvidence, listRelated, searchOfficial, 후보 목록 |
| KnowledgeRepository | Prisma | PolicyDocument, DecisionDocument, Article, OfficialDomain, EvidenceRef 대상 행 |
| FileStore | `apps/api` | temp 수신, 최종 경로 이동, `KNOWLEDGE_FILES_DIR` 하위 검사, 다운로드 스트림 |
| ExtractionPort | `apps/api` Extraction | txt UTF-8, PDF 라이브러리, HWP는 `HWP_EXTRACT_CMD`. 30초 |
| OfficialSearchPort | `apps/api` Knowledge | 허용 호스트 병렬 검색. 키·타임아웃. 재시도 없음 |
| KnowledgeSeedRunner | `apps/api` 스크립트 | migrate 후 시드 행·동봉 추출 텍스트 |
| RequestLog | Fastify 훅 | stdout 한 줄 (P8 A) |

회로차단기, 작업 큐, 캐시 프로세스 없음 (P1 A, P3 A, P6 C).

---

## 연결

```
KnowledgeUi
    HTTP /api
        KnowledgeCommandService
            FileStore (temp → 최종)
            ExtractionPort
            KnowledgeRepository
        KnowledgeQueryService
            OfficialSearchPort --> 검색 HTTP
            KnowledgeRepository
            FileStore (다운로드)
        KnowledgeSeedRunner (CLI, 요청 경로 밖)
PostgreSQL
KNOWLEDGE_FILES_DIR
```

Web은 OfficialSearch·파일·Prisma를 직접 쓰지 않는다.

---

## 외부 의존 (프로세스 밖)

| 의존 | 타임아웃 | 실패 시 |
|---|---|---|
| PostgreSQL | 드라이버/쿼리 타임아웃 (코드 생성에서 상수) | API 오류, 숨기지 않음 |
| Official search HTTP | 호스트 10초, 전체 30초 | P4 A |
| HWP CLI | 30초 | 추출 실패 = 업로드 실패 |
| PDF 라이브러리 | 추출 30초 한도에 포함 | 동일 |

OpenAI는 이 단위가 호출하지 않는다.

---

## 시드 (P7 A)

KnowledgeSeedRunner가 넣는 것:

- 여신 정책 요약용 PolicyDocument (MONITOR Attention)
- 포용금융 논의 DecisionDocument
- 포용금융 확정 Article
- OfficialDomain 기본 3 호스트

실행: API 패키지 스크립트. AdminUi는 U-PROPAGATE.

---

## 요청 흐름

### 업로드

```
Ui submit
  -> Command: 확장자·20MB 검사
  -> FileStore temp
  -> ExtractionPort
  -> 실패: temp 삭제, 4xx/5xx, 목록 불변
  -> 성공: FileStore commit + Repository insert (같은 트랜잭션 경계)
```

DB 커밋 실패 시 방금 옮긴 최종 파일은 삭제한다. temp는 이미 없을 수 있다.

### 검색

```
Ui searchOfficial
  -> Query: OfficialDomain.enabled 목록
  -> OfficialSearchPort 병렬
  -> URL 호스트 재검증
  -> 히트 0 + 전부 실패: error + []
  -> 그 외: hits (미저장)
```

### 원문

```
getEvidence
  -> kind+targetId
  -> article이면 confirmed만
  -> 메타 + summary + FileStore 경로 또는 URL
```

---

## N/A

| 논리 요소 | 이유 |
|---|---|
| Queue, Redis, LB | P3 A, Infrastructure SKIP |
| CircuitBreaker | P1 A |
| Identity 가드 | N8 A, U-MONITOR |
| OpenTelemetry collector | P8 A |
| CI runner | P9 A |
