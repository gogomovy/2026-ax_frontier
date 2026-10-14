# NH AI 경영 의사결정 플랫폼

은행 내·외부 정보를 연결하여 **경영목표의 설정과 조정을 지원하고, 그 결과를 조직 전체의 판단 기준으로 전파**하는 Agentic AI 의사결정 플랫폼.

| 구분 | 현재 상태 |
|---|---|
| 스펙 | `.kiro/specs/nh-decision-ai-platform/` — `requirements.md`(§16) · `design.md`(§19) · `tasks.md`(Phase B) |
| 프론트엔드 | Next.js 16 · React 19 — 업무 화면 3개 부서(종합기획부 · 신용리스크관리부 · 영업점) + 로그인·가입 + 관리자 화면 25종(묶음 6개 · 관리자 홈) |
| 백엔드 | FastAPI + 워커 — 인증·권한, 계산 커널, 데이터셋/문서 적재, 온톨로지(Neo4j), 3-way 검색(PostgreSQL 원장 · Elasticsearch 키워드/의미 · Neo4j 그래프), 외부 LiteLLM 연동, 변경 기반 워크플로우 |
| 데이터 | 프론트는 항상 백엔드 API 만 쓴다(목데이터 모드 없음) — 자료를 올리기 전에는 수치 없는 화면 템플릿, 올린 뒤에는 모든 수치 · 기간을 업로드 자료로 계산. 시연 자료 패키지는 `python -m nhdip.cli load-sample` 또는 `python -m nhdip.sample upload` 로 올리고, 실데이터는 관리자 화면에서 같은 데이터셋 정의로 업로드 |

---

## 1. 실행 (Docker, 5개 서비스)

```bash
make up          # .env 준비(비밀값 자동 생성) → 빌드 → 기동 → 마이그레이션 · 정의 시드(정의만 · 업무 자료 없음). 시연 자료는 LOAD_SAMPLE_ON_START=1 일 때만 올린다(기본 0)
make sample      # 시연 자료 패키지(엑셀 · CSV · PDF 43개)를 실제 업로드 API 로 올리기 · make sample-verify 엑셀 독립 계산 ↔ 화면 대조
make admin-pass  # 최초 관리자 사번·비밀번호
make ps | logs | down | reset(볼륨 삭제) | test(백엔드 테스트) | e2e(브라우저 E2E, 기동 중인 스택 대상)
make wait-idle   # 이벤트 · 작업 처리가 끝날 때까지 대기 (기동 직후 선계산 확인)
make backup      # DB(업무 · litellm) + 업로드 파일 → backups/<시각>/
make restore FROM=backups/<시각> CONFIRM=yes   # 복구 (현재 데이터 덮어씀 · 그래프는 관리자 [온톨로지] 재투영)
make preflight   # 운영 준비 점검 · make host-check 서버 점검 · make a11y 자동 접근성 점검 · make set k=키 v=값 (.env 지정) · make es-password (Elasticsearch 401)
make upload-test # 업로드 기반 에이전트 시험 — 별도 스택(포트 3100)에 2026.09 시험 엑셀 · PDF 를 올려 워크플로우 · 에이전트 · mart 갱신 확인 후 내림 (LLM: E2E_LLM_BASE · E2E_LLM_KEY · E2E_LLM_MODEL 환경변수, 없으면 규칙 경로 판정 · E2E_EXPECT_LLM=0/1)
```

**내 자료로 시작하기(기본)** — `make up` 은 정의(데이터셋 · 지표 · 규칙 · 워크플로우)만 시드하고 업무 자료는 넣지 않습니다. 화면은 자료가 올라오기 전까지 "미제공"으로 보이고, 관리자 `/admin/datasets`(또는 업무 `/knowledge/upload`)에서 직접 올리면 관련 워크플로우만 계산합니다. 시연 자료가 필요하면 `make sample`(43개 파일 업로드) 또는 `.env` 에 `LOAD_SAMPLE_ON_START=1`(`make set k=LOAD_SAMPLE_ON_START v=1`). **이미 시연 자료가 올라간 DB 를 비우려면** `make reset`(볼륨까지 삭제 — 되돌릴 수 없음) 후 `make up`. 기존 `.env` 에 `LOAD_SAMPLE_ON_START=1` 이 있으면 먼저 `make set k=LOAD_SAMPLE_ON_START v=0`.

