# 종합기획부 Persona — 요구사항 확인 질문

아래 두 문서를 이미 읽었고, 기획안에서 **명시적으로 고정된 내용은 다시 묻지 않습니다.**

- `AX프런티어 AI Agent 프로젝트 제품 정의서.md`
- `종합기획부 Persona 상세 기획 & 개발 요건.md`

각 질문의 `[Answer]:` 뒤에 선택 글자를 적어 주세요. 보기가 맞지 않으면 `X`를 고르고 설명을 적으면 됩니다. 여러 보기를 함께 골라도 됩니다. 다 채운 뒤 채팅에서 **답변을 채웠으니 파일을 다시 읽고 진행해 달라**고 알려 주세요.

---

## 이미 기획안에서 확정으로 받아들인 사항

- 이번 제품의 사용자: 종합기획부 Persona
- 핵심 루프: MONITOR → INTERPRET → SET DIRECTION → PROPAGATE
- 상위 화면 3개: 은행 Dashboard / 경영목표 설정 / 데이터베이스
- Journey A~D와 MUST 기능 목록
- Dashboard First, Proactive Agent, Evidence First, Traceability, Unsupported Causality 금지
- Agent 근거 3종: 당행 정형 Data / 내부 경영 의사결정 / 외부 정책·환경
- 여신만 상세 구현, 나머지 사업부문은 세계관 카드
- 여신 상세 3영역: 종합수익 / 기업여신 / 가계여신
- 목표 수치는 LLM이 임의 생성하지 않음
- 실제 인증·결재·전사 시스템 연동·전 사업부문 상세는 Prototype 범위 밖
- 당행 화면·보고문서·사업계획이 오기 전에는 Mock Data / Sample Logic 사용 가능
- UI 세부 디자인(배치, 차트 종류, 버튼 위치 등)은 이번 단계에서 고정하지 않음

---

## Question 1
이번 Inception으로 만드는 제품의 범위를 어떻게 둘까요?

A) 종합기획부 Journey A~D와 MUST 항목만. 신용리스크관리부·영업점 화면은 이번 범위에 넣지 않는다

B) 종합기획부 MUST + Journey D를 위해 사업부서용 최소 수신 화면(확정된 경영목표를 보여주는 stub)까지 포함한다

C) 종합기획부 MUST와 SHOULD를 모두 이번 범위에 넣는다. 다른 Persona 화면은 넣지 않는다

X) Other (please describe after [Answer]: tag below)

[Answer]: C. 그러나 이후에 신용리스크관리부 & 영업점 화면이 자연스럽게 연결 될 수 있도록 구조를 구성했으면 좋겠음.

---

## Question 2
Journey D(확정 경영목표를 사업부서 판단 기준으로 전파)를 이번 Prototype에서 어떻게 증명할까요? 본부 사업부서 Journey는 아직 없습니다.

A) 종합기획부에서 확정하면 저장만 한다. 사업부서 화면은 이후 Persona 기획에서 연결한다. 이번에는 저장 구조와 데이터 모델만 만든다

B) 사업부서용 최소 화면을 하나 만들어, 확정된 여신 경영목표가 표시되고 Agent가 그 목표를 기준으로 한 문단을 말하게 한다

C) 종합기획부 화면 안에서 ‘사업부서 반영 미리보기’를 제공해 전파를 보여 준다. 별도 사업부서 Persona 화면은 만들지 않는다

X) Other (please describe after [Answer]: tag below)

[Answer]: A.

---

## Question 3
Prototype에서 사용자는 어떻게 종합기획부로 들어가나요?

A) 로그인 없이 진입 시 Persona 선택 화면(종합기획부 / 신용리스크관리부 / 영업점). 이번 구현은 종합기획부만 실제 동작하고 나머지는 ‘이후 구현’으로 비활성화

B) 로그인 없이 종합기획부로 바로 진입. Persona 전환 UI는 두지 않는다

C) 간단한 Mock 로그인(아이디만 고르면 종합기획부 권한)을 만들고, 그 권한으로 은행 Dashboard에 들어간다

X) Other (please describe after [Answer]: tag below)

[Answer]: C.

---

## Question 4
화면 언어는 무엇으로 할까요?

A) 한국어 UI, Agent 응답도 한국어

