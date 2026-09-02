# NFR Design Patterns — U-KNOWLEDGE

NFR Requirements와 P1–P9. 클라우드 패턴(오토스케일, 멀티 AZ)은 Infrastructure SKIP·NFR-6.5로 적용하지 않는다.

---

## Resilience

### Fail-fast 검색 (P1 A)

- OfficialSearchPort는 호스트당 HTTP 1회. 재시도 없음
- 타임아웃 10초/호스트, 전체 30초 (N5 A)
- 키 없음, 4xx/5xx, 타임아웃: 그 호스트는 히트 없음
- 회로차단기 없음 (RESILIENCY-10 CB: 이 단위 N/A. 타임아웃은 적용)

### Temp-then-commit 업로드 (P2 A)

1. multipart를 요청 temp에 둔다 (`KNOWLEDGE_FILES_DIR` 밖)
2. ExtractionPort가 temp 경로를 읽는다
3. 성공이면 최종 `{KNOWLEDGE_FILES_DIR}/{kind}/{id}/v{n}/{versionNo}.{ext}`로 옮기고 Prisma 트랜잭션으로 행을 쓴다
4. 실패면 temp를 지운다. 최종 경로와 DB에 해당 버전 없음

보상 삭제(P2 B)는 쓰지 않는다. 추출 전에 최종 경로에 쓰지 않는다.

### 시드 재적재 (P7 A, NFR-6.3)

- KnowledgeSeedRunner: migrate 후 정책·의사결정·확정 기사·공식 도메인 시드
- 시드 HWP는 추출 텍스트 동봉. CLI 없이 재적재
- 원본 바이너리는 git에 넣지 않는다

### 복구 (P9 A)

- RTO: 프로세스·compose 재기동
- 검증: 시드 재적재 후 목록·getEvidence가 시드 행을 돌려준다
- CI/CD, 카오스, IR 프로세스 없음

---

## Scalability

### In-request 동기 (P3 A, N6 A)

- registerPolicy / searchOfficial / listRelated는 그 HTTP 요청이 끝날 때까지 실행된다
- 워커, 메시지 큐, Redis 없음
- 프로세스 하나. 스케일 아웃 패턴 없음

---

## Performance

### 호스트 병렬 검색 (P4 A)

- enabled OfficialDomain마다 검색을 병렬 호출
- 호스트 실패는 그 호스트 히트만 빠진다
- 성공 호스트가 하나라도 있으면 요청은 성공(합친 목록). 검색 오류 플래그는 켜지 않는다
- 성공 호스트가 0이면 빈 목록 + 실패 표시 (K6 A, NFR-6.4)
- URL 호스트가 허용 목록이 아니면 히트에서 제거

### 조회

- listRelated: 테이블 스캔 + 부문+Tag 필터. 캐시 없음
- 파일 다운로드: FileStore가 스트림. 추출 텍스트는 DB

---

## Security

Security baseline 미적용.

### 파일 이름 (P5 A)

- 디스크: `{versionNo}.{ext}`만. `..`와 구분자를 파일명에 쓰지 않는다
- 사용자 원본명은 DB 메타
- 다운로드 `Content-Disposition`: 문서 title + ext
- 저장 전 최종 경로가 `KNOWLEDGE_FILES_DIR` 정규화 경로의 하위인지 검사. 아니면 거부
- 확장자 화이트리스트: pdf, txt, hwp
- 인증 미들웨어 없음 (N8 A)

### 로그 (P8 A)

- 요청 id, 경로, 상태, 추출/검색 실패 이유만 stdout
- 파일 바이트, 추출 본문, `OFFICIAL_SEARCH_API_KEY` 없음

---

## 적용하지 않는 패턴

| 패턴 | 이유 |
|---|---|
| Circuit breaker | P1 A, 로컬 1명 |
| Bulkhead / 외부 커넥션 풀 분리 | 프로세스 하나, 동시 1 |
| Retry with backoff | P1 A |
| Cache-aside | 수십 건 스캔 |
| Blue/green, canary | P9 A |
| WAF, JWT | NFR-7.1, N8 A |