| 서비스 | 주소 | 역할 |
|---|---|---|
| web | http://localhost:3000 | 로그인 · 업무 화면 · 관리자(`/admin`) — `/backend/*` 를 api 로 프록시 |
| api | http://localhost:8000/health | 인증 · 화면 API · 상태 API · 관리자 API (문서 `/docs` 는 `API_DOCS=true` 일 때) |
| worker | - | 아웃박스 디스패처 · 워크플로우 엔진 · 임베딩 · 문서 구조화 · 그래프 투영 |
| postgres | (내부) | 원장 · 설정 · 계산 이력 · pgvector(임베딩 값) · 작업 큐 |
| elasticsearch | 127.0.0.1:9200 | 검색 엔진 — 분석 결과 · 문서 색인(nori 형태소 + 온톨로지 별칭 사용자 사전 · kNN). 원장에서 다시 만들 수 있음(`kb-es --rebuild`), 꺼지면 검색은 PostgreSQL 로 축소 동작. 호스트 `vm.max_map_count ≥ 262144` |
| neo4j | http://localhost:7474 | 온톨로지 그래프(투영) |
| (LLM) | 외부 LiteLLM | 관리자 `/admin/llm` 에서 주소 · 키 · 모델 입력. 내장 게이트웨이가 필요하면 `.env` 에 `COMPOSE_PROFILES=litellm`(선택) |
| files-init | - | 기동 때 한 번 실행하고 끝나는 준비 단계 — 파일 저장소 볼륨을 api · worker 계정이 쓸 수 있게 권한 정리(업무 자료 요청 파일 · 업로드 원본). `make preflight` 의 '파일 저장소' 항목으로 확인 |

**처음 사용 순서**
1. 관리자 계정으로 로그인 → `/admin/llm` 의 **LiteLLM 연결 (간단 설정)** 에 외부 LiteLLM 주소 · API 키 · 모델을 넣고 [저장하고 연결 확인](모델 목록에서 골라도 됨).
   LLM 이 설정되지 않아도 모든 수치·화면은 동작하며, 서술 노드만 기존 문장으로 폴백(degraded)합니다.
2. 사용자는 `/signup` 에서 사번 8자리 + 소속(본부 > 부 > 국 > 팀 또는 지역본부 > 영업점)으로 가입 → 관리자가 `/admin/users` 에서 승인.
3. 화면 권한은 `/admin/screens` 에서 조직 단위로 부여합니다(하위 조직이 상속). 기본: 종합기획부 · 신용리스크관리부 · 수도권1지역본부 · 중부지역본부(영업점 포함).
4. 실데이터는 `/admin/datasets` 에서 업로드(당행/외부 구분 확인) → 품질 검증 → 확정 시 관련 워크플로우만 재계산. 시연 자료 원본은 `sample-data/202608/`(직접 열어 보고 화면에서 올려도 같은 결과).
5. 잘못 올린 자료는 **데이터 관리자**(관리자 중 `/admin/users` 에서 지정 — 부트스트랩 관리자는 처음부터)가 `/admin/datasets` 의 버전 · 문서 표에서 [삭제]합니다. 삭제 사유를 받고, 현재 버전이면 직전 버전이 현재가 되며, 행 · 청크(임베딩) · 원본 파일과 검색 색인(Elasticsearch) · 그래프(Neo4j)에서도 지웁니다(저장소가 멈춰 있으면 워커가 끝날 때까지 재시도 — '삭제 반영 상태'). 부서 데이터 책임자는 [자료 올리기 > 우리 부서 자료]에서 **자기 부서가 올려 승인된 자료만** 같은 방식으로 지웁니다. 문서를 지우면 AI 호출 기록 · 실행 기록 · 보고서 근거에 복사된 본문 조각도 정리하고(토큰 · 비용 같은 기록은 유지), 데이터셋을 지우면 다시 계산이 끝난 뒤 옛 산출물 세대를 정리합니다(계산 기록 · 감사 로그는 지우지 않음).

시연용 사용자(선택): `.env` 에 `DEMO_USER_PASSWORD` 를 넣고 최초 기동하면 20250001(종합기획부) · 20250002(신용리스크관리부) · 20250003(영업점 · 수원영통지점 001068)이 생성됩니다.

**프론트만 (도커 없이)**: `make web-dev` → http://localhost:3000 — 백엔드 API(`API_INTERNAL_URL`, 기본 http://localhost:8000)가 떠 있어야 하고 로그인이 필요합니다.

---

## 서버 배포 (아마존 리눅스 2023 · EC2)
권장 사양: 메모리 8GB 이상(t3.large · 부족하면 스왑 4GB), 디스크 30GB 이상, x86 · Graviton 모두 가능. 이미지 · 패키지를 받기 위해 서버에서 인터넷으로 나가는 연결이 필요합니다.

