# Component Methods

상세 업무 규칙은 Functional Design에서 정한다. 여기 시그니처는 입력·출력과 목적만 고정한다.

공통 타입:

- `PersonaId`: 종합기획부 | 신용리스크관리부 | 영업점
- `SectorId`: 여신 | 수신 | 퇴직연금 | 자산관리 | 신탁 | 외환 | 카드
- `EvidenceId`: 근거 레코드 ID (Metrics / 목표 / 문서 / 확정 기사 / 공식 검색)
- `AgentResult`: `{ body, evidenceIds: EvidenceId[] }` — `evidenceIds` 빈 목록이면 호출 실패
- `Locale`: ko | en

---

## WebShell
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `showLogin` | 계정 목록 | 없음 | 세 Persona 계정 |
| `login` | Mock 로그인 | 계정 식별자 | PersonaId, 진입 경로 |
| `navigate` | 상위 영역 이동 | Dashboard \| Goals \| Knowledge | 해당 화면 |
| `setLocale` | 한/영 | Locale | 적용된 Locale |

## DashboardUi
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `load` | 메인 구성 | 세션 | 카드, Attention 목록, 보고 목록 |
| `openSector` | 카드 클릭 | SectorId | 여신이면 상세, 아니면 부문 Attention만 |
| `saveForGoalReview` | 검토 대상 등록 | Attention 또는 보고 ID | 저장 확인 |

## LoanDetailUi
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `load` | 상세 | 세션 | Attention+근거, 세 영역 지표, 해설 |
| `askFollowUp` | 추가 질문 | 질문 문자열 | AgentResult |

## GoalsUi
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `load` | 여신 설정 | 세션 | 목표 List, 검토 필요, 제안 |
| `keepGoal` / `applyProposal` / `applyEditedProposal` | 기존 목표 확인 | 목표 ID, 선택 값 | 현재 목표 |
| `addProposed` / `addEdited` / `addManual` | 신규 추가 | 제안 또는 입력 | 현재 목표 |
| `openEvidence` | 원문 | EvidenceId | 문서 메타+텍스트 또는 파일 |

## KnowledgeUi
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `loadHome` | 두 카드 | 없음 | 정책 DB, 의사결정 DB |
| `upload` | 문서 등록 | 파일, 메타 | 문서 ID |
| `confirmArticle` | 기사 확정 | 후보 ID | 확정 여부 |
| `searchOfficial` | 공식 검색 | 질의 | 검색 결과 |

## AdminUi
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `load` / `saveMetrics` / `saveGoals` | 시드 변경 | 숫자·목표 | 갱신된 시드 |

---

## Identity
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `authenticate` | Mock 로그인 | 계정 | PersonaId, 세션 |
| `resolveEntry` | 진입 경로 | PersonaId | Dashboard 또는 이후구현 |

## Metrics
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `listSectorCards` | 세계관 카드 | 없음 | 7 부문 요약 |
| `getLoanOverview` | 여신 종합수익 | 없음 | 단일 값 + 비교 |
| `getCorporateLoan` | 기업여신 지표 | 없음 | FR-5.7 지표 + 현재 목표 |
| `getHouseholdLoan` | 가계여신 지표 | 없음 | FR-5.9 + 포용금융(FR-5.10) |

## Attention
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `listDashboard` | 부문별 1~2개 목록 | 없음 | notification list (여신=Agent, 나머지=Mock) |
| `getBySector` | 부문 Attention | SectorId | 해당 부문 항목+evidenceIds |
| `saveLoanItems` | 여신 Attention 저장 | AgentResult[] | 저장본 |

## ReportRequest
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `create` | 이후 Journey 생성 | Persona, 조직, 부문, 제목, 본문, 상태 | 요청 ID |
| `list` | Dashboard 목록 | 없음 | 요청 목록 |

## ManagementGoal
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `listCurrent` | 현재 여신 목표 | SectorId=여신 | 목표 List+상태 |
| `listReviewNeeds` | 검토 필요사항 | 없음 | US-A-05 목록 |
| `addReviewItem` | 검토 등록 | Attention 또는 보고 ID | 항목 |
| `keep` | 유지 확인 | 목표 ID | 현재 목표 |
| `applyProposal` | 제안 그대로 | 목표 ID, 제안 | 현재 목표, 생성방식 AI |
| `applyEditedProposal` | 일부 수정 후 확인 | 목표 ID, 수정본 | 현재 목표, History |
| `addFromProposal` / `addFromEditedProposal` / `addManual` | 신규 | 제안 또는 입력 | 현재 목표 |
| `listHistory` | History | 목표 ID | 변경 기록 |
| `getCurrentForPropagation` | 전파 읽기 | SectorId | 현재 목표 모델 (화면 없음) |

## Knowledge
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `registerPolicy` / `registerDecision` | 업로드 | 파일, 메타 | 문서 ID (내부에서 Extraction 호출) |
| `getEvidence` | 원문 확인 | EvidenceId | 문서명, 출처, 날짜, 참고 내용/요약, 파일 |
| `listRelated` | 관련 문서만 | 부문, 목표 맥락 | 문서 패킷 |
| `searchOfficial` | 공식 도메인만 | 질의 | 금감원·금융위·기재부 등 결과 |
| `listArticleCandidates` / `confirmArticle` | 기사 | 후보 ID | 확정된 것만 근거 가능 |

## Extraction
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `extract` | 텍스트 추출 | 로컬 경로, 형식(hwp\|pdf\|txt) | 추출 텍스트 |

## AttentionAgent
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `selectLoanAttentions` | 여신 Attention | Metrics, 현재 목표, Knowledge 정책 요약 | AgentResult[] (1~2) |
| `commentLoan` | 영역 해설 | 영역(종합수익\|기업\|가계), Metrics | AgentResult (Metrics evidenceIds만) |
| `answerFollowUp` | Dashboard/여신 추가 질문 | 질문, 화면 맥락 | AgentResult |

## GoalAgent
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `selectRelatedDocuments` | 관련 문서만 | 부문, 목표 | Knowledge 패킷 (전 문서 투입 금지) |
| `reviewGoals` | 기존 목표 검토 | 목표 List, 세 근거 패킷 | AgentResult (방향+범위, 왜 수정/왜 숫자 분리) |
| `proposeNew` | 신규 (포용금융) | 가계 포용금융 지표, 확정 기사, 내부 논의, 공식 정책 | AgentResult + 제안 필드 |
| `answerFollowUp` | 목표 화면 추가 질문 | 질문, 화면 맥락 | AgentResult |

## AdminSeed
| 메서드 | 목적 | 입력 | 출력 |
|---|---|---|---|
| `updateMetrics` | 실적 시드 | 지표 값 | 갱신 |
| `updateGoals` | 목표 시드 | 목표 값 | 갱신 |
