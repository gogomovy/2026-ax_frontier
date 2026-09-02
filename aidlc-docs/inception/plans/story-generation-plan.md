# Story Generation Plan

User Stories Part 1 — Planning. 요구사항은 승인됨: `aidlc-docs/inception/requirements/requirements.md`.

이 파일의 `[Answer]:`를 모두 채운 뒤 채팅에서 **답변을 채웠으니 다시 읽고 진행해 달라**고 해 주세요. 답을 검증하고 모호하면 추가 질문을 합니다. 그다음 이 계획을 승인한 뒤에만 `stories.md`와 `personas.md`를 만듭니다.

스토리 내용(무엇을 구현할지)은 요구사항에 이미 있습니다. 여기서는 **어떻게 자를지, 어떤 형식으로 쓸지**만 정합니다.

---

## 이미 요구사항에서 고정된 것

- 주 사용자: 종합기획부. 신용리스크관리부·영업점은 로그인 후 ‘이후 구현’만
- Journey A Dashboard / B 경영목표 / C 데이터베이스 / D 전파는 저장·스키마
- End-to-End 9단계가 데모의 성공 정의
- 스토리 언어는 사용자에게 보이는 기본이 한국어 (FR-2.6)

---

## 스토리 분해 방식 (참고)

| 방식 | 이 프로젝트에서의 의미 |
|---|---|
| User Journey-Based | Journey A→B→C와 E2E 순서로 스토리를 나열 |
| Feature-Based | Dashboard, 목표, DB, 로그인 등 기능 덩어리 |
| Persona-Based | 종합기획부 vs 다른 Persona 안내 |
| Domain-Based | 여신 / 목표 / 지식 / 전파 |
| Epic-Based | MONITOR / INTERPRET / SET DIRECTION / PROPAGATE 에픽 아래 스토리 |

하이브리드를 고르면, 어떤 축이 1차 목차인지 `[Answer]`에 적어 주세요.

---

## Question S1
스토리를 무엇 기준으로 나눌까요?

A) User Journey-Based — Journey A, B, C, D(구조) 순. 데모 E2E가 읽기 쉽다

B) Epic-Based — MONITOR / INTERPRET / SET DIRECTION / PROPAGATE 에픽 아래 스토리

C) Feature-Based — 로그인, Dashboard, 여신 상세, 경영목표, DB, 시드/관리

D) A를 1차 목차로 하고, 각 Journey 안에서 Feature로 묶는 하이브리드

X) Other (please describe after [Answer]: tag below)

[Answer]: D

---

## Question S2
한 스토리의 크기는 어느 정도가 좋습니까?

A) 화면·주요 행동 단위 (예: “여신 상세에서 기업여신 지표와 Agent 해설을 본다”)

B) FR 번호에 가깝게 잘게 (예: Attention 목록, 카드 클릭, 상세 재표시를 각각 스토리)

C) Journey 한 덩어리당 큰 스토리 소수 (A/B/C 각 1~2개) + 수용 기준만 길게

X) Other (please describe after [Answer]: tag below)

[Answer]:A로 하되, B에 해당하는 FR들의 성공 여부를 체크하면서 진행

---

## Question S3
신용리스크관리부·영업점 Persona는 스토리에 어떻게 넣을까요?

A) 페르소나에는 세 명을 적되, 이번 구현 스토리는 종합기획부만. 다른 둘은 ‘이후 구현’ 로그인 안내 스토리 1개로만 둔다

B) 페르소나 문서에만 세 명을 적고, 다른 Persona 스토리는 만들지 않는다 (로그인 안내는 종합기획부 진입 스토리의 수용 기준으로만)

C) 이후 Journey용 백로그 스토리(확인·보고 요청 생성, 목표 수신)를 ‘구현 안 함’으로 명시해 둔다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question S4
수용 기준 형식은요?

A) Given / When / Then

B) 체크리스트 불릿 (조건이 참이면 완료)

C) 핵심 스토리는 Given/When/Then, 보조는 불릿