```bash
# 1) 도구 — docker · git · make (설치 후 다시 로그인하거나 newgrp docker)
sudo dnf install -y docker git make openssl && sudo systemctl enable --now docker && sudo usermod -aG docker $USER && newgrp docker

# 2) compose · buildx 플러그인 (아마존 리눅스 저장소에는 없음 — compose 2.30 이상은 buildx 0.17 이상 필요)
ARCH=$(uname -m); BX=$([ "$ARCH" = aarch64 ] && echo arm64 || echo amd64)
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -fSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$ARCH -o /usr/local/lib/docker/cli-plugins/docker-compose
mkdir -p ~/.docker/cli-plugins && curl -fSL https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-$BX -o ~/.docker/cli-plugins/docker-buildx
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose; chmod +x ~/.docker/cli-plugins/docker-buildx

# 3) 코드 받기 → 플랫폼 폴더로 (gogomovy 저장소는 nh-decision-platform/ 안)
git clone -b <브랜치> <저장소 주소> && cd <플랫폼 폴더>

# 4) 점검 → 기동
make host-check       # Docker · buildx 버전 · 메모리 · 디스크 · .env · 포트 · EC2 공인 IP — FAIL 이 있으면 안내된 명령 실행
make up               # .env 비밀값 생성 → 빌드(처음 10~20분) → 기동
make wait-idle && make ps      # 5개 모두 (healthy)
make admin-pass       # 최초 관리자 사번 · 비밀번호
make preflight        # 운영 준비 점검 (관리자 [시스템 상태] 에도 표시)
```

**외부 접속**
- 웹만 외부에 열립니다(api · Neo4j 는 서버 안에서만). 서버에서 외부 LiteLLM 주소로 나갈 수 있어야 합니다(보안 그룹 아웃바운드 · 방화벽). 80 포트로 열려면 `make set k=WEB_PORT v=80 && make up` 후 EC2 보안 그룹 인바운드에 `TCP 80` 을 추가하고 `http://<공인 IP>` 로 접속합니다.
- `.env` 값은 `make set k=<키> v=<값>` 으로 바꿉니다. `echo ... >> .env` 로 추가하면 같은 키가 두 줄이 되어 어느 값이 쓰일지 알 수 없습니다(`make host-check` 가 찾아 줍니다).
- 서버 안에서는 열리는데 밖에서 안 되면: 보안 그룹 인바운드(포트 · 소스) → 서브넷 라우팅 테이블에 `0.0.0.0/0 → igw-…` 경로 → 네트워크 ACL → 내 쪽 회사망이 해당 포트를 막는지(휴대폰 핫스팟으로 확인) 순서로 봅니다. 외부 인바운드가 막힌 VPC 라면 SSH · SSM 터널을 씁니다.
  ```bash
  ssh -i <키.pem> -L 3000:localhost:3000 ec2-user@<서버 IP>          # → 내 PC 에서 http://localhost:3000
  aws ssm start-session --target <인스턴스 ID> --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
  ```
- 도메인 + HTTPS(ALB · nginx 뒤): `make set k=COOKIE_SECURE v=1`, `make set k=TRUSTED_ORIGINS v=https://<도메인>`, 앞단 프록시가 X-Forwarded-For 를 채우면 `make set k=TRUST_UPSTREAM_PROXY v=1` · `make set k=TRUSTED_PROXY_HOPS v=2` 후 `make up`.

**운영**
- 관리자 비밀번호: 관리자 [사용자] 의 [비밀번호], 잊었거나 잠겼으면 `echo '새비밀번호123' | docker compose exec -T api python -m nhdip.cli admin-password 00000001` (8자 이상 · 영문 + 숫자).
- 백업은 매일 권장 — `crontab -e` 에 `0 2 * * * cd <플랫폼 폴더> && make backup >> backups/cron.log 2>&1` (최근 14개 보관, `BACKUP_KEEP`). 복구는 `make restore FROM=backups/<시각> CONFIRM=yes`.
- 최신 코드: `git pull && make up`. 서버를 재부팅해도 Docker · 컨테이너가 자동으로 다시 뜹니다.

---
## 2. 데이터 흐름

```
업로드(당행 bank.* / 외부 ext.*) ─ 품질 검증 ─ 버전 확정 + outbox 이벤트 (한 트랜잭션)
   └→ worker: 트리거 ∪ 계보(지표·바인딩이 참조하는 데이터셋) 매칭 → 관련 워크플로우만 작업 생성(디바운스 병합)
        load_inputs → compute_metrics(계산 커널, calc_run 기록) → judge(규칙) → build_views(화면 수치·표·차트)
        → detect_changes(변화 감지) → plan_run(플래너) → retrieve_evidence(그래프 필터 → Elasticsearch 키워드 · 의미(없으면 PostgreSQL) RRF) → narrate(LLM, [[fig:ID]] 마커만) → critic → publish(새 세대)
   (오케스트레이터: 상위 워크플로우 — 그래프 투영 · 참조 지표 — 가 끝난 뒤 하위 실행)
문서 업로드 → 청크 → 임베딩 → LLM 구조화(스키마 검증, 실패분 검토 대기 · LLM 미설정 시 별칭 규칙) → Neo4j 투영
```

