# Story Generation Plan — 추가 질문

S1–S7을 모두 읽었습니다. S1, S3–S7은 그대로 받습니다. S2만 A와 B를 합친 답이라, FR 체크를 **어디에 남길지**가 스토리 품질에 영향을 줍니다.

`[Answer]:` 뒤에 선택 글자를 적어 주세요. 채운 뒤 채팅에서 다시 읽어 달라고 해 주세요.

---

## 이미 확정으로 받아들인 답

- S1 D: Journey A→B→C→D가 1차 목차, 각 Journey 안에서 Feature로 묶음
- S3 A: personas.md에 세 명. 구현 스토리는 종합기획부. 다른 둘은 ‘이후 구현’ 로그인 안내 스토리 1개
- S4 C: 본편은 Given/When/Then, 보조는 불릿
- S5 A: 스토리·수용 기준 한국어, ID만 영어
- S6 C: 데모 E2E에 필요한 스토리가 본편. 시드 관리·한/영 전환 등 보조는 짧게 적음. IN 범위 FR은 생략하지 않음
- S7 A: 시드된 확인·보고 목록을 보는 본편 스토리 + 같은 저장소에 생성하는 API·스키마 기술 스토리(UI 없음)

---

## Question F1

S2는 스토리 크기는 A(화면·주요 행동)이고, B처럼 FR 성공 여부를 체크한다고 하셨습니다. FR 체크는 어디에 남길까요?

A) 화면 단위 스토리의 수용 기준에, 그 화면이 담당하는 FR마다 성공 조건을 넣는다. stories.md 끝에도 IN FR 대조표를 둔다

B) 수용 기준은 사용자 행동만 쓰고, FR 커버리지는 stories.md 끝 대조표로만 본다

C) 본편 스토리 제목/본문에 관련 FR ID만 적고, 성공 조건은 사용자 행동 Given/When/Then에만 둔다. 대조표는 문서 끝에 둔다

X) Other (please describe after [Answer]: tag below)

[Answer]: 너가 추천하는 안으로 가자

기록된 선택: **C**. S4 C(본편 수용 기준은 사용자 행동 Given/When/Then)와 S2(스토리는 화면 단위, FR로 쪼개지 않음)에 맞춘다. FR 성공 여부는 스토리의 FR ID 매핑과 stories.md 끝 대조표로 검사한다.
