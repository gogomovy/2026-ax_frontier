# Frontend Components — U-KNOWLEDGE

레이아웃 픽셀은 정하지 않는다. 구조·상태·호출만 둔다.

홈은 카드 두 개다. 기사 후보·확정·공식 검색·도메인 목록은 **정부정책 DB** 안에 둔다 (K8 A).

---

## 계층

```
KnowledgeHome
  PolicyDbCard → PolicyDbPage
  DecisionDbCard → DecisionDbPage

PolicyDbPage
  PolicyDocumentList
  PolicyUploadForm
  PolicyDocumentDetail
  OfficialSearchPanel
    OfficialDomainList
    SearchBox
    SearchHitList
  ArticleCandidateList
  ArticleDetail (확정/해제)

DecisionDbPage
  DecisionDocumentList
  DecisionUploadForm
  DecisionDocumentDetail
```

원문 확인(US-C-01)은 이 단위의 EvidencePanel을 쓴다. 목표 화면에서 여는 것은 U-SET-DIRECTION이 같은 getEvidence를 호출한다.

---

## 상태

| 화면 | 상태 |
|---|---|
| KnowledgeHome | 없음(카드 두 개) |
| PolicyDbPage | 목록, 선택 문서, 업로드 중, 검색어, 검색 결과, 검색 오류, 기사 후보 |
| DecisionDbPage | 목록, 선택 문서, 업로드 중 |
| PolicyUploadForm / DecisionUploadForm | 파일, 메타 필드, 검증 오류 |
| PolicyDocumentDetail | 현재 버전, extractedText, summary(편집), 다운로드 |
| OfficialSearchPanel | 질의, hits[], error |
| ArticleCandidateList | 미확정 목록 |

---

## 상호작용

- 카드 클릭 → 해당 DB 페이지
- 업로드 제출 → registerPolicy / registerDecision. 추출 실패면 폼 오류, 목록에 안 올라감
- 상세에서 summary 수정 저장
- 원본 다운로드
- 검색 실행 → searchOfficial. 실패면 오류 표시, hits 비움
- 히트에서 후보로 넣기 → 미확정 Article
- 기사 확정 / 확정 해제
- 직접 기사 등록(제목·URL 또는 파일) → 미확정 Article
- 도메인 추가·삭제

---

## 폼 검증

- 정책·의사결정: 파일 필수, 문서명 필수, 사업부문 1개 이상, 허용 확장자
- 기사 직접 등록: 제목 필수, URL 또는 파일 중 하나
- 도메인 추가: 호스트 문자열, 목록 중복 금지

---

## API (이 화면이 쓰는 것)

| UI | 호출 |
|---|---|
| KnowledgeHome | 없음(정적 카드) |
| 목록·상세 | Knowledge 조회, getEvidence |
| 업로드 | registerPolicy / registerDecision |
| 검색 | searchOfficial |
| 기사 | listArticleCandidates, confirmArticle, 확정 해제, 직접 등록 |
| 도메인 | 목록 조회·추가·삭제 |

Extraction은 UI가 직접 호출하지 않는다. 업로드 API가 호출한다.