- 수치는 모두 계산 커널(decimal · numpy · scipy · scikit-learn)이 계산합니다. LLM 은 계산하지 않습니다.
- 지표 정의(`/admin/metrics`) · 규칙(`/admin/rules`) · 트리거/노드(`/admin/workflows`) · 데이터셋 정의(`/admin/datasets`) · 온톨로지(`/admin/ontology`) · LLM(`/admin/llm`, `/admin/agents`) 은 모두 관리자 화면에서 바꿉니다.
- 컬럼 정의서: 종기부 컬럼정의서(T01 현황 · T02 데이터분석 · T03 목표설정)를 `/admin/contracts` 에 올리면 컬럼을 지표·서술에 연결해 `mart.hq_t01~t03` 에 적재하고, 정의서 화면값과 계산값을 대조합니다(일치 · 불일치 · 미연결).
- 정기 실행: 워크플로우별 cron 트리거(기본 06:00 · 06:10 · 06:20 KST, `/admin/workflows`)가 데이터 변경과 같은 경로로 재계산합니다.
- 질의: 업무 화면 우측 하단 `질문하기` — 권한 범위의 확정 수치(커널)와 근거 문서로만 답하고, 답변 숫자의 출처를 검증합니다. LLM 미연결 시 수치·근거만 보여줍니다.
- 질문하기 지식 색인(Phase D): 게시된 분석 결과(인사이트 · 보고서 · 카드 · 목표 · 수행방안 등)를 `app.kb_chunk` 에 색인하고, 팀별 컬렉션(담당 · 공유 팀 · 공개 범위 · 화면 권한 · 지점 범위)으로 나눠 사용자마다 볼 수 있는 것만 검색합니다(키워드 · 의미 · 개념 그래프 3채널 + 가중 RRF). 관리자 `/admin/knowledge`(색인 상태 · 컬렉션 편집 · 사용자 관점 검색 진단 · 전체 재색인), 임베딩 모델 확정 후 `python -m nhdip.cli kb-hnsw --dim <차원>` 한 번.
- 판단 에이전트(LLM): 오케스트레이터(이벤트마다 영향받는 워크플로우 추가 · 실행 순서 보장) · 변화 감지(커널이 계산한 변화의 업무상 중요도 판단 → '최근 감지된 변화') · 플래너(서술 대상 · 근거 검색어 · 후속 워크플로우 결정). LLM 판단은 허용 목록으로 검증하고 미연결 · 실패 시 규칙(`CHANGE_SIGNIFICANCE` · `PLANNER_POLICY` · `orchestrator.policy`)으로 대체. 결정 · 판단 주체 · 근거는 `/admin/monitor/agents`, 프롬프트는 `/admin/agents`.
- 모니터링: `/admin/monitor/flow`(이벤트 → 매칭 사유 → 실행 → 게시) · `/admin/monitor/runs`(노드 입출력 · LLM 원문 · 계산) · `/admin/monitor/calc`(지표 값 · 추이 · 산출물 세대) · `/admin/monitor/agents`(에이전트 결정) · `/admin/monitor/trace`(요청 추적) · `/admin/monitor/evals`(골든셋) · `/admin/monitor/alerts`(운영 알림 · LLM 비용).
- 관리자 화면 묶음(Phase C): 관리자 홈(`/admin` — 처리할 일 · 시스템 상태 · 24시간 실행) · 사용자와 권한 · 데이터와 지식(자료 승인 `/admin/uploads` 포함) · AI · 에이전트(분석 에이전트 `/admin/analysis-agents` 포함) · 계산과 규칙(운영 설정 `/admin/settings`) · 운영 모니터링(운영 개요 `/admin/monitor` — 시간대별 실행 · LLM · 이벤트 그래프, 그래프마다 '표로 보기'). 화면마다 위치 표시 · 요약 수치, 원본 JSON 은 '고급' 접기 안.
- 업무 자료 올리기: 화면 권한 `자료 올리기`(기본 종합기획부 · 신용리스크관리부)를 받은 사용자는 `/knowledge/upload` 에서 정형 자료(기존 데이터셋의 새 버전)나 문서를 올립니다. 올리는 즉시 보안 · 형식 · 품질 검사를 하고(품질 실패는 요청 거절) '승인 대기' 로 남으며, 관리자(`/admin/uploads`)나 **부서 데이터 책임자**(관리자가 [사용자]에서 지정 — 자기 부서 사용자의 요청을 [자료 올리기 > 승인할 자료]에서 처리, 본인 요청은 불가)가 승인하면 관리자 직접 업로드와 같은 경로로 확정 · 재계산합니다. 올릴 수 있는 대상은 설정 `upload.user_targets`. 첫 단계는 파일 놓기 영역이고, 파일 이름(이름 규칙 · 보고서 번호 · 코드 · 낱말)으로 맞는 자료를 골라 두면 사용자가 확인합니다(Phase E · Q121). [데이터베이스] 표의 '새 버전 올리기' 는 `/knowledge/upload?target=<데이터셋 코드>` 로 그 자료를 고른 채 엽니다. 관리자 `/admin/datasets` 는 맨 위 '파일로 업로드' 에 놓으면 맞는 데이터셋 상세가 파일이 채워진 채 열립니다(즉시 확정은 확인 대화상자).
- 새 종류 자료 · 한 장 PDF(Phase J 후속 · 설계 §28): 맞는 데이터셋이 없는 파일은 거절하지 않고 머리글 · 값으로 **정의 초안**(열 이름 · 타입 · 키 · 기준일)을 만들어 보여 줍니다. 업무 사용자는 [자료 올리기]에서 확인 · 수정해 등록을 요청하고(설정 `upload.user_targets.new_datasets`), 책임자 또는 관리자가 승인하면 데이터셋이 만들어지고 그 파일이 첫 버전이 됩니다. 관리자는 `/admin/datasets` 에서 [이 파일로 새 데이터셋 만들기], 정의에 없어 저장되지 않는 열은 [파일에서 새 열 찾기]로 선택 열에 더합니다. 머리말 [내보내기]는 화면 내용 크기의 **PDF 한 장**(스크롤 표 · 접은 이슈 펼침 · 시뮬레이션 고지 유지)을 만듭니다 — 인쇄 창에서 "PDF로 저장". `UPLOAD_AV_COMMAND` 를 설정했는데 실행할 수 없으면 검사 없이 받지 않고 업로드를 거절합니다.
- 3-way 검색(Phase H · 설계 §24): PostgreSQL = 원장 · 권한 판정 · 임베딩 값, Elasticsearch = AI 어시스턴트 · 워크플로 근거 검색의 키워드(BM25 + nori + 온톨로지 별칭 사용자 사전) · 의미(kNN) — 분석 결과 · 문서(현재 판) 색인 두 개, Neo4j = 개념 그래프. ES 후보는 PostgreSQL 에서 접근 규칙으로 다시 걸러 읽고(권한 누수 0), 워커가 1분마다 동기화(아직 못 올린 새 청크는 PostgreSQL 이 보충), ES 가 없거나 안 되면 같은 채널을 PostgreSQL 로. 검색 설정 `knowledge.search.backend` 기본 `auto` · 점검 `python -m nhdip.cli kb-es --check` · 관리자 [AI 어시스턴트 색인]의 3-way 구성 카드. 이전 `.env` 의 `ES_URL=` 이 비어 있으면 `bash infra/scripts/set-env.sh ES_URL http://elasticsearch:9200`.
- 온톨로지 구성 지도(Phase G): 관리자 `/admin/ontology` 첫 탭 — PostgreSQL 원장에서 Neo4j 투영과 같은 코드(`graph/projection.collect_graph`)로 개체 · 관계를 모아 3D 군집 지도(Louvain 군집 · 서버 결정적 배치 · 회전 · 확대 · 2D) · 구조도(클래스 ↔ 관계 유형) · 표로 보여 줍니다. Neo4j 가 없어도 동작(`GET /admin/ontology/map?limit=&classes=&refresh=`).
- 관리자 내비게이션(Phase E · Q122): 관리자의 첫 화면은 `/admin`, 사이드바는 관리 묶음 먼저(가입 · 자료 · 분석 승인 대기 건수 — `/me/menu` 의 `adminUsers` · `adminUploads` · `adminAnalyses` · `adminTodo`) · 업무 화면은 접힘 묶음. 되돌리기 어려운 작업은 앱 확인 대화상자(`useConfirm`, 초점 = 취소 · Esc). 권한 없음 화면은 요청한 화면 이름 · 메뉴 위치 · 요청 방법을 보입니다(`GET /me/screen?path=`).
- 분석 에이전트(부서 맞춤 분석): 화면 권한 `분석 에이전트 만들기`를 받은 사용자가 `/analysis/builder` 에서 도메인 지식 · 하고 싶은 분석을 글로 적으면 ① 정제 에이전트(LLM, 미연결 시 규칙)가 분석 명세(데이터 · 커널 수식 · 표 · 보고서 구성 · 의견 지시)로 정리하고 허용 목록으로 검증 → 미리보기(실제 계산, 저장 안 함) → 승인 요청. 관리자가 `/admin/analysis-agents` 에서 승인하면 지표(`dyn_*`) · 워크플로(`wf_an_*`) · 그 분석 전용 에이전트(`an_*`) · 트리거가 만들어지고, 실행마다 계산 커널 → ② 동적 수행 에이전트(판단 · 서술, 수치는 마커만) → ③ 범용 렌더링(결정론) → 검증 → 게시. 승인은 관리자만 하며, 승인하면서 실행 주기(cron) · 자료가 바뀌면 다시 계산 · LLM 의견 작성 여부를 정합니다. 결과는 그 부서의 **기존 분석 화면에 '맞춤' 탭**으로 나타납니다(신용리스크 [분석 결과] `/risk/analysis/<탭>`, 종합기획부 [데이터 분석] 탭 줄 `/hq/analysis/<탭>`). 기존 화면이 없는 새 부서는 설정 `analysis.spaces` + `POST /admin/screens` 로 코드 변경 없이 추가. 실 LLM 시험: `apps/e2e/analysis-agents-llm.mjs`(E2E_LLM_BASE · E2E_LLM_KEY · E2E_LLM_MODEL).
- 파이프라인: `/admin/pipeline` — 원천(데이터셋 · 문서 · 규칙) → 워크플로 노드 · 에이전트 → 산출물 → 화면 연결을 DB 정의에서 그린 지도와 이벤트 흐름.
- 다지점 영업점: 규칙 `BRANCH_SCOPE.office_codes`(`/admin/rules`)에 사무소 코드를 더하고 그 지점 자료(`BRANCH_OFFICE_MASTER` · `BRANCH_KPI_SCORE` · `BRANCH_BIZ_BALANCE`)를 올리면 같은 지표 정의로 지점마다 계산합니다. 지역본부 · 관리자 화면에는 지점 선택 상자가 나오고(`/branch?office=<코드>`), 영업점 직원은 자기 지점만 봅니다. 자료가 없는 지점은 '준비 중', 지점 수 상한 · LLM 을 쓸 지점 수는 설정 `workflow.scopes`(`max` · `narrate_max`).
- 화면 설정(Phase K · 설계 §27): 화면 코드에 두던 판정 구간(한도 · 신용RWA 소진율 · 본부 전파 목표 진행률 · 근거 관련도) · 기준값(계획 수준 허용 폭 · 한도 여유 경고 · 구성비 기준선 · 제안 사유 최소 글자 수) · 화면이 집어 쓰는 목표(역할 → 목표 id) · 업무 영역(종기부 · 사업부서 · 영업점 이름과 단위 = 조직 + 메뉴 묶음) · AI 어시스턴트 예시 질문 · 알림 목록 · 주요 이슈 순서 · 하위 영역 표시 이름은 관리자 `/admin/ui` 에서 바꿉니다(설정 `ui.*`, 저장 전 형식 검사 · 감사). 화면은 `/me/menu.config` 로 받아 쓰고, 화면 코드에 다시 연도 · 반기 문구 · 목표 id · 판정 숫자를 넣으면 시험(`apps/web/src/lib/hardcode.test.ts`)이 실패합니다.
- 업무 영역 전환(Phase K): 헤더의 영역 칸에서 사업부서 · 영업점 지점이 둘 이상이면 눌러서 고릅니다(화면이 아직 없는 부서는 '준비 중'). 새 부서는 [화면 권한]에서 화면을 등록(묶음 = 부서 이름) → [화면 설정 › 업무 영역]에 한 줄. 빨간 점(레드닷)은 확인하지 않은 새 이슈 · 분석에만 붙고, 열면 사라지며 내용이 바뀌면 다시 뜹니다(사용자별 브라우저 기록). 화면이 열릴 때 막대 · 선 · 게이지 · 수치에 등장 효과가 있고, OS 의 '동작 줄이기'를 켜면 없습니다.
- Elasticsearch 인증 실패(HTTP 401 · `unable to authenticate user [elastic]`): ES 는 `.env` 의 `ES_PASSWORD` 를 볼륨을 처음 만들 때만 씁니다. `.env` 를 다시 만들었거나 볼륨이 먼저 있었다면 `make es-password` 로 볼륨의 elastic 비밀번호를 `.env` 값으로 맞춥니다(데이터 유지 · 임시 관리 계정으로 바꾸고 지움 · api · worker 재시작). 외부 ES 이거나 비밀번호를 알면 관리자 [AI 어시스턴트 색인 › Elasticsearch 연결]에서 주소 · 계정 · 비밀번호를 입력 · 시험 · 저장합니다(암호화 저장 · 환경변수보다 우선 · 지우면 환경변수로).

