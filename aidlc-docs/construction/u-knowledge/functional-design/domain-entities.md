# Domain Entities — U-KNOWLEDGE

K1 B: 정책·의사결정·기사는 별도 엔티티. 원문 열기는 EvidenceRef.

기술 타입 이름은 구현이 정한다. 아래는 개념이다.

---

## EvidenceRef

원문 확인의 공통 손잡이.

- evidenceId
- kind: policy | decision | article
- targetId

확정되지 않은 Article을 가리키는 EvidenceRef는 getEvidence에서 거절한다.

---

## PolicyDocument

- id
- title (문서명)
- agency (기관)
- policyOrAsOfDate
- registeredAt
- sectors[]
- tags[]
- versions[] (최신이 현재)
- 각 버전: versionNo, file, extractedText, summary, createdAt

---

## DecisionDocument

- id
- title
- meetingOrSource
- decisionDate
- registeredAt
- sectors[]
- tags[]
- versions[] (PolicyDocument와 동일 구조)

---

## Article

- id
- title
- url (직접 등록·검색 후보일 때)
- file (업로드한 기사일 때, 없으면 없음)
- source (시드 | 직접 | 공식검색)
- confirmed: boolean
- confirmedAt (확정 시각, 미확정이면 없음)
- sectors[]
- tags[]
- summary (선택)

파일과 URL이 둘 다 없을 수 없다. 직접 등록은 제목+URL 또는 파일.

---

## OfficialDomain

- host
- enabled
- 기본 시드: fsc.go.kr, fss.or.kr, moef.go.kr에 해당하는 공식 호스트. 정확한 호스트 문자열은 구현 시 공개 도메인으로 고정한다

---

## SearchHit (저장 엔티티 아님)

검색 응답의 화면용 값: title, url, excerpt, sourceHost.  
후보로 넣기 전까지 도메인에 남기지 않는다.

---

## 관계

```
EvidenceRef --kind+targetId--> PolicyDocument | DecisionDocument | Article
PolicyDocument 1--* DocumentVersion
DecisionDocument 1--* DocumentVersion
OfficialDomain (검색 허용)
Article.confirmed가 true일 때만 EvidenceRef.kind=article 허용
```