B) 한국어 UI, 코드·식별자·문서 파일명은 영어

C) UI와 Agent 모두 한/영 전환 가능

X) Other (please describe after [Answer]: tag below)

[Answer]: C. 그러나 기본 설정은 한국어.

---

## Question 5
프론트엔드는 무엇으로 만들까요?

A) Next.js (React, App Router)

B) React SPA (Vite)

C) Vue 3

D) 이번 단계에서 고르지 않고, Construction의 NFR/기술스택 단계에서 결정한다

X) Other (please describe after [Answer]: tag below)

[Answer]: D. 나중에 전체 필요 기능이 확정되고 최선의 안으로 가면 됨

---

## Question 6
백엔드와 API는 어떻게 둘까요?

A) 프론트엔드와 같은 앱 안의 API(예: Next.js Route Handler). 별도 서버 프로세스 없음

B) 별도 백엔드(Python FastAPI)

C) 별도 백엔드(Node.js)

D) 이번 단계에서 고르지 않고 Construction에서 결정한다

X) Other (please describe after [Answer]: tag below)

[Answer]: D.

---

## Question 7
정형 데이터(여신 실적, 경영목표, 보고 요청)는 어디에 저장할까요?

A) 로컬 파일(JSON/SQLite)만. 외부 DB 없음

B) PostgreSQL

C) 프론트에서 보이는 Mock만 두고, 서버 영속 저장은 최소한(경영목표 확정 결과 정도)

D) 이번 단계에서 고르지 않고 Construction에서 결정한다

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question 8
Agent(해설, Attention, 목표 수정·신규 제안)의 LLM은 무엇으로 할까요?

A) AWS Bedrock

B) OpenAI API

C) Anthropic API

D) Prototype은 고정 템플릿 + 규칙 기반 해설을 기본으로 하고, LLM은 자연어 추가 질문에만 쓰거나 나중에 붙인다

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question 9
이번 Prototype의 실행 환경은 어디인가요?

A) 로컬 개발 서버만. 클라우드 배포는 하지 않는다

B) 로컬 개발 + 내부 데모용 단일 클라우드 배포(예: AWS)

C) 로컬만 우선. 배포 구성은 문서와 스크립트만 준비한다

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

## Question 10
Dashboard의 AI 주요 Attention은 어떻게 만들까요? (기획안은 Ranking Logic을 추후 구체화한다고 되어 있습니다)

A) 규칙 기반: 목표 대비 Gap, 전년 동분기 변화 등 정해진 조건으로 1~2개를 고른다. LLM은 문장만 다듬는다

B) LLM이 실적·목표·정책 요약을 읽고 Attention을 고른다. 다만 근거 데이터 ID를 반드시 붙인다

C) 데모용으로 시나리오에 맞춘 고정 Attention을 넣고, 선택 로직은 이후 교체 가능하게 분리한다

X) Other (please describe after [Answer]: tag below)

[Answer]: B. 다만 사업부문별로 Attention 생성해서 해당 카드 클릭 시 해당 사업부문 Attention이 나오도록.

---

## Question 11
기존 경영목표의 **수치 추천**(예: +7% → +8%)은 기획안의 GOAL-08 세 방식 중 이번 Prototype에서 무엇을 쓰나요?

A) 사전에 정의된 Rule에 따른 추천값

B) 범위 형태 추천(예: +7.5% ~ +8.0%)

C) 방향성만 제안하고 최종 수치는 사용자가 입력한다

D) A와 B를 함께: 방향 + 범위. 단일 확정 숫자는 사용자가 고른다

X) Other (please describe after [Answer]: tag below)

[Answer]: D

---

## Question 12
정부정책 DB의 HWP 업로드는 이번 Prototype에서 어떻게 할까요?

A) PDF와 텍스트 파일만 지원. HWP는 이후 과제로 명시한다

B) HWP도 받아 저장은 하지만, Agent가 읽는 것은 추출된 텍스트/요약 필드(사용자가 붙여 넣거나 사전 준비)

C) HWP 파싱까지 이번 범위에 넣는다

X) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Question 13
외부 최신 정책·기사(DB-08)는 이번 Prototype에서 어떻게 할까요?