---

## 3. 화면 흐름

| 부서 | 경로 |
|---|---|
| 종합기획부 | `/hq/overview` 현황·목표 → `/hq/analysis` 데이터 분석 → `/hq/goals` 경영목표 설정 · 참고 `/hq/initiatives` `/hq/capital` |
| 신용리스크관리부 | `/risk` 현황 → `/risk/analysis/[tabKey]` 분석 결과(보고서) → `/risk/guides` 수행방안 |
| 영업점 | `/branch` 현황(업적평가 득점 · 기준 변경 알림 · 사업부문) → `/branch/analysis/[tabKey]` 영업 가이드 보고서(우량기업여신 · 서민금융) · 참고 `/branch/targets` 본부 전파 목표·가이드 |
| 공통 | `/knowledge` 데이터베이스(문서·데이터셋·용어집) · `/knowledge/upload` 자료 올리기(승인 요청 · 내 요청) · `/analysis/builder` 분석 에이전트 만들기(정제 → 확인 · 수정 → 미리보기 → 승인 요청 · 내 분석) |

경영목표 처리(유지·반영·직접 수정·신설)와 진행사업 등록·영업점 전파는 서버 상태로 저장되어 모든 사용자에게 공유되고, 목표 확정은 `goal.confirmed` · `rule.changed` 이벤트로 관련 수치를 다시 계산합니다.

