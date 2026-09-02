# NFR Requirements — U-KNOWLEDGE

단위: 문서 등록, 추출, 공식 검색, 기사 확정, 근거 원문.  
스택 표는 `tech-stack-decisions.md`. 클라우드·가용성 %·CI/CD는 요구사항 NFR-6.5대로 이 Prototype에 두지 않는다.

---

## Performance

| 항목 | 목표 |
|---|---|
| 원본 파일 | 최대 20MB. 초과는 업로드 실패 |
| 추출 | 제한시간 30초. 초과는 추출 실패 = 업로드 실패 (파일 안 남김) |
| 공식 검색 | 호스트당 10초, 전체 30초. 초과는 빈 목록+실패 |
| HTTP 조회 (목록, 상세, getEvidence, listRelated) | 로컬 p95 SLA 없음. 수십 건 스캔이 끝나면 응답 |
| summary | 초기값 추출 앞 500자. 저장 상한 4000자. extractedText 전체는 별도 저장 |

업로드는 완료/실패까지 동기. 화면은 스피너. 진행률 % 없음 (N12 A).

---

## Scalability

| 항목 | 가정 |
|---|---|
| 동시 사용자 | 1 (로컬 데모) |
| 문서+기사 | 수십 건 |
| listRelated | 인덱스 없이 부문+Tag 교집합 스캔 |
| 스케일 아웃 | 없음. 프로세스 하나 |

---

## Availability

| 항목 | 목표 |
|---|---|
| SLA % | 두지 않음 (NFR-6.2) |
| RTO | 로컬 스택 재기동 (NFR-6.3) |
| RPO | PostgreSQL 로컬 볼륨 + `KNOWLEDGE_FILES_DIR` |
| 데모 복구 | Mock/시드 재적재. 시드 HWP는 추출 텍스트 동봉 (N4 C) |

Infrastructure Design SKIP. 다중 리전·로드밸런서 없음.

---

## Reliability

| 실패 | 동작 |
|---|---|
| 추출 실패 (형식, CLI 없음, 타임아웃, 비0) | 업로드 전체 실패. 파일·메타 없음 (K6 A) |
| 검색 키 없음 / HTTP 실패 / 타임아웃 | 빈 목록 + 실패 표시. 성공한 척 금지 (NFR-6.4) |
| 히트 URL이 허용 호스트 아님 | 결과에서 제외. 근거로 쓰지 않음 |
| PostgreSQL 다운 | API 실패. 숨기지 않음 |
| 재시도 | 이 단계 숫자 재시도 없음. 패턴은 NFR Design |

---

## Security

Security baseline 미적용 (NFR-7.1).

| 항목 | 이 단위 |
|---|---|
| 인증 | 없음. Mock 세션은 U-MONITOR (N8 A) |
| 업로드 | 확장자 화이트리스트 (pdf, txt, hwp). 20MB. 저장 경로가 `KNOWLEDGE_FILES_DIR` 밖으로 나가면 거부 |
| 비밀 | env. `.env` 커밋 금지 (NFR-7.2) |
| CORS | 개발은 웹 origin만 (프록시). `*` 없음 (N9 A) |
| 검색 키 | `OFFICIAL_SEARCH_API_KEY` |

---

## Usability

| 항목 | 결정 |
|---|---|
| 언어 | 문자열은 i18n 키. 기본 한국어. 전환 컨트롤은 Shell (N10 A) |
| 업로드 | 스피너. 실패는 폼 오류. 목록에 안 올라감 |
| HWP | 추출 텍스트·summary·다운로드. 뷰어 없음 |
| 검색 | 실패 상태를 목록과 함께 표시 |

`data-testid`는 코드 생성 (NFR-4.2).

---

## Maintainability

- 경로: `apps/web/src`, `apps/api/src/knowledge`, `apps/api/src/extraction`
- 패키지: npm workspaces
- 테스트: Vitest. API PBT는 fast-check
- 파일·DB 시드는 git에 원본 바이너리를 넣지 않는 것을 기본으로 한다. 시드 텍스트·메타는 코드/SQL로 재적재

---

## Testable properties (PBT-01, 코드 생성으로 이월)

Functional Design 산출물에 속성 절이 없었다. 이 단위 속성은 여기서 식별한다. NFR-5.1 전면.

| 속성 | 분류 | 주장 |
|---|---|---|
| EvidenceRef JSON round-trip | Round-trip | 직렬화 후 역직렬화 = 동일 evidenceId, kind, targetId |
| 허용 호스트 | Easy verification | 검색·근거 URL의 호스트는 enabled OfficialDomain과 같아야 한다. 아니면 거부 |
| listRelated 필터 | Oracle | 결과는 부문이 맞고, Tag가 비면 부문만, Tag가 있으면 교집합이 있는 항목만. 순위 없음 |
| Article 확정 | Invariant | confirmed=true만 listRelated·getEvidence(kind=article)에 포함 |
| 확정 해제 | Invariant | 해제 후 listRelated·getEvidence에서 제외 |
| 도메인 중복 | Idempotence | 같은 host 추가는 거부. 목록은 한 번만 |
| 업로드 실패 원자성 | Invariant | 추출 실패 후 DB에 해당 문서 행이 없고 `KNOWLEDGE_FILES_DIR`에 해당 파일이 없다 |

Web: Knowledge 홈 카드 2개, 업로드 검증(파일·문서명·부문)은 예제 테스트. PBT 대상 아님.

---

## Mapping

| 출처 | 이 문서 |
|---|---|
| NFR-1.1, NFR-1.2 | 로컬. Vite+Fastify |
| NFR-2.1, NFR-2.2 | PostgreSQL + `KNOWLEDGE_FILES_DIR` |
| NFR-3 | 이 단위 LLM 없음 |
| NFR-4 | i18n 키, 기본 ko |
| NFR-5 | Vitest + fast-check |
| NFR-6 | 시드 재적재, 검색 실패 표시, SLA 없음 |
| NFR-7 | 인증 없음 + 경로/확장자/크기 |
| K1–K8, K6 A | 실패·확정 규칙 유지 |
