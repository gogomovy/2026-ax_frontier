# Unit of Work Plan — 추가 질문

U1–U6을 읽었습니다. U2 B, U3 A는 그대로 받습니다. U6는 요구사항 FR-10(`apps/web`, `apps/api`)과 맞춰 **B**로 기록합니다. 루트 `src/`나 `src/web`으로 FR-10을 바꾸지 않습니다.

남은 충돌은 단위를 **몇 개로 자를지**입니다.

- U1 B: Journey 5개 (진입+Dashboard, 여신 상세, 경영목표, Knowledge, 전파·시드)
- U4 C: 모노레포 **한 단위**
- U5 B: MONITOR / SET DIRECTION / Knowledge / PROPAGATE **4개**

`[Answer]:` 뒤에 선택 글자를 적어 주세요. 채운 뒤 채팅에서 다시 읽어 달라고 해 주세요.

---

## 이미 확정으로 받아들인 답

- U2 B: 스토리마다 Web·API를 같이 연다. 계약은 스토리마다 확장
- U3 A: 한 작업 흐름. 소유 구분은 문서상 단위
- U6 B: 물리 경로는 `apps/web`, `apps/api`만. 단위 이름 폴더를 워크스페이스 루트에 두지 않음

---

## Question F1

Units Generation에서 Construction이 반복할 **단위 개수**는 어느 쪽인가요?

A) U1 B — 5단위. 진입+Dashboard, 여신 상세, 경영목표, Knowledge, 전파·시드. 각 단위에 해당 화면과 필요한 API를 같이 넣는다. U4 C는 쓰지 않는다. U5의 MONITOR는 이 중 앞의 둘을 가리키는 이름일 뿐

B) U5 B — 4단위. MONITOR(진입+Dashboard+여신 상세), SET DIRECTION(경영목표), Knowledge, PROPAGATE(전파 API·시드·확인보고 생성). U1의 여신 상세는 MONITOR에 포함한다. U4 C는 쓰지 않는다

C) U4 C — 단위 1개(모노레포 전체). U1 B·U5 B는 그 안의 작업 순서(에픽)로만 적고, Functional Design은 한 번만 한다

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **B**. Construction 단위는 4개다. MONITOR에 진입·Dashboard·여신 상세를 넣는다. 코드는 계속 `apps/web`·`apps/api`에만 둔다 (U4의 별도 스케일 단위는 아님).