---

## 4. 구조

```
apps/
├─ web/src/
│  ├─ app/              # 업무 화면 · login · signup · forbidden · admin/*
│  ├─ components/       # ui · layout · data · evidence · domain · providers · admin(kit) · auth
│  ├─ lib/              # data.ts(백엔드 화면 API) · api-server · api-client · terms · types
│  └─ proxy.ts          # (Next 16 proxy) 세션 쿠키 없으면 /login
├─ e2e/              # 브라우저 E2E (puppeteer) — make e2e
└─ api/src/nhdip/
   ├─ models/           # iam · cfg · bank/ext(source) · calc/app/ops/audit(runtime)
   ├─ calc/             # 수식 레지스트리 · 커널 · 지표 평가
   ├─ data/             # 데이터셋 적재·품질·버전·롤백 · 문서 적재
   ├─ graph/            # Neo4j 투영 · LLM 구조화+검증 · 하이브리드 검색
   ├─ llm/              # LiteLLM 클라이언트 (에이전트별 설정 · 호출 기록)
   ├─ workflow/         # 엔진 · 노드 구현 · 디스패처
   ├─ views/            # 화면 산출물 저장(세대) · 표/차트 빌더
   ├─ api/              # auth · screens · state · admin
   ├─ sample/           # 시연 자료 패키지 생성기(시나리오 → 실무형 엑셀 · 원본 양식 · PDF) · 업로드 · 엑셀 대조 · 교란 검사
   └─ seed/             # 초기 설정 · 데이터 정의(업무 수치 없음) · screens/*.json(수치 없는 화면 템플릿 + 서식 문구)
sample-data/202608/  시연 자료 패키지 저장소 사본(생성기와 같은지 CI 가 확인)
infra/  postgres init · litellm config · scripts(ensure-env 등)
.github/workflows/ci.yml  pytest · tsc · eslint · build · audit · e2e
```

