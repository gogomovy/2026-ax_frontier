# Unit of Work Story Map

스토리 16개. 주 단위가 Construction 본편이다. 부 단위는 같은 스토리의 다른 화면·API다 (U2 B).

| 스토리 | 주 단위 | 부 단위 | 이유 |
|---|---|---|---|
| US-LOGIN-01 | U-MONITOR | | 로그인→Dashboard |
| US-LOGIN-02 | U-MONITOR | | 이후 구현 안내 |
| US-A-01 | U-MONITOR | U-KNOWLEDGE | Attention이 정책 요약 읽기 |
| US-A-02 | U-MONITOR | U-PROPAGATE | 목록은 MONITOR, 생성 API는 PROPAGATE |
| US-A-03 | U-MONITOR | | 여신 상세 Attention |
| US-A-04 | U-MONITOR | | 여신 지표·해설 |
| US-A-05 | U-MONITOR | U-SET-DIRECTION | 등록은 Dashboard/상세, 목록은 목표 화면 |
| US-B-01 | U-SET-DIRECTION | U-MONITOR | Nav·검토 목록 |
| US-B-02 | U-SET-DIRECTION | U-KNOWLEDGE | 세 근거 |
| US-B-03 | U-SET-DIRECTION | U-PROPAGATE | 확인이 현재 목표를 남김 |
| US-B-04 | U-SET-DIRECTION | U-KNOWLEDGE | 포용금융 근거 |
| US-C-01 | U-KNOWLEDGE | U-SET-DIRECTION | 원문 API·Knowledge UI / 목표 화면에서 열기 |
| US-D-01 | U-PROPAGATE | U-SET-DIRECTION | 읽기 API / 확인 시 저장 |
| US-D-02 | U-PROPAGATE | U-MONITOR | 생성 API / 같은 목록 |
| US-AUX-01 | U-MONITOR | | Shell i18n |
| US-AUX-02 | U-PROPAGATE | U-MONITOR, U-SET-DIRECTION | Admin이 Metrics·목표를 바꿈 |
| US-AUX-03 | U-MONITOR | U-SET-DIRECTION | 화면 맥락별 Agent |
| US-AUX-04 | U-KNOWLEDGE | | 업로드·HWP |
| US-AUX-05 | U-KNOWLEDGE | | 검색·기사 확정 |

---

## 단위별 본편 스토리

### U-KNOWLEDGE
US-C-01, US-AUX-04, US-AUX-05

### U-MONITOR
US-LOGIN-01, US-LOGIN-02, US-A-01, US-A-02, US-A-03, US-A-04, US-A-05, US-AUX-01, US-AUX-03

### U-SET-DIRECTION
US-B-01, US-B-02, US-B-03, US-B-04

### U-PROPAGATE
US-D-01, US-D-02, US-AUX-02

---

## 누락 검사

| ID | 배정 |
|---|---|
| US-LOGIN-01 | 있음 |
| US-LOGIN-02 | 있음 |
| US-A-01 | 있음 |
| US-A-02 | 있음 |
| US-A-03 | 있음 |
| US-A-04 | 있음 |
| US-A-05 | 있음 |
| US-B-01 | 있음 |
| US-B-02 | 있음 |
| US-B-03 | 있음 |
| US-B-04 | 있음 |
| US-C-01 | 있음 |
| US-D-01 | 있음 |
| US-D-02 | 있음 |
| US-AUX-01 | 있음 |
| US-AUX-02 | 있음 |
| US-AUX-03 | 있음 |
| US-AUX-04 | 있음 |
| US-AUX-05 | 있음 |

16개 모두 주 단위가 있다.
