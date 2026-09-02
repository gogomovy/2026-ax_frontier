# Functional Design Plan — U-KNOWLEDGE

Construction 첫 단위. 스토리: US-C-01, US-AUX-04, US-AUX-05.  
선행 단위 없음. 기술 스택·인프라는 이 단계에서 정하지 않는다.

이 파일의 `[Answer]:`를 모두 채운 뒤 채팅에서 **답을 채웠으니 다시 읽고 진행해 달라**고 해 주세요.

---

## 이미 고정된 것

- 두 카드: 정부정책 DB, 경영 의사결정사항 DB
- 정책 업로드: PDF, 텍스트, HWP. 브라우저 HWP 뷰어 없음
- 추출은 Extraction 컴포넌트. Knowledge는 경로·메타를 들고 추출을 호출 (D9 B)
- 공식 도메인만 검색. 기본: 금융위, 금감원, 기재부
- 기사는 확정 후에만 근거. 데모 포용금융 기사는 확정 시드
- Agent는 관련 문서만 (선정 로직의 본편은 GoalAgent, 이 단위는 조회 API)

---

## 답변에서 확정한 생성 규칙

- K1 B: PolicyDocument, DecisionDocument, Article. 원문은 EvidenceRef
- K2 A: listRelated는 부문 + Tag 교집합. 랭킹 없음
- K3 C: 공식 검색도 후보→확정 후에만 근거 (Article)
- K4 B: 추출 전체 + 수정 가능한 summary. LLM 요약 없음
- K5 C: 도메인 목록 화면 관리. 기사 = 시드 + 직접 등록 + 검색에서 후보
- K6 A: 추출 실패는 업로드 실패. 검색 실패는 숨기지 않음. 허용 밖은 거부
- K7 A: 재업로드는 새 버전. 기사 확정 해제 가능
- K8 A: 홈 카드 2개. 검색·기사는 정부정책 DB 안

## 승인 후 실행할 체크리스트

- [x] `aidlc-docs/construction/u-knowledge/functional-design/business-logic-model.md`
- [x] `aidlc-docs/construction/u-knowledge/functional-design/business-rules.md`
- [x] `aidlc-docs/construction/u-knowledge/functional-design/domain-entities.md`
- [x] `aidlc-docs/construction/u-knowledge/functional-design/frontend-components.md`

---

## Question K1

정책 문서, 경영 의사결정, 기사 후보는 도메인에서 어떻게 구분할까요? (Domain Model)

A) 한 KnowledgeItem. kind = policy | decision | article. 메타 필드 중 해당 kind만 필수

B) PolicyDocument, DecisionDocument, Article는 별도 엔티티. 공통은 EvidenceRef(원문 열기용)만

C) 정책·의사결정은 문서(파일 있음). 기사는 파일 없는 레코드(URL·제목·확정 여부). 업로드한 기사 파일은 policy와 같은 문서이나 kind=article

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question K2

“관련 문서만” 조회는 이 단위에서 어떤 필드로 걸러 줄까요? (Business Logic / FR-7.6)

A) 적용 사업부문 + Tag 교집합. Agent(나중 단위)가 부문·태그를 넘기면 목록을 돌려준다. 점수·랭킹은 이 단위에 두지 않는다

B) 부문만. Tag는 표시용이고 필터에 쓰지 않는다

C) 사용자가 문서에 ‘목표 검토에 사용’ 플래그를 켠 것만 Agent에 준다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question K3

공식 검색 결과와 기사 후보의 저장 규칙은요? (Business Rules / Data Flow)

A) 공식 검색: 호출 시점의 제목·URL·발췌를 스냅샷으로 저장하면 근거 ID를 붙일 수 있다. 기사는 후보(미확정)로 모이고, 확정 후에만 listRelated·원문에 나온다

B) 공식 검색은 URL만 두고 원문은 매번 다시 가져온다. 기사는 A와 같다 (확정 전 근거 금지)

C) 공식 검색도 기사와 같이 ‘확정’이 있어야 근거가 된다

X) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Question K4

업로드 후 추출과 화면의 ‘요약’은요? (Data Flow)

A) 업로드 성공 = 파일 저장 + 추출 텍스트. 요약은 추출 텍스트 앞부분(길이 상한). LLM 요약은 이 단위에 없다

B) 추출 텍스트 전체 + 별도 summary 필드. summary는 사용자가 수정할 수 있다. 초기값은 앞부분

C) 추출 실패해도 파일과 메타는 남기고, 텍스트 없음으로 표시. 재추출을 누를 수 있다

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question K5

공식 도메인 목록과 기사 후보는 누가 채울까요? (Integration)

A) 도메인 목록은 설정(기본 3곳) + 이 단위 화면에서 추가·삭제. 기사 후보는 ‘검색 실행’으로 공식 도메인 결과를 모은 뒤, 사용자가 기사로 분류해 후보에 넣는 것

B) 도메인 목록은 설정만 (이번 단위에 관리 UI 없음). 기사 후보는 시드 + 사용자가 URL·제목을 직접 등록

C) 도메인 목록은 설정 + 화면 관리. 기사 후보는 시드 + 직접 등록 + 검색 결과에서 ‘후보로 넣기’

X) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Question K6

실패 시 사용자에게 보이는 동작은요? (Error Handling)

A) 추출 실패: 업로드 전체 실패(파일 안 남김). 공식 검색 실패: 목록 비움 + 실패를 숨기지 않음. 허용 도메인 밖 URL은 검색·근거 모두 거부

B) 추출 실패: 파일은 남기고 텍스트 없음 + 오류 표시. 검색 실패: A와 같음

C) 허용 도메인 밖이어도 저장은 하고, 근거로만 쓰지 않는다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question K7

같은 파일 재업로드, 기사 확정 취소는요? (Business Scenarios)

A) 같은 파일명·내용은 새 버전으로 추가(이력). 기사 확정은 해제할 수 있고, 해제 후 Agent 근거에서 빠진다

B) 같은 문서는 덮어쓰기(메타·텍스트 교체). 확정 해제는 없음. 잘못된 기사는 삭제만

C) 재업로드는 거부(이미 있으면 오류). 확정 해제는 A와 같음

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question K8

Knowledge 화면 구조는요? (Frontend)

A) 홈: 카드 2개. 각 DB는 목록+업로드+상세(메타, 추출 텍스트, 다운로드). 기사 후보·확정은 정부정책 DB 안의 구역

B) 홈: 카드 2개 + 세 번째 ‘기사 확정’ 카드. 검색·후보는 그 카드

C) 홈: 카드 2개. 검색·기사 확정은 상단 공통 영역(어느 카드를 열든 보임)

X) Other (please describe after [Answer]: tag below)

[Answer]: A