화면 수치 · 기간은 업로드 자료에서만 옵니다. 시연 자료 패키지는 `python -m nhdip.cli load-sample`(api 컨테이너 안) 또는 `python -m nhdip.sample upload --base-url URL --user 사번`(업로드 API 경유)으로 올립니다. 하드코딩 검사는 `python -m nhdip.sample selftest`(빈 DB — 정의 시드 → 업로드 → 엑셀 대조 → 셀마다 다른 비율로 바꾼 패키지 두 벌 업로드 → 그대로인 데이터 자리 0 이어야 통과, CI api 잡).

---

## 5. 보안 메모

- 비밀번호 bcrypt · 세션은 서명된 HttpOnly 쿠키 + DB 세션(즉시 폐기) · 5회 실패 시 잠금 · 가입은 승인제
- LLM 키는 AES-GCM 암호화 저장(`CONFIG_ENC_KEY`), 화면에는 마스킹. `.env` 는 커밋하지 않습니다.
- api(8000) · neo4j(7474/7687) · (선택) litellm(4000) 포트는 기본으로 이 컴퓨터(127.0.0.1)에서만 열립니다(`ADMIN_BIND`). web 은 `WEB_BIND`(기본 0.0.0.0). HTTPS 환경이면 `COOKIE_SECURE=1`(HSTS 포함).
- api 는 데이터 조작만 가능한 DB 계정(`nhdip_app`, 비밀번호 `APP_DB_PASSWORD`)으로 접속해 감사 로그를 고치거나 지울 수 없습니다. 마이그레이션 · 시드 · 워커는 소유자 계정. 비우면 이전 방식.
- 속도 제한은 DB 에서 함께 셉니다(API 여러 개 가능). 사용자 IP 는 앞단 프록시(`TRUSTED_PROXIES`)가 넘긴 X-Forwarded-For 로 판정합니다. 화면은 요청마다 nonce 를 쓰는 CSP 로 스크립트를 제한합니다.
- 변경 요청(POST 등)은 같은 출처만 받습니다. 다른 주소(리버스 프록시 · 도메인)로 서비스하면 `TRUSTED_ORIGINS=https://<웹 주소>` 를 넣으세요. 운영(`NHDIP_ENV=prod`)에서는 기본 · 짧은 `SESSION_SECRET` 으로 기동하지 않습니다.
- 로그인 · 가입 · 질의 속도 제한(설정 `auth.rate_limits`), 잠금은 30분 뒤 자동 해제(`auth.lockout_minutes`, 0 = 관리자만). 보안 헤더(CSP · X-Frame-Options 등)는 web · api 모두 붙습니다.
- 개인정보: 적재할 데이터에 주민등록번호 · 휴대전화 · 이메일 · 카드번호 형식 값이 있으면 품질 검증에서 거부하고, 차주명은 화면에서 가립니다(설정 `privacy.policy`). LLM 호출 기록에도 같은 형식 값을 가려 저장합니다.
- 통제(선택): 규칙 이중 승인 `governance.dual_control`, 자동 실행 사람 승인 `orchestrator.policy.require_approval`(관리자 [에이전트 결정]에서 승인 · 반려). 운영 기록 보관 기간은 `retention.policy`(감사 로그는 정리하지 않음).
- SSO(선택): `.env` 의 `OIDC_ISSUER` · `OIDC_CLIENT_ID` · `OIDC_CLIENT_SECRET` · `OIDC_REDIRECT_URI`(`https://<웹 주소>/backend/auth/oidc/callback`) 를 넣으면 로그인 화면에 SSO 버튼이 생깁니다. 사번은 `OIDC_EMP_CLAIM` 클레임으로 기존 사용자와 연결하고 자동 가입은 하지 않습니다. 전환 후에는 `OIDC_LOCAL_LOGIN=admin`(관리자 비상 로그인만) 을 권장합니다.
- 업로드는 파싱 전에 형식 · 압축 폭탄 · 매크로 · PDF 스크립트 · DRM 을 검사합니다. 백신을 쓰려면 `UPLOAD_AV_COMMAND`(예: `clamdscan --no-summary {path}`).
- 모든 API 응답에 `X-Trace-Id` 가 붙습니다. 오류 문의 시 이 값을 관리자 [요청 추적] 화면에 넣으면 요청 → 워커 실행 → DB 구간까지 볼 수 있습니다.
- 운영 알림(선택): 관리자 [운영 알림 · 비용]에서 켜고, 채널은 `.env` 의 `ALERT_WEBHOOK_URL` · `ALERT_SMTP_*` 로 지정합니다. LLM 월 예산 · 단가는 설정 `llm.budget` · `llm.pricing`.
- 품질 점검: `make eval`(골든셋 — 기준값 · 판정 · 화면 · 서술 출처 · 검색 · 질의) · `make perf`(주요 API p95 기준치).