A) 외부 검색은 하지 않는다. 정부정책 DB에 미리 넣어 둔 문서와 데모용 기사 메타데이터만 사용한다

B) 공식 출처 URL을 사용자가 등록하면 Agent가 그 문서만 근거로 쓴다. 실시간 웹 검색은 없다

C) 실시간 웹/보도자료 검색을 넣는다

X) Other (please describe after [Answer]: tag below)

[Answer]: C.

---

## Question 14
기획안 SHOULD 항목 중, MUST 외에 이번에 포함할 것을 고르세요. 여러 개면 글자를 같이 적으면 됩니다.

A) MUST만 구현한다. SHOULD는 요구사항에 ‘이후’로 남긴다

B) Dashboard Attention → 경영목표 검토 대상 바로 등록 (DASH-05)

C) 근거 원문 상세 Drill-down (DB-07 수준: 문서명·출처·날짜·참고 요약·원본 열기)

D) 문서별 사업부문 Tag

E) 목표 상태 표시(현재 적용 중 / AI 수정 제안 / 수정 검토 중)

F) 경영목표 변경 History

G) Agent에게 Dashboard 관련 자연어 추가질문

X) Other (please describe after [Answer]: tag below)

[Answer]: BCDEFG

---

## Question 15
당행 실제 화면·보고문서가 오기 전에 여신 종합수익/기업여신/가계여신 화면을 어느 깊이로 만들까요?

A) 기획안의 최소 비교(현재값, 전년 동분기, 증감액, 증감률, Agent 요약)와 데모용 Mock 지표만 구현한다. 실제 화면 복제는 자료 도착 후 한다

B) 일반적인 은행 여신 성과 화면을 가정한 중간 깊이 UI를 만들되, 지표 목록은 교체 가능하게 둔다

C) 실제 화면이 올 때까지 해당 상세 화면은 골격(제목, Agent 자리, 비교 테이블 자리)만 만들고 숫자는 Mock 한 줄만 둔다

X) Other (please describe after [Answer]: tag below)

[Answer]: X. B에서 제안한 대로 중간 깊이 UI를 만들되, 지표 목록은 내가 설명에 간단하게 적어준 대로 A에 있는 비교 기준들과 데모용 mock 지표를 만들어서 채워놔. 종합수익은 여신 분야의 종합수익 단일 값만 있다고 가정하고, 기업여신과 가계여신에 대한 세부 값과 기준들은 다시 한 번 따로 질문해주면 각각 상세하게 적어주려고 해.

---

## Question 16
애플리케이션 코드는 어디에 둘까요? `aidlc-docs/`와 `aidlc-workflows/`는 제품 코드 위치가 아닙니다.

A) 워크스페이스 루트에 `src/`, `tests/` 등 직접 생성

B) `app/` 디렉터리 아래에 프론트/서버를 둔다

C) 모노레포: `apps/web`, `apps/api`처럼 나눈다

X) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Question 17
Security extension 규칙을 이 프로젝트에 강제할까요?

A) Yes — 프로덕션급으로 SECURITY 규칙을 blocking constraint로 적용한다

B) No — PoC/Prototype이므로 SECURITY 규칙은 건너뛴다

X) Other (please describe after [Answer]: tag below)

[Answer]:B

---

## Question 18
Resiliency baseline을 적용할까요?

A) Yes — 설계 단계 가이드로 적용한다 (가용성 인증은 아님)

B) No — Prototype이므로 건너뛴다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 19
Property-Based Testing 규칙을 적용할까요?

A) Yes — 비즈니스 로직·데이터 변환에 PBT를 blocking으로 적용한다

B) Partial — 순수 함수와 직렬화 round-trip만

C) No — 건너뛴다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question 20
이번 Prototype의 데모 시나리오 데이터는 어떻게 준비할까요?

A) 기획안에 나온 예시(기업여신 목표 하회, 가계여신 상단 근접, 포용금융 신규 목표)를 재현하는 고정 Mock 세트를 코드에 넣는다

B) Mock을 넣되, 관리 화면에서 숫자·목표를 바꿔 다른 시나리오도 보여 줄 수 있게 한다

C) 빈 데이터로 시작하고 사용자가 업로드·입력한 것만 사용한다

X) Other (please describe after [Answer]: tag below)

[Answer]:B