X) Other (please describe after [Answer]: tag below)

[Answer]:C

---

## Question S5
스토리 본문 언어는요? (화면 카피는 한국어가 기본)

A) 스토리·수용 기준 전부 한국어. ID만 영어 (예: US-A-01)

B) 역할/행동 템플릿은 영어, 설명은 한국어

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

## Question S6
데모 End-to-End 9단계와 나머지 FR의 관계는요?

A) E2E를 관통하는 스토리를 먼저 두고, 빠진 FR은 같은 Journey에 보충 스토리로 붙인다. 데모에 안 나오는 관리 화면(시드 숫자 변경 등)도 스토리로 남긴다

B) FR을 빠짐없이 스토리로 만들고, E2E는 스토리 ID를 이어 붙인 시나리오 절만 둔다

C) 데모 E2E에 필요한 스토리만 이번 Generation에 넣고, 시드 관리·한영 전환 등 보조는 ‘보조 스토리’로 짧게만 적는다

X) Other (please describe after [Answer]: tag below)

[Answer]:C

---

## Question S7
확인·보고 요청(FR-4.9)처럼 **이번엔 UI가 없고 API·시드만**인 것은 어떻게 쓸까요?

A) 종합기획부 스토리: “시드된 요청을 목록에서 본다”. 별도 기술 스토리: “다른 Journey가 같은 저장소에 생성할 수 있다” (구현 범위: API+스키마, UI 없음)

B) 종합기획부 목록 스토리에 수용 기준으로 API·스키마를 넣고, 생성자 스토리는 만들지 않는다

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

## 답변에서 확정한 생성 규칙

F1 원문: “너가 추천하는 안으로 가자”. S4 C·S2와 맞춰 **F1 C**로 기록한다.

- **목차**: Journey A → B → C → D(구조)가 1차. 각 Journey 안에서 Feature로 묶음 (S1 D)
- **크기**: 화면·주요 행동 단위. FR 번호로 스토리를 쪼개지 않음 (S2 A)
- **FR 추적**: 본편 스토리 제목/본문에 관련 FR ID를 적는다. 수용 기준의 성공 조건은 사용자 행동 Given/When/Then이다. stories.md 끝에 IN FR 대조표를 둔다. 빠진 IN FR이 있으면 보조 스토리로 짧게 올린다 (F1 C, S6 C)
- **본편**: 데모 E2E 9단계에 필요한 스토리. 수용 기준은 Given / When / Then (S4 C, S6 C)
- **보조**: 시드 관리, 한/영 전환, HWP 등 E2E에 필수 아닌 것은 짧게, 수용 기준은 불릿 (S4 C, S6 C)
- **Persona**: personas.md에 세 명. 구현 스토리는 종합기획부. 다른 둘은 ‘이후 구현’ 로그인 안내 스토리 1개 (S3 A)
- **언어**: 스토리·수용 기준 한국어, ID만 영어 (S5 A)
- **확인·보고**: 종합기획부가 시드 목록을 보는 본편 스토리 + 다른 Journey가 같은 저장소에 생성하는 API·스키마 기술 스토리(UI 없음, 보조) (S7 A)

---

## 승인 후 실행할 체크리스트

- [x] 승인된 분해 방식·크기로 스토리 목차를 확정한다
- [x] `aidlc-docs/inception/user-stories/personas.md`를 만든다 (종합기획부 + 로그인만 있는 두 Persona)
- [x] `aidlc-docs/inception/user-stories/stories.md`를 만든다 (INVEST, 수용 기준, 페르소나 매핑, FR 추적)
- [x] End-to-End 9단계를 스토리 ID로 매핑하는 절을 stories.md에 넣는다
- [x] INVEST를 스토리별로 점검한다
- [x] 요구사항 FR 중 스토리에 안 올라간 IN 범위가 없는지 대조한다

---

계획을 채운 뒤에도 바로 생성하지 않습니다. 답을 검증한 다음, 이 계획에 대한 **명시적 승인**을 받습니다.