---

## 6. 시연 자료 기준값 (시나리오 정의 반영 · 시연 자료 패키지를 올린 뒤의 값)

| 항목 | 값 |
|---|---|
| 분석 기준일 | 2026-08-31 |
| 소기업 6B 등급 | 실제부도율 **7.929%** / 예측 대표값 **7.733%** / 최대값 **8.933%** → 대표값 초과·최대값 이내 |
| 소기업 모형 | PSI 0.082(관찰) · AR 49.62% · AR 하락률 23.8% · χ² **20.47** < 임계 21.03 (목데이터 수기값 18.42 → 커널 계산값으로 교체) |
| 소매 모형 | AS모형 AR 35.52%(하락률 34.7%) · BS모형 AR 83.84%(하락률 2.06%) |
| 포용금융 충당금 비중 | 2026.01 **7.97%** → 2026.08 **9.16%** (+1.19%p, +14.9%) → 주의 |
| 포용금융 상품코드 | 새희망홀씨 6 · 햇살론 13 · 사잇돌 2 = **21건** 전건 매칭 |
| 기업여신 | 115.34조원 · +4.04% (목표 +7.0% 대비 −2.96%p) |
| 가계여신 | 99.24조원 · +6.50% (관리목표 +4.0% 이하 초과, 잔액 한도 99.2% 소진) |
| 지주 한도 | 총자산 최대 증가율 8.2% · RWA 순증 12.4조 · 은행 목표 7.4%(여유 0.8%p) |
| 목표 추천 | 기업 +7.5~8.0% 상향 / 가계 +3.0~3.5% 이하 하향 / 포용금융 3.1~3.3조 신설 |

| 영업점(수원영통지점) | 업적평가 593.7 / 1,000점 · 지점 평균 등급 8.39(전행 6.16, 1~16) · 소기업 비중 12.7%(전행 4.4%) → 본부 추천 후보 5개 · 140억원 유치 시 평균 7.87 · 우량기업여신 +14.0점 |
| 영업점 서민금융 | 지점 비중 0.45%(전행 2.14%) · 권고 19건 · 427백만원(충당금 허용 범위 적용) · +12.7점 · 추가 충당금 20.0백만원 |

모든 시뮬레이션 수치는 화면에서 `시뮬레이션 데이터` 배지로 구분됩니다. 영업점 배점 · 가중치 · 선정 기준 · 한도는 업적평가 세부기준 원본 수령 전 시뮬레이션 가정(규칙 `BRANCH_*`)입니다.

---

## 7. 접근성·품질

- 키보드만으로 근거·계산추적·용어 도움말 접근 가능 (`focus-visible` 링 유지)
- 모든 차트에 `role="img"` + aria-label + **표로 보기** 토글
- 숫자 `tabular-nums` 고정폭, 금액 단위 라벨 상시 표기
- 하드코딩 색상·폰트 금지 — `tokens.generated.css` 변수만 사용
- Optimistic VF 는 한글 글리프가 없어 Pretendard 폴백(폐쇄망에서는 system 폰트로 자동 대체)
