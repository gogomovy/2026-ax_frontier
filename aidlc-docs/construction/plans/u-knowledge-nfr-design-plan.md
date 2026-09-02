# NFR Design Plan — U-KNOWLEDGE

NFR Requirements 승인됨.  
산출물: `aidlc-docs/construction/u-knowledge/nfr-design/`  
승인 후 다음 단계는 Infrastructure Design SKIP → **Code Generation** 계획.

이 파일의 `[Answer]:`를 모두 채운 뒤 채팅에서 **답을 채웠으니 다시 읽고 진행해 달라**고 해 주세요.

---

## 이미 고정된 것 (다시 묻지 않음)

- 로컬만. 스케일 아웃 없음. 동시 1명, 문서 수십 건
- 파일 20MB, 추출 30초, 검색 호스트당 10초·전체 30초
- 추출 실패 = 업로드 실패, 파일 안 남김. 검색 실패는 빈 목록+표시
- 인증 없음. 확장자·크기·`KNOWLEDGE_FILES_DIR` 이탈 거부
- 업로드는 동기+스피너. 큐·워커는 NFR 요구에서 없음으로 가정하되, 패턴은 아래에서 확정
- 재시도 횟수는 NFR Requirements가 이 단계로 넘김
- NFR-6.5: 프로덕션 DR·CI/CD·리전은 배포가 범위에 들어오는 단계에서 다시
- Infrastructure Design SKIP. Operations PLACEHOLDER

---

## 답변에서 확정한 생성 규칙

원문 P1–P9는 모두 “추천안”. NFR Requirements·K6 A·NFR-6.5와 맞춰 아래 글자로 기록한다.

- P1 A: 검색 재시도 없음. 회로차단기 없음
- P2 A: temp 추출 후 성공일 때만 최종 경로+DB 커밋
- P3 A: 추출·검색은 HTTP 요청 안 동기. 큐·워커 없음
- P4 A: 호스트 병렬. 일부 성공은 합침. 전부 실패만 빈 목록+실패
- P5 A: 디스크 `{versionNo}.{ext}`. 원본명은 DB. Content-Disposition은 title
- P6 C: FileStore, ExtractionPort, OfficialSearchPort, KnowledgeRepository, KnowledgeSeedRunner
- P7 A: 이 단위 `apps/api` 시드 스크립트. 바이너리 git 금지
- P8 A: stdout 요청 한 줄. 키·파일 내용 없음
- P9 A: CI/CD·IR·카오스 없음. 복구는 재기동+시드 재적재

## 승인 후 실행할 체크리스트

- [x] `aidlc-docs/construction/u-knowledge/nfr-design/nfr-design-patterns.md`
- [x] `aidlc-docs/construction/u-knowledge/nfr-design/logical-components.md`

---

## Question P1

공식 검색의 장애 격리 패턴은요? (Resilience / RESILIENCY-10)

타임아웃 숫자는 이미 있다. 회로차단기는 로컬 1명에 과할 수 있다.

A) 재시도 없음. 호스트당 1회. 타임아웃·4xx/5xx·키 없음은 즉시 실패 표시. 회로차단기 모듈 없음

B) 검색만 같은 요청 안에서 1회 재시도(동일 질의). 그다음 실패 표시. 회로차단기 없음

C) 연속 실패 3회 후 검색 포트를 연 상태(즉시 실패)로 두고, API 프로세스 재기동까지 유지

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. NFR이 재시도 숫자를 두지 않았고, 로컬 1명에 회로차단기(C)는 필요 없다. 실패는 즉시 표시 (K6 A).

---

## Question P2

업로드·추출의 원자성 패턴은요? (Resilience)

실패 후 DB 행과 `KNOWLEDGE_FILES_DIR` 파일이 없어야 한다 (K6 A).

A) 요청 temp에 받은 뒤 추출. 성공일 때만 최종 경로와 DB를 한 트랜잭션으로 커밋. 실패면 temp 삭제

B) 최종 경로에 저장한 다음 추출. 실패면 파일 삭제 + DB 롤백 (보상)

C) multipart를 최종 경로에 직접 씀. 추출 실패 시 파일 삭제 시도. 삭제 실패와 DB 없음이 겹치면 불일치 가능

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. K6 A와 PBT 업로드 원자성: 추출 실패 후 최종 경로에 파일이 없어야 한다. B·C는 최종 경로에 먼저 쓴다.

---

## Question P3

추출·검색을 요청 안에서 돌릴까요, 별도 실행 단위를 둘까요? (Scalability)

N6 A는 동시 1명·큐 없음이다. 여기서 실행 경계를 확정한다.

A) 추출·검색 모두 HTTP 요청 안에서 동기. 워커·메시지 큐·캐시 프로세스 없음

B) 추출만 프로세스 안 단일 슬롯(한 건씩). 검색·조회는 동기. 외부 큐 없음

C) 외부 큐 또는 캐시(Redis 등)를 둔다

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. N6 A·N12 A와 같다. Redis(C)는 NFR에 없다. 단일 슬롯 큐(B)는 동시 1명에 필요 없다.

---

## Question P4

허용 호스트가 여러 개일 때 검색 호출은요? (Performance)

호스트당 10초, 전체 30초.

A) 호스트별 검색을 병렬. 전체 한도 30초. 한 호스트가 실패해도 다른 호스트 결과는 합친다. 전부 실패면 빈 목록+실패

B) 호스트 순차. 합 시간이 30초에 닿으면 나머지 호스트는 호출하지 않음. 일부 성공이면 그 결과만 (부분 실패를 실패로 표시하지 않음)

C) 순차. 한 호스트라도 실패하면 전체를 빈 목록+실패로 본다 (부분 성공 없음)

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. 기본 도메인이 3곳이라 순차(B/C)는 한도 30초에 잘린다. 한 호스트 실패로 전체 실패(C)는 데모가 한 사이트에 묶인다. 전부 실패만 빈 목록+실패 (NFR-6.4).

---

## Question P5

업로드 파일명·다운로드 헤더 패턴은요? (Security)

Security baseline은 강제하지 않는다. 경로 이탈은 이미 거부한다.

A) 디스크 이름은 `{versionNo}.{ext}`만. 사용자 원본명은 DB 메타. 다운로드 `Content-Disposition`은 문서 title. path 문자(`..`, 구분자)는 파일명에 안 씀

B) 사용자 원본 파일명을 쓰되 `..`와 디렉터리 구분자는 거부. 그 외 문자는 유지

C) 크기·확장자만. 파일명은 클라이언트가 준 문자열을 그대로 씀

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. `KNOWLEDGE_FILES_DIR` 이탈 거부와 맞다. 사용자 문자열을 디스크 이름에 쓰지 않는다 (C 제외).

---

## Question P6

이 단위 논리 컴포넌트는요? (Logical Components)

큐·로드밸런서·클라우드 리소스는 Infrastructure SKIP.

A) FileStore, ExtractionPort(PDF 라이브러리 + HWP CLI), OfficialSearchPort, KnowledgeRepository(Prisma). 캐시·큐·회로차단기 컴포넌트 없음

B) A + OfficialSearchPort 앞에 회로차단기

C) A + KnowledgeSeedRunner(CLI). Admin 화면은 U-PROPAGATE. 이 단위는 테이블·파일을 채우는 스크립트만

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **C**. P7 A 시드 스크립트를 논리 컴포넌트로 둔다. 회로차단기(B)는 P1 A와 어긋난다. Admin UI는 PROPAGATE.

---

## Question P7

Knowledge 시드 재적재는 어디에 둘까요? (Resilience / NFR-6.3)

A) 이 단위 `apps/api` 시드 스크립트. Prisma migrate 후 Knowledge 행+시드 텍스트(및 동봉 HWP 텍스트). 원본 바이너리는 git에 안 넣음

B) 시드 데이터 파일만 이 단위에 두고, 실행 진입점은 U-PROPAGATE AdminSeed가 연 뒤에 호출

C) `docker compose down -v` 후 up + migrate + seed를 루트 스크립트 하나로. 단위 코드 안의 SeedRunner는 없음

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. NFR-6.3 재적재를 이 단위에서 실행할 수 있어야 한다. B는 PROPAGATE까지 시드가 없다. C는 SeedRunner가 없다.

---

## Question P8

로컬 관측은요? (Resilience / Logical Components)

A) stdout에 요청 단위 한 줄(요청 id, 경로, 상태, 추출/검색 실패 이유). PII·파일 내용·검색 키 없음

B) 실패만 stderr. 성공 요청은 로그 없음

C) OpenTelemetry 등 별도 관측 스택

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. 검색·추출 실패를 숨기지 않으려면 요청 로그가 필요하다. OTel(C)은 로컬 Prototype 범위 밖.

---

## Question P9

CI/CD, 배포 롤백, 카오스, 사고 대응은요? (RESILIENCY-04, 14, 15)

프로덕션 배포는 범위 밖이다 (NFR-6.5, Infrastructure SKIP, Operations PLACEHOLDER).

A) 이번 Prototype은 파이프라인·배포 롤백·카오스·IR 프로세스 없음. 복구 검증은 로컬 재기동과 시드 재적재

B) 테스트만 CI(GitHub Actions). 배포·IR·카오스는 없음

C) 조직에 있는 CI/IR/DR 연습에 맞춘다. 레퍼런스를 [Answer]: 뒤에 적는다

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. NFR-6.5, Infrastructure SKIP, Operations PLACEHOLDER. 조직 CI 레퍼런스(C)는 없다.
