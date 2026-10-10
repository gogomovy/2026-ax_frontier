import type {
  AnalysisTab,
  BranchDashboard,
  BranchKpiAlert,
  BranchOffice,
  BranchTabs,
  DomainCardInfo,
  Evidence,
  Figure,
  Insight,
  KpiGroup,
  ReportDoc,
  ReportTableBlock,
} from "@/lib/types";
import { AS_OF, GENERATED_AT, PASSED_VERIFICATIONS, evidence, fig } from "./helpers";
import { DOC } from "./knowledge";

/**
 * 영업점 시나리오 (B.29) — 수원영통지점(사무소 001068) · 2026년 하반기 업적평가
 *
 * 시나리오 정의: data/사나리오 정의/TalkFile_(영업점)데이터활용계획 및 Agent시나리오_.txt
 * 수치(V) · 표(T)는 시드 데이터(apps/api/src/nhdip/seed/defs_branch.py)를 커널로 계산한 결과의 스냅샷이다.
 * API 모드에서는 워크플로우 wf_branch_kpi 가 같은 id 의 수치 · 표를 다시 계산해 채운다.
 */

/* ── 계산 스냅샷 (커널 결과) ────────────────────────────────── */
const V: Record<string, number> = {
  br_corp_cnt: 180, br_corp_amt: 1331.9, bank_corp_cnt: 3894, bank_corp_amt: 59942.1, br_micro_amt_share: 12.7, bank_micro_amt_share: 4.4,
  br_micro_cnt_share: 62.2, bank_micro_cnt_share: 43.5, br_upper_amt_share: 43.6, bank_upper_amt_share: 79.4, br_upper_cnt_share: 17.2,
  bank_upper_cnt_share: 40.1, bank_micro_avg_grade: 9.79, bank_upper_avg_grade: 6.78, br_avg_grade: 8.39, bank_avg_grade: 6.16,
  br_avg_grade_gap: 2.22, br_prospect_cnt: 5, br_prospect_amt: 140, br_prospect_avg_grade: 2.96, br_prospect_weighted: 210, br_avg_grade_after: 7.87,
  br_avg_grade_improve: 0.52, br_prime_actual: 60, br_prime_target: 600, br_prime_points: 40, br_prime_score_now: 4.0, br_prime_score_after: 18.0,
  br_prime_uplift: 14.0, br_retail_amt: 283.9, br_retail_cnt: 260, bank_retail_amt: 5181.7, bank_retail_cnt: 6020, br_seomin_amt: 129,
  br_seomin_cnt: 6, bank_seomin_amt: 111.0, bank_seomin_cnt: 485, br_seomin_share: 0.45, bank_seomin_share: 2.14, br_seomin_cnt_share: 2.3,
  bank_seomin_cnt_share: 8.1, br_seomin_share_gap: 1.69, br_lowcredit_share: 2.2, bank_lowcredit_share: 5.3, br_retail_dlq_rate: 0.3,
  bank_retail_dlq_rate: 0.54, bank_seomin_dlq_rate: 5.34, br_seomin_prov_rate: 4.68, br_seomin_ticket_avg: 22.9, br_seomin_limit: 35,
  br_seomin_ticket: 22.9, br_seomin_gap_amt: 490, br_seomin_prov_limit: 20, br_seomin_prov_cap: 427, br_seomin_max_cnt: 30, br_seomin_cnt_cap: 687,
  br_seomin_rec_amt: 427, br_seomin_rec_cnt: 19, br_seomin_add_prov: 20.0, br_seomin_share_after: 1.93, br_seomin_actual: 4, br_seomin_target: 30,
  br_seomin_points: 20, br_seomin_score_now: 2.7, br_seomin_score_after: 15.3, br_seomin_uplift: 12.7, br_kpi_total: 593.7, br_kpi_max: 1000,
  br_kpi_cust: 137.0, br_kpi_biz: 254.7, br_kpi_fin: 200.0, br_kpi_adj: 2.0, br_kpi_uplift: 26.7, br_kpi_total_after: 620.3, br_loan_total: 1615.8,
  br_seg_deposit: 1420.6, br_seg_fx: 38.4, br_seg_pension: 210.3, br_seg_card: 52.1,
};

type Spec = [label: string, unit: Figure["unit"], decimals: number];
const SPEC: Record<string, Spec> = {
  br_corp_cnt: ["지점 기업여신 차주 수", "CNT", 0],
  br_corp_amt: ["지점 기업여신 대출잔액", "KRW_BN", 1],
  bank_corp_cnt: ["전행 기업여신 차주 수", "CNT", 0],
  bank_corp_amt: ["전행 기업여신 대출잔액", "KRW_BN", 1],
  br_micro_amt_share: ["지점 소기업 비중(금액)", "PCT", 1],
  bank_micro_amt_share: ["전행 소기업 비중(금액)", "PCT", 1],
  br_micro_cnt_share: ["지점 소기업 비중(건수)", "PCT", 1],
  bank_micro_cnt_share: ["전행 소기업 비중(건수)", "PCT", 1],
  br_upper_amt_share: ["지점 대기업 · 외감 · 비외감 비중(금액)", "PCT", 1],
  bank_upper_amt_share: ["전행 대기업 · 외감 · 비외감 비중(금액)", "PCT", 1],
  br_upper_cnt_share: ["지점 대기업 · 외감 · 비외감 비중(건수)", "PCT", 1],
  bank_upper_cnt_share: ["전행 대기업 · 외감 · 비외감 비중(건수)", "PCT", 1],
  bank_micro_avg_grade: ["전행 소기업 평균 신용등급(차주 수 기준)", "NONE", 2],
  bank_upper_avg_grade: ["전행 대기업 · 외감 · 비외감 평균 신용등급(차주 수 기준)", "NONE", 2],
  br_avg_grade: ["지점 평균 신용등급(대출잔액 가중, 1~16)", "NONE", 2],
  bank_avg_grade: ["전행 평균 신용등급(대출잔액 가중, 1~16)", "NONE", 2],
  br_avg_grade_gap: ["평균 신용등급 차이(지점 − 전행)", "NONE", 2],
  br_prospect_cnt: ["우량기업 마케팅 후보 수", "NONE", 0],
  br_prospect_amt: ["후보 신규 여신 가정액", "KRW_BN", 0],
  br_prospect_avg_grade: ["후보 평균 예상재무등급(금액 가중, 1~16)", "NONE", 2],
  br_prospect_weighted: ["후보 유치 시 등급 가중 실적", "KRW_BN", 0],
  br_avg_grade_after: ["후보 유치 후 지점 평균 신용등급", "NONE", 2],
  br_avg_grade_improve: ["평균 신용등급 개선 폭(단계)", "NONE", 2],
  br_prime_actual: ["우량기업여신 현재 실적(등급 가중)", "KRW_BN", 0],
  br_prime_target: ["우량기업여신 만점 목표(등급 가중)", "KRW_BN", 0],
  br_prime_points: ["우량기업여신 배점", "NONE", 0],
  br_prime_score_now: ["우량기업여신 현재 득점", "NONE", 1],
  br_prime_score_after: ["후보 유치 시 우량기업여신 득점", "NONE", 1],
  br_prime_uplift: ["예상 업적 점수 상향(우량기업여신)", "NONE", 1],
  br_retail_amt: ["지점 소매여신 익스포저", "KRW_BN", 1],
  br_retail_cnt: ["지점 소매여신 차주 수", "CNT", 0],
  bank_retail_amt: ["전행 소매여신 익스포저", "KRW_BN", 1],
  bank_retail_cnt: ["전행 소매여신 차주 수", "CNT", 0],
  br_seomin_amt: ["지점 서민금융(업적평가 인정 Pool) 익스포저", "KRW_MN", 0],
  br_seomin_cnt: ["지점 서민금융 차주 수", "CNT", 0],
  bank_seomin_amt: ["전행 서민금융(업적평가 인정 Pool) 익스포저", "KRW_BN", 1],
  bank_seomin_cnt: ["전행 서민금융 차주 수", "CNT", 0],
  br_seomin_share: ["지점 서민금융 비중(금액)", "PCT", 2],
  bank_seomin_share: ["전행 서민금융 비중(금액)", "PCT", 2],
  br_seomin_cnt_share: ["지점 서민금융 비중(건수)", "PCT", 1],
  bank_seomin_cnt_share: ["전행 서민금융 비중(건수)", "PCT", 1],
  br_seomin_share_gap: ["서민금융 비중 차이(전행 − 지점)", "PP", 2],
  br_lowcredit_share: ["지점 저신용자 Pool 비중(금액)", "PCT", 1],
  bank_lowcredit_share: ["전행 저신용자 Pool 비중(금액)", "PCT", 1],
  br_retail_dlq_rate: ["지점 소매여신 연체율(금액)", "PCT", 2],
  bank_retail_dlq_rate: ["전행 소매여신 연체율(금액)", "PCT", 2],
  bank_seomin_dlq_rate: ["전행 서민금융 연체율(금액)", "PCT", 2],
  br_seomin_prov_rate: ["서민금융 충당금률(가정)", "PCT", 2],
  br_seomin_ticket_avg: ["전행 서민금융 차주당 평균 익스포저", "KRW_MN", 1],
  br_seomin_limit: ["동일차주 연간 최고 대출한도", "KRW_MN", 0],
  br_seomin_ticket: ["권고 산정 평균 취급액(한도 이내)", "KRW_MN", 1],
  br_seomin_gap_amt: ["전행 평균 비중 도달 필요액", "KRW_MN", 0],
  br_seomin_prov_limit: ["충당금 증가 허용액", "KRW_MN", 0],
  br_seomin_prov_cap: ["충당금 허용 범위 내 최대 유치액", "KRW_MN", 0],
  br_seomin_max_cnt: ["반기 신규 가능 건수", "CNT", 0],
  br_seomin_cnt_cap: ["신규 가능 건수 기준 최대 유치액", "KRW_MN", 0],
  br_seomin_rec_amt: ["권고 신규 유치 규모", "KRW_MN", 0],
  br_seomin_rec_cnt: ["권고 신규 유치 건수", "CNT", 0],
  br_seomin_add_prov: ["권고 규모 유치 시 예상 추가 충당금", "KRW_MN", 1],
  br_seomin_share_after: ["유치 후 지점 서민금융 비중", "PCT", 2],
  br_seomin_actual: ["서민금융 하반기 신규 실적", "CNT", 0],
  br_seomin_target: ["서민금융 만점 목표 건수", "CNT", 0],
  br_seomin_points: ["서민금융 배점", "NONE", 0],
  br_seomin_score_now: ["서민금융 현재 득점", "NONE", 1],
  br_seomin_score_after: ["권고 규모 유치 시 서민금융 득점", "NONE", 1],
  br_seomin_uplift: ["예상 업적 점수 상향(서민금융)", "NONE", 1],
  br_kpi_total: ["업적평가 총득점(가 · 감점 포함)", "NONE", 1],
  br_kpi_max: ["업적평가 총배점", "NONE", 0],
  br_kpi_cust: ["고객KPI 득점", "NONE", 1],
  br_kpi_biz: ["사업KPI 득점", "NONE", 1],
  br_kpi_fin: ["재무KPI 득점", "NONE", 1],
  br_kpi_adj: ["가 · 감점 합계", "NONE", 1],
  br_kpi_uplift: ["예상 업적 점수 상향 합계", "NONE", 1],
  br_kpi_total_after: ["의견 반영 시 예상 총득점", "NONE", 1],
  br_loan_total: ["여신 잔액(기업 + 소매)", "KRW_BN", 1],
  br_seg_deposit: ["수신 평잔", "KRW_BN", 1],
  br_seg_fx: ["외환 누적 실적", "KRW_BN", 1],
  br_seg_pension: ["퇴직연금 적립금", "KRW_BN", 1],
  br_seg_card: ["카드 누적 이용실적", "KRW_BN", 1],
};

const F = (id: string): Figure => {
  const [label, unit, decimals] = SPEC[id];
  return fig(id, label, V[id] ?? null, unit, { decimals });
};
const figs = (...ids: string[]): Record<string, Figure> => Object.fromEntries(ids.map((id) => [id, F(id)]));

/* ── 표 스냅샷 (빌더 결과) ──────────────────────────────────── */
type Rows = ReportTableBlock["rows"];
const T: Record<string, Rows> = {
  size: [
    {"size": "대기업", "brCnt": "1", "brCntShare": "0.6", "brAmt": "252.0", "brAmtShare": "18.9", "bankCntShare": "5.0", "bankAmtShare": "42.9", "diffPp": "-24.0"},
    {"size": "외감", "brCnt": "8", "brCntShare": "4.4", "brAmt": "180.3", "brAmtShare": "13.5", "bankCntShare": "13.8", "bankAmtShare": "26.6", "diffPp": "-13.1"},
    {"size": "비외감", "brCnt": "22", "brCntShare": "12.2", "brAmt": "148.3", "brAmtShare": "11.1", "bankCntShare": "21.4", "bankAmtShare": "9.9", "diffPp": "+1.2"},
    {"size": "소기업", "brCnt": "112", "brCntShare": "62.2", "brAmt": "168.6", "brAmtShare": "12.7", "bankCntShare": "43.5", "bankAmtShare": "4.4", "diffPp": "+8.3"},
    {"size": "기업형소호", "brCnt": "37", "brCntShare": "20.6", "brAmt": "582.7", "brAmtShare": "43.8", "bankCntShare": "16.4", "bankAmtShare": "16.2", "diffPp": "+27.6"},
    {"size": "합계", "brCnt": "180", "brCntShare": "100.0", "brAmt": "1,331.9", "brAmtShare": "100.0", "bankCntShare": "100.0", "bankAmtShare": "100.0", "diffPp": "-"},
  ],
  grade: [
    {"grade": "1", "brCnt": "0", "brCntShare": "0.0", "brAmt": "0.0", "brAmtShare": "0.0", "bankCntShare": "0.2", "bankAmtShare": "1.6"},
    {"grade": "2A", "brCnt": "1", "brCntShare": "0.6", "brAmt": "11.5", "brAmtShare": "0.9", "bankCntShare": "0.8", "bankAmtShare": "4.5"},
    {"grade": "2B", "brCnt": "0", "brCntShare": "0.0", "brAmt": "0.0", "brAmtShare": "0.0", "bankCntShare": "2.4", "bankAmtShare": "12.4"},
    {"grade": "3A", "brCnt": "4", "brCntShare": "2.2", "brAmt": "35.7", "brAmtShare": "2.7", "bankCntShare": "3.6", "bankAmtShare": "13.6"},
    {"grade": "3B", "brCnt": "5", "brCntShare": "2.8", "brAmt": "312.4", "brAmtShare": "23.5", "bankCntShare": "6.1", "bankAmtShare": "15.8"},
    {"grade": "4A", "brCnt": "8", "brCntShare": "4.4", "brAmt": "50.0", "brAmtShare": "3.8", "bankCntShare": "8.3", "bankAmtShare": "12.7"},
    {"grade": "4B", "brCnt": "14", "brCntShare": "7.8", "brAmt": "71.4", "brAmtShare": "5.4", "bankCntShare": "11.4", "bankAmtShare": "10.4"},
    {"grade": "5A", "brCnt": "22", "brCntShare": "12.2", "brAmt": "102.6", "brAmtShare": "7.7", "bankCntShare": "13.3", "bankAmtShare": "7.7"},
    {"grade": "5B", "brCnt": "34", "brCntShare": "18.9", "brAmt": "228.6", "brAmtShare": "17.2", "bankCntShare": "14.7", "bankAmtShare": "6.4"},
    {"grade": "5C", "brCnt": "36", "brCntShare": "20.0", "brAmt": "179.3", "brAmtShare": "13.5", "bankCntShare": "14.0", "bankAmtShare": "5.2"},
    {"grade": "6A", "brCnt": "26", "brCntShare": "14.4", "brAmt": "171.0", "brAmtShare": "12.8", "bankCntShare": "10.8", "bankAmtShare": "4.0"},
    {"grade": "6B", "brCnt": "16", "brCntShare": "8.9", "brAmt": "107.8", "brAmtShare": "8.1", "bankCntShare": "7.9", "bankAmtShare": "3.1"},
    {"grade": "6C", "brCnt": "12", "brCntShare": "6.7", "brAmt": "60.6", "brAmtShare": "4.5", "bankCntShare": "4.2", "bankAmtShare": "1.6"},
    {"grade": "7A", "brCnt": "2", "brCntShare": "1.1", "brAmt": "0.9", "brAmtShare": "0.1", "bankCntShare": "1.5", "bankAmtShare": "0.5"},
    {"grade": "7B", "brCnt": "0", "brCntShare": "0.0", "brAmt": "0.0", "brAmtShare": "0.0", "bankCntShare": "0.6", "bankAmtShare": "0.2"},
    {"grade": "8", "brCnt": "0", "brCntShare": "0.0", "brAmt": "0.0", "brAmtShare": "0.0", "bankCntShare": "0.2", "bankAmtShare": "0.1"},
  ],
  sizeGradeCount: [
    {"size": "대기업", "b1": "0.6", "b2": "0.0", "b3": "0.0", "b4": "0.0", "b5": "0.0", "total": "0.6"},
    {"size": "외감", "b1": "1.7", "b2": "1.1", "b3": "1.1", "b4": "0.6", "b5": "0.0", "total": "4.4"},
    {"size": "비외감", "b1": "1.7", "b2": "6.1", "b3": "3.3", "b4": "1.1", "b5": "0.0", "total": "12.2"},
    {"size": "소기업", "b1": "1.7", "b2": "4.4", "b3": "33.3", "b4": "21.7", "b5": "1.1", "total": "62.2"},
    {"size": "기업형소호", "b1": "0.0", "b2": "0.6", "b3": "13.3", "b4": "6.7", "b5": "0.0", "total": "20.6"},
    {"size": "합계", "b1": "5.6", "b2": "12.2", "b3": "51.1", "b4": "30.0", "b5": "1.1", "total": "100.0"},
  ],
  sizeGradeAmount: [
    {"size": "대기업", "b1": "18.9", "b2": "0.0", "b3": "0.0", "b4": "0.0", "b5": "0.0", "total": "18.9"},
    {"size": "외감", "b1": "6.1", "b2": "2.3", "b3": "2.0", "b4": "3.2", "b5": "0.0", "total": "13.5"},
    {"size": "비외감", "b1": "1.8", "b2": "4.7", "b3": "2.9", "b4": "1.8", "b5": "0.0", "total": "11.1"},
    {"size": "소기업", "b1": "0.2", "b2": "0.9", "b3": "6.8", "b4": "4.7", "b5": "0.1", "total": "12.7"},
    {"size": "기업형소호", "b1": "0.0", "b2": "1.3", "b3": "26.7", "b4": "15.8", "b5": "0.0", "total": "43.8"},
    {"size": "합계", "b1": "27.0", "b2": "9.1", "b3": "38.3", "b4": "25.5", "b5": "0.1", "total": "100.0"},
  ],
  weights: [
    {"band": "1~3B", "grades": "1 ~ 3B", "h1": "100%", "h2": "150%"},
    {"band": "4A~4B", "grades": "4A ~ 4B", "h1": "100%", "h2": "120%"},
    {"band": "5A~5C", "grades": "5A ~ 5C", "h1": "100%", "h2": "100%"},
    {"band": "6A~6C", "grades": "6A ~ 6C", "h1": "100%", "h2": "70%"},
    {"band": "7A~8", "grades": "7A ~ 8", "h1": "100%", "h2": "50%"},
  ],
  prospects: [
    {"rank": 1, "corp": "신동에너지(주)", "industry": "태양력 발전업 (D35)", "model": "대기업", "grade": "2A", "asset": "8,204", "debt": "72", "sales": "4,128", "loan": "50", "weight": "150%", "weighted": "75"},
    {"rank": 2, "corp": "광교바이오팜(주)", "industry": "완제 의약품 제조업 (C21)", "model": "외감", "grade": "2B", "asset": "1,824", "debt": "87", "sales": "1,413", "loan": "30", "weight": "150%", "weighted": "45"},
    {"rank": 3, "corp": "원천소프트(주)", "industry": "응용 소프트웨어 개발 및 공급업 (J58)", "model": "비외감", "grade": "2B", "asset": "412", "debt": "60", "sales": "386", "loan": "15", "weight": "150%", "weighted": "23"},
    {"rank": 4, "corp": "영통세미텍(주)", "industry": "기타 전자부품 제조업 (C26)", "model": "외감", "grade": "3A", "asset": "2,468", "debt": "110", "sales": "1,984", "loan": "30", "weight": "150%", "weighted": "45"},
    {"rank": 5, "corp": "매탄메디칼(주)", "industry": "기타 의료용 기기 제조업 (C27)", "model": "비외감", "grade": "3A", "asset": "683", "debt": "94", "sales": "572", "loan": "15", "weight": "150%", "weighted": "23"},
  ],
  top: [
    {"rank": 1, "name": "원천식품(주)", "size": "대기업", "grade": "3B", "industry": "I56111", "amount": "252.0", "share": "18.9"},
    {"rank": 2, "name": "(주)대성유통", "size": "외감", "grade": "6B", "industry": "G47190", "amount": "42.2", "share": "3.2"},
    {"rank": 3, "name": "삼정정밀(주)", "size": "외감", "grade": "3B", "industry": "C25929", "amount": "41.2", "share": "3.1"},
    {"rank": 4, "name": "권선전자", "size": "기업형소호", "grade": "5B", "industry": "L68112", "amount": "27.2", "share": "2.0"},
    {"rank": 5, "name": "(주)영통산업", "size": "외감", "grade": "3A", "industry": "M70113", "amount": "22.9", "share": "1.7"},
    {"rank": 6, "name": "푸른상사", "size": "기업형소호", "grade": "6A", "industry": "L68112", "amount": "22.9", "share": "1.7"},
    {"rank": 7, "name": "망포식품", "size": "기업형소호", "grade": "6B", "industry": "L68112", "amount": "22.1", "share": "1.7"},
    {"rank": 8, "name": "세류화학", "size": "기업형소호", "grade": "6A", "industry": "G46510", "amount": "21.5", "share": "1.6"},
    {"rank": 9, "name": "광교식품", "size": "기업형소호", "grade": "6C", "industry": "C25929", "amount": "20.6", "share": "1.5"},
    {"rank": 10, "name": "세류상사(주)", "size": "외감", "grade": "4A", "industry": "G46510", "amount": "20.2", "share": "1.5"},
  ],
  pool: [
    {"pool": "P01", "name": "주택담보대출(우량)", "seomin": "-", "lowCredit": "-", "brCnt": "54", "brAmt": "11,121", "brShare": "39.17", "bankShare": "33.36", "brDlq": "0.00", "provRate": "0.05"},
    {"pool": "P02", "name": "주택담보대출(일반)", "seomin": "-", "lowCredit": "-", "brCnt": "38", "brAmt": "5,952", "brShare": "20.96", "bankShare": "16.97", "brDlq": "1.42", "provRate": "0.15"},
    {"pool": "P03", "name": "전세자금대출", "seomin": "-", "lowCredit": "-", "brCnt": "39", "brAmt": "6,830", "brShare": "24.06", "bankShare": "26.89", "brDlq": "0.00", "provRate": "0.06"},
    {"pool": "P04", "name": "신용대출(우량 1~3등급)", "seomin": "-", "lowCredit": "-", "brCnt": "46", "brAmt": "2,497", "brShare": "8.80", "bankShare": "10.06", "brDlq": "0.00", "provRate": "0.23"},
    {"pool": "P05", "name": "신용대출(일반 4~6등급)", "seomin": "-", "lowCredit": "-", "brCnt": "37", "brAmt": "1,205", "brShare": "4.24", "bankShare": "6.33", "brDlq": "0.00", "provRate": "0.90"},
    {"pool": "P06", "name": "신용대출(저신용 7~10등급)", "seomin": "-", "lowCredit": "저신용", "brCnt": "16", "brAmt": "219", "brShare": "0.77", "bankShare": "1.29", "brDlq": "0.00", "provRate": "3.58"},
    {"pool": "P07", "name": "NH새희망홀씨대출", "seomin": "인정", "lowCredit": "저신용", "brCnt": "6", "brAmt": "129", "brShare": "0.45", "bankShare": "2.14", "brDlq": "0.00", "provRate": "4.68"},
    {"pool": "P08", "name": "햇살론(보증부)", "seomin": "-", "lowCredit": "저신용", "brCnt": "8", "brAmt": "143", "brShare": "0.50", "bankShare": "1.12", "brDlq": "0.00", "provRate": "0.45"},
    {"pool": "P09", "name": "사잇돌(보증부)", "seomin": "-", "lowCredit": "저신용", "brCnt": "8", "brAmt": "127", "brShare": "0.45", "bankShare": "0.78", "brDlq": "0.00", "provRate": "1.20"},
    {"pool": "P10", "name": "기타 소매", "seomin": "-", "lowCredit": "-", "brCnt": "8", "brAmt": "169", "brShare": "0.59", "bankShare": "1.05", "brDlq": "0.00", "provRate": "0.40"},
  ],
  seomin: [
    {"limit": "전행 평균 비중 도달 필요액", "basis": "지점 서민금융 비중을 전행 평균 수준으로", "amount": "490", "count": "22", "applied": "-"},
    {"limit": "충당금 증가 허용 범위", "basis": "추가 충당금 ≤ 허용액 (충당금률 가정)", "amount": "427", "count": "19", "applied": "적용(최소)"},
    {"limit": "반기 신규 가능 건수", "basis": "신규 가능 건수 × 평균 취급액", "amount": "687", "count": "30", "applied": "-"},
    {"limit": "권고 규모", "basis": "세 한도 중 최소", "amount": "427", "count": "19", "applied": "권고"},
  ],
};
const NOTE_PROSPECT =
  "본부 추천 기업 중 제외 — 지역 외 61개 · 예상재무등급 3B 초과 1개 · 부채비율 200% 초과 1개 · 지점 집중 업종(C25, F42, G46, G47, I56, L68, Q86, 금액 비중 5.0% 이상) 1개 · 업종 중복 1개 · 후보 상한(5개) 초과 2개. 신규 여신 가정액은 NICS 모형별 가정값(규칙 BRANCH_PROSPECT_POLICY · 시뮬레이션 가정), 금액 단위 억원.";
const CHART_BAND: { name: string; points: { label: string; value: number }[] }[] = [{"name": "지점", "points": [{"label": "1~3B", "value": 27.0}, {"label": "4A~4B", "value": 9.1}, {"label": "5A~5C", "value": 38.3}, {"label": "6A~6C", "value": 25.5}, {"label": "7A~8", "value": 0.1}]}, {"name": "전행", "points": [{"label": "1~3B", "value": 48.0}, {"label": "4A~4B", "value": 23.1}, {"label": "5A~5C", "value": 19.3}, {"label": "6A~6C", "value": 8.7}, {"label": "7A~8", "value": 0.8}]}];
const CHART_POOL: { name: string; points: { label: string; value: number }[] }[] = [{"name": "지점", "points": [{"label": "주택담보", "value": 60.1}, {"label": "전세", "value": 24.1}, {"label": "신용", "value": 13.8}, {"label": "서민금융", "value": 1.4}, {"label": "기타", "value": 0.6}]}, {"name": "전행", "points": [{"label": "주택담보", "value": 50.3}, {"label": "전세", "value": 26.9}, {"label": "신용", "value": 17.7}, {"label": "서민금융", "value": 4.0}, {"label": "기타", "value": 1.1}]}];
const KPI_GROUPS: KpiGroup[] = [
 {
  "max": 200,
  "code": "CUST",
  "kind": "kpi",
  "items": [
   {
    "max": 90,
    "code": "CUST_BASE",
    "label": "고객기반 확대",
    "score": 58.0,
    "details": [],
    "docPage": null,
    "prevMax": 90,
    "changeType": null,
    "changeSummary": null
   },
   {
    "max": 60,
    "code": "CUST_DIGITAL",
    "label": "디지털 고객",
    "score": 41.0,
    "details": [],
    "docPage": null,
    "prevMax": 60,
    "changeType": null,
    "changeSummary": null
   },
   {
    "max": 50,
    "code": "CUST_CS",
    "label": "고객만족 · 소비자보호",
    "score": 38.0,
    "details": [],
    "docPage": null,
    "prevMax": 50,
    "changeType": null,
    "changeSummary": null
   }
  ],
  "label": "고객KPI",
  "score": 137.0,
  "prevMax": 200
 },
 {
  "max": 500,
  "code": "BIZ",
  "kind": "kpi",
  "items": [
   {
    "max": 220,
    "code": "BIZ_CORE",
    "label": "핵심사업",
    "score": 107.0,
    "details": [
     {
      "max": 60,
      "code": "CORE_CORP_LOAN",
      "label": "기업여신 증대",
      "score": 31.0,
      "actual": 4820.0,
      "target": 9300.0,
      "docPage": "84",
      "prevMax": 100,
      "actualUnit": "백만원",
      "changeType": "변경",
      "changeSummary": "배점 100 → 60 (40점을 우량기업여신으로 이관)"
     },
     {
      "max": 40,
      "code": "CORE_PRIME",
      "label": "우량기업여신",
      "score": 4.0,
      "actual": 6000.0,
      "target": 60000.0,
      "docPage": "84~91",
      "prevMax": null,
      "actualUnit": "백만원(가중)",
      "changeType": "신설",
      "changeSummary": "신규 · 증액 유치한 기업여신을 차주 신용등급 구간별 가중치(1~3B 150% … 7A 이하 50%)로 환산해 실적 인정 — 우량기업여신 유치 우대"
     },
     {
      "max": 120,
      "code": "CORE_DEPOSIT",
      "label": "저원가성 예금",
      "score": 72.0,
      "docPage": null,
      "prevMax": 120,
      "changeType": null,
      "changeSummary": null
     }
    ],
    "docPage": null,
    "prevMax": 220,
    "changeType": null,
    "changeSummary": null
   },
   {
    "max": 160,
    "code": "BIZ_STRAT",
    "label": "전략사업",
    "score": 88.0,
    "details": [],
    "docPage": "15",
    "prevMax": 180,
    "changeType": "변경",
    "changeSummary": "배점 180 → 160 (20점을 생산적·포용금융으로 이관)"
   },
   {
    "max": 120,
    "code": "BIZ_INCL",
    "label": "생산적·포용금융",
    "score": 59.67,
    "details": [
     {
      "max": 60,
      "code": "INCL_PROD",
      "label": "생산적금융",
      "score": 33.0,
      "docPage": null,
      "prevMax": 60,
      "changeType": null,
      "changeSummary": null
     },
     {
      "max": 40,
      "code": "INCL_INCL",
      "label": "포용금융",
      "score": 24.0,
      "docPage": null,
      "prevMax": 40,
      "changeType": null,
      "changeSummary": null
     },
     {
      "max": 20,
      "code": "INCL_SEOMIN",
      "label": "서민금융",
      "score": 2.67,
      "actual": 4.0,
      "target": 30.0,
      "docPage": "126",
      "prevMax": null,
      "actualUnit": "건",
      "changeType": "신설",
      "changeSummary": "NH새희망홀씨대출(용도코드 1031 · 1032) 신규 유치 건수에 배점 부여, 해당 차주는 건전성평가 중 연체평가에서 제외"
     }
    ],
    "docPage": "15",
    "prevMax": 100,
    "changeType": "변경",
    "changeSummary": "배점 100 → 120 (서민금융 20점 신설)"
   }
  ],
  "label": "사업KPI",
  "score": 254.7,
  "prevMax": 500
 },
 {
  "max": 300,
  "code": "FIN",
  "kind": "kpi",
  "items": [
   {
    "max": 180,
    "code": "FIN_PROFIT",
    "label": "수익성(총이익)",
    "score": 118.0,
    "details": [],
    "docPage": null,
    "prevMax": 180,
    "changeType": null,
    "changeSummary": null
   },
   {
    "max": 120,
    "code": "FIN_SOUND",
    "label": "건전성",
    "score": 82.0,
    "details": [],
    "docPage": null,
    "prevMax": 120,
    "changeType": null,
    "changeSummary": null
   }
  ],
  "label": "재무KPI",
  "score": 200.0,
  "prevMax": 300
 },
 {
  "max": null,
  "code": "ADJ",
  "kind": "adjustment",
  "items": [
   {
    "max": null,
    "code": "ADJ_BONUS",
    "note": "지역사회 공헌",
    "label": "가점",
    "score": 5.0,
    "details": [],
    "docPage": null,
    "prevMax": null,
    "changeType": null,
    "changeSummary": null
   },
   {
    "max": null,
    "code": "ADJ_PENALTY",
    "note": "민원 발생",
    "label": "감점",
    "score": -3.0,
    "details": [],
    "docPage": null,
    "prevMax": null,
    "changeType": null,
    "changeSummary": null
   }
  ],
  "label": "가 · 감점",
  "score": 2.0,
  "prevMax": null
 }
];

/* ── 공통 ───────────────────────────────────────────────────── */
export const BRANCH_OFFICE: BranchOffice = { code: "001068", name: "수원영통지점", region: "경기", sigungu: "수원시", regionHq: "수도권1지역본부", orgCode: "001068" };
const PERIOD_LABEL = "2026년 하반기";

const EV_H2_PRIME = evidence("ev-br-h2-prime", "internal_direction", "26년(하) 업적평가 세부기준 — 핵심사업 > 우량기업여신 (84~91p)", {
  doc: { ...DOC.perfEvalH2, page: 84, sectionPath: "2. 영업본부/영업점 평가기준 > 나. 사업KPI > 핵심사업 > 우량기업여신" },
  relevance: 0.95,
  snippet: "신규 · 증액 유치한 기업여신은 차주 신용등급 구간별 가중치(1~3B 150% · 4A~4B 120% · 5A~5C 100% · 6A~6C 70% · 7A 이하 50%)를 적용한 금액을 실적으로 인정한다.",
});
const EV_H2_PRIME_NOTE = evidence("ev-br-h2-prime-note", "internal_direction", "26년(하) 업적평가 세부기준 — 우량기업여신 실적 산정 유의사항 (91p)", {
  doc: { ...DOC.perfEvalH2, page: 91, sectionPath: "2. 영업본부/영업점 평가기준 > 나. 사업KPI > 핵심사업 > 우량기업여신 > 유의사항" },
  relevance: 0.88,
  snippet: "기존 거래 차주의 대환 · 기한연장은 신규 · 증액 실적에서 제외하며, 신용등급은 취급 시점의 최종 신용등급을 적용한다.",
});
const EV_H1_CORE = evidence("ev-br-h1-core", "internal_direction", "26년(상) 업적평가 세부기준 — 핵심사업 > 기업여신 증대 (80p)", {
  doc: { ...DOC.perfEvalH1, page: 80, sectionPath: "2. 영업본부/영업점 평가기준 > 나. 사업KPI > 핵심사업 > 기업여신 증대" },
  relevance: 0.82,
  snippet: "기업여신 증대는 평잔 증가 금액 기준으로 평가하며 차주 신용등급에 따른 가중치는 두지 않는다.",
});
const EV_H2_SCHEME = evidence("ev-br-h2-scheme", "internal_direction", "26년(하) 업적평가 세부기준 — 영업점 배점표(리테일) (13p)", {
  doc: { ...DOC.perfEvalH2 },
  relevance: 0.9,
  snippet: "리테일 영업점 배점표: 고객KPI 200 · 사업KPI 500(핵심사업 220 · 전략사업 160 · 생산적·포용금융 120) · 재무KPI 300. 상반기 대비 우량기업여신 · 서민금융 항목 신설.",
});
const EV_NOTICE = evidence("ev-br-notice", "internal_direction", "[외감기업 활성화] 여신가망 재무우량 기업명세 제공 안내 (신용리스크관리부)", {
  doc: { ...DOC.prospectNotice },
  relevance: 0.9,
  snippet: "당행과 여신 미거래 중인 기업 중 재무등급 시산 결과가 우수한 상위규모 기업을 선정하여 붙임1 명세로 제공하니 영업점 마케팅에 활용하기 바람.",
});
const EV_H2_SEOMIN = evidence("ev-br-h2-seomin", "internal_direction", "26년(하) 업적평가 세부기준 — 생산적·포용금융 > ① 서민금융 (126p)", {
  doc: { ...DOC.perfEvalH2, page: 126, sectionPath: "2. 영업본부/영업점 평가기준 > 나. 사업KPI > 생산적·포용금융 > ① 서민금융" },
  relevance: 0.96,
  snippet: "NH새희망홀씨대출(용도코드 1031 · 1032)을 신규 유치한 경우 유치 건수에 따라 배점을 부여하며, 해당 차주는 건전성평가 중 연체평가에서 제외한다. 동일차주 연간 최고 대출한도는 35백만원.",
});
const EV_SOUND = evidence("ev-br-h2-soundness", "internal_direction", "26년(하) 업적평가 세부기준 — 재무KPI > 건전성 (118p)", {
  doc: { ...DOC.perfEvalH2, page: 118, sectionPath: "2. 영업본부/영업점 평가기준 > 다. 재무KPI > 건전성" },
  relevance: 0.84,
  snippet: "건전성은 연체평가와 충당금 전입액 증감으로 평가한다. 신규 취급 여신의 부실 발생 시 충당금 전입이 늘어 득점이 낮아질 수 있다.",
});
const EV_GOV_CORP = evidence("ev-br-gov-corp", "external_policy", "생산적 금융 공급 확대 및 기업금융 활성화 방안 (금융위원회)", {
  doc: DOC.corpLoanPolicy,
  relevance: 0.86,
  snippet: "기업여신 공급 확대 기조를 유지하고 생산적 부문에 대한 자금공급을 확대한다는 정책 방향이 제시됨.",
});
const EV_GOV_INCL = evidence("ev-br-gov-inclusive", "external_policy", "포용금융 확대방안 (금융위원회)", {
  doc: DOC.inclusivePolicy,
  relevance: 0.9,
  snippet: "2026년 1월 이후 서민·취약계층 금융공급 확대 기조가 제시됨.",
});
const EV_DATA_CORP = evidence("ev-br-data-corp", "bank_data", "기업 익스포저 차주별 현황 (Oblg_grd_def 2026.08)", {
  sourceKind: "metric_value",
  tableRef: "bank.OBLG_GRD_DEF · 조사자사무소코드 001068 · 카드전용 · 등급 체계 밖 제외",
  snippet: "지점 차주 · 대출잔액 · 규모 · 등급 분포와 전행 비교",
  figureId: "br_avg_grade",
});
const EV_DATA_PROSPECT = evidence("ev-br-data-prospect", "bank_data", "붙임1) 여신가망 재무우량 기업명세(2026)", {
  sourceKind: "metric_value",
  tableRef: "bank.CORP_PROSPECT · 지역 경기 수원시",
  snippet: "본사 소재지 · 예상재무등급 · 재무정보로 후보 선정",
  figureId: "br_prospect_cnt",
});
const EV_DATA_RETAIL = evidence("ev-br-data-retail", "bank_data", "소매여신 익스포저 월별 현황 (TB_JC_PM_C_LA 2026.08)", {
  sourceKind: "metric_value",
  tableRef: "bank.RETAIL_EXPOSURE · 사무소코드 001068 · Pool 정의(서민금융 인정)",
  snippet: "지점 · 전행 Pool별 익스포저와 서민금융 비중",
  figureId: "br_seomin_share",
});

/* ── 의견 (Agent) ───────────────────────────────────────────── */
export const PRIME_OPINION: Insight = {
  id: "ins-br-prime-corp",
  kind: "opinion",
  persona: "P3",
  domainCode: "loan",
  subDomain: "corporate",
  title: "본부 추천 우량기업 중심 신규 유치로 우량기업여신 가점 확보",
  statement:
    "하반기 업적평가는 핵심사업에 등급 가중 실적으로 평가하는 우량기업여신([[fig:br_prime_points]]점)을 신설했습니다. 지점은 소기업 비중이 금액 기준 [[fig:br_micro_amt_share]]로 전행 [[fig:bank_micro_amt_share]]보다 높아 평균 신용등급이 [[fig:br_avg_grade]]단계로 전행 [[fig:bank_avg_grade]]단계보다 낮습니다. 본부 추천 재무우량 기업 중 수원시 소재 · 업종 비중복 후보 [[fig:br_prospect_cnt]]개(신규 여신 가정 [[fig:br_prospect_amt]])를 유치하면 평균 등급은 [[fig:br_avg_grade_after]]단계로 개선되고 우량기업여신 득점은 [[fig:br_prime_uplift]]점 오를 것으로 추정됩니다. 건전성 감점을 피하도록 예상재무등급 3B 이내 우량 차주 중심으로 접촉하기를 권합니다.",
  severity: "watch",
  asOf: AS_OF,
  dataOrigin: "simulated",
  figures: figs("br_prime_points", "br_micro_amt_share", "bank_micro_amt_share", "br_avg_grade", "bank_avg_grade", "br_prospect_cnt", "br_prospect_amt", "br_avg_grade_after", "br_prime_uplift"),
  evidence: [EV_H2_PRIME, EV_H1_CORE, EV_NOTICE, EV_DATA_CORP, EV_DATA_PROSPECT, EV_GOV_CORP],
  verifications: PASSED_VERIFICATIONS,
  reportKind: "branch_prime_corp",
  reportAnchor: "bp-effect",
  tabKey: "prime-corp",
};

export const SEOMIN_OPINION: Insight = {
  id: "ins-br-seomin",
  kind: "opinion",
  persona: "P3",
  domainCode: "loan",
  subDomain: "retail",
  title: "건전성 범위 안에서 NH새희망홀씨 신규 유치로 서민금융 가점 확보",
  statement:
    "하반기 업적평가는 생산적·포용금융에 NH새희망홀씨 신규 유치 건수로 평가하는 서민금융([[fig:br_seomin_points]]점)을 신설하고 해당 차주를 연체평가에서 제외했습니다. 지점 서민금융 비중은 [[fig:br_seomin_share]]로 전행 [[fig:bank_seomin_share]]보다 낮습니다. 전행 수준 도달에는 [[fig:br_seomin_gap_amt]]이 필요하지만 충당금 증가 허용 범위를 함께 고려해 [[fig:br_seomin_rec_cnt]] · [[fig:br_seomin_rec_amt]] 신규 유치를 권하며, 이 경우 서민금융 득점은 [[fig:br_seomin_uplift]]점 오를 것으로 추정됩니다. 동일차주 연간 최고 한도([[fig:br_seomin_limit]])를 지키고, 업적평가의 연체평가 예외와 별개로 실제 충당금이 [[fig:br_seomin_add_prov]] 늘 수 있음을 감안해 분할 유치와 사후관리를 병행하기 바랍니다.",
  severity: "watch",
  asOf: AS_OF,
  dataOrigin: "simulated",
  figures: figs("br_seomin_points", "br_seomin_share", "bank_seomin_share", "br_seomin_gap_amt", "br_seomin_rec_cnt", "br_seomin_rec_amt", "br_seomin_uplift", "br_seomin_limit", "br_seomin_add_prov"),
  evidence: [EV_H2_SEOMIN, EV_SOUND, EV_DATA_RETAIL, EV_GOV_INCL],
  verifications: PASSED_VERIFICATIONS,
  reportKind: "branch_seomin",
  reportAnchor: "bs-effect",
  tabKey: "seomin",
};

/* ── 2화면 · 핵심사업 > 우량기업여신 ───────────────────────── */
const SIZE_COLUMNS: ReportTableBlock["columns"] = [
  { key: "size", label: "기업규모" },
  { key: "brCnt", label: "지점 건수", align: "right" },
  { key: "brCntShare", label: "건 비중(%)", align: "right" },
  { key: "brAmt", label: "지점 잔액(억원)", align: "right" },
  { key: "brAmtShare", label: "금액 비중(%)", align: "right" },
  { key: "bankCntShare", label: "전행 건 비중(%)", align: "right" },
  { key: "bankAmtShare", label: "전행 금액 비중(%)", align: "right" },
  { key: "diffPp", label: "금액 비중 차(%p)", align: "right" },
];
const BAND_COLUMNS: ReportTableBlock["columns"] = [
  { key: "size", label: "기업규모" },
  { key: "b1", label: "1~3B", align: "right" },
  { key: "b2", label: "4A~4B", align: "right" },
  { key: "b3", label: "5A~5C", align: "right" },
  { key: "b4", label: "6A~6C", align: "right" },
  { key: "b5", label: "7A~8", align: "right" },
  { key: "total", label: "합계", align: "right" },
];

export const PRIME_REPORT: ReportDoc = {
  id: "rpt-branch-prime-corp",
  kind: "branch_prime_corp",
  title: "핵심사업 · 우량기업여신 — 업적평가 가점 확보 방안",
  subtitle: `${BRANCH_OFFICE.name} · ${PERIOD_LABEL} 업적평가 세부기준 변경 대응 · 기준일 2026.08.31`,
  asOf: AS_OF,
  generatedAt: GENERATED_AT,
  dataOrigin: "simulated",
  office: BRANCH_OFFICE,
  toc: [
    { id: "bp-change", label: "1. 업적평가 기준 변경", level: 2 },
    { id: "bp-portfolio", label: "2. 지점 기업여신 포트폴리오", level: 2 },
    { id: "bp-size", label: "① 기업규모별", level: 3 },
    { id: "bp-grade", label: "② 신용등급별", level: 3 },
    { id: "bp-cross", label: "③ 규모 × 등급", level: 3 },
    { id: "bp-finding", label: "3. 분석 결과", level: 2 },
    { id: "bp-prospect", label: "4. 마케팅 후보", level: 2 },
    { id: "bp-effect", label: "5. 기대 효과", level: 2 },
    { id: "bp-caution", label: "6. 영업 시 유의사항", level: 2 },
  ],
  sections: [
    {
      id: "bp-change",
      heading: "1. 업적평가 기준 변경 — 사업KPI > 핵심사업 > 우량기업여신",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "2026년 하반기 업적평가 세부기준(84~91p)은 핵심사업에 우량기업여신([[fig:br_prime_points]]점)을 신설했습니다. 신규 · 증액 유치한 기업여신을 차주 신용등급 구간별 가중치로 환산해 실적으로 인정하므로, 같은 금액을 유치해도 우량 차주일수록 득점이 커집니다. 상반기에는 기업여신 증대를 금액 기준으로만 평가했습니다.",
        },
        { type: "table", table: { caption: "우량기업여신 신용등급 구간별 가중치 (2026년 하반기 신설)", columns: [{ key: "band", label: "등급 구간" }, { key: "grades", label: "해당 등급" }, { key: "h1", label: "상반기", align: "right" }, { key: "h2", label: "하반기", align: "right" }], rows: T.weights, note: "가중치는 세부기준 원본 수령 전 시뮬레이션 가정(규칙 BRANCH_PRIME_CORP_POLICY)." } },
        {
          type: "callout",
          tone: "info",
          text: "변경 배경(추론) — 정부의 생산적 금융 공급 확대 · 기업금융 활성화 방안이 기업여신 공급 확대를 요구하는 가운데, 확대 과정의 자산 건전성 저하를 막기 위해 우량 차주 유치에 가점을 주는 방식으로 평가 기준을 조정한 것으로 보입니다.",
        },
      ],
    },
    {
      id: "bp-portfolio",
      heading: "2. 지점 기업여신 포트폴리오",
      level: 2,
      blocks: [
        {
          type: "kv",
          kv: [
            { label: "차주 수", value: "[[fig:br_corp_cnt]] (전행 [[fig:bank_corp_cnt]])" },
            { label: "대출잔액", value: "[[fig:br_corp_amt]] (전행 [[fig:bank_corp_amt]])" },
            { label: "평균 신용등급", value: "[[fig:br_avg_grade]]단계 (전행 [[fig:bank_avg_grade]]단계)" },
            { label: "분석 제외", value: "카드 전용 차주 · 등급 체계(1~16) 밖 값" },
          ],
        },
      ],
    },
    { id: "bp-size", heading: "① 기업규모별 익스포저", level: 3, blocks: [{ type: "table", table: { caption: "기업규모별 익스포저 현황 — 지점 vs 전행", columns: SIZE_COLUMNS, rows: T.size, highlightRowKey: "size", highlightRowValue: "소기업" } }] },
    {
      id: "bp-grade",
      heading: "② 신용등급별 익스포저",
      level: 3,
      blocks: [
        { type: "chart", chart: { kind: "bar", title: "신용등급 구간별 금액 비중 — 지점 vs 전행", series: CHART_BAND, unit: "PCT" } },
        {
          type: "table",
          table: {
            caption: "신용등급별 익스포저 현황 — 지점 vs 전행",
            columns: [
              { key: "grade", label: "등급" },
              { key: "brCnt", label: "지점 건수", align: "right" },
              { key: "brCntShare", label: "건 비중(%)", align: "right" },
              { key: "brAmt", label: "지점 잔액(억원)", align: "right" },
              { key: "brAmtShare", label: "금액 비중(%)", align: "right" },
              { key: "bankCntShare", label: "전행 건 비중(%)", align: "right" },
              { key: "bankAmtShare", label: "전행 금액 비중(%)", align: "right" },
            ],
            rows: T.grade,
            note: "데이터의 최종NICS신용등급 1~16 을 1 · 2A · 2B … 7B · 8 의 16단계로 매핑(규칙 CORP_GRADE_SCALE).",
          },
        },
      ],
    },
    {
      id: "bp-cross",
      heading: "③ 기업규모 × 신용등급 구간",
      level: 3,
      blocks: [
        { type: "table", table: { caption: "기업규모 × 신용등급 구간 — 건수 기준 비중(지점 전체 = 100%)", columns: BAND_COLUMNS, rows: T.sizeGradeCount } },
        { type: "table", table: { caption: "기업규모 × 신용등급 구간 — 금액 기준 비중(지점 전체 = 100%)", columns: BAND_COLUMNS, rows: T.sizeGradeAmount } },
        {
          type: "table",
          table: {
            caption: "지점 기업여신 상위 차주 (대출잔액 순)",
            columns: [
              { key: "rank", label: "순위", align: "right" },
              { key: "name", label: "차주명" },
              { key: "size", label: "규모" },
              { key: "grade", label: "등급" },
              { key: "industry", label: "업종코드" },
              { key: "amount", label: "잔액(억원)", align: "right" },
              { key: "share", label: "비중(%)", align: "right" },
            ],
            rows: T.top,
          },
        },
      ],
    },
    {
      id: "bp-finding",
      heading: "3. 분석 결과 — 우량기업여신 실적 수준",
      level: 2,
      blocks: [
        {
          type: "ul",
          items: [
            "① 지점은 전행 대비 소기업 비중이 높습니다 — 금액 기준 [[fig:br_micro_amt_share]](전행 [[fig:bank_micro_amt_share]]), 건수 기준 [[fig:br_micro_cnt_share]](전행 [[fig:bank_micro_cnt_share]]). 대기업 · 외감 · 비외감 비중은 금액 기준 [[fig:br_upper_amt_share]]로 전행 [[fig:bank_upper_amt_share]]보다 낮습니다.",
            "② 전행 기준 소기업 차주의 평균 신용등급은 [[fig:bank_micro_avg_grade]]단계로, 대기업 · 외감 · 비외감 차주 평균 [[fig:bank_upper_avg_grade]]단계보다 낮습니다(값이 클수록 위험).",
            "③ 그 결과 지점 익스포저의 평균 신용등급은 [[fig:br_avg_grade]]단계로 전행 [[fig:bank_avg_grade]]단계보다 [[fig:br_avg_grade_gap]]단계 낮은 수준입니다.",
          ],
        },
        { type: "callout", tone: "attention", text: "등급 가중치가 적용되는 하반기에는 지금의 포트폴리오 구성만으로는 우량기업여신 득점이 [[fig:br_prime_score_now]]점(배점 [[fig:br_prime_points]]점)에 머뭅니다." },
      ],
    },
    {
      id: "bp-prospect",
      heading: "4. 마케팅 후보 — 본부 추천 여신가망 재무우량 기업",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "신용리스크관리부가 공유한 여신가망 재무우량 기업명세(당행 여신 미거래 · 재무등급 시산 우수 상위규모 기업)에서 본사 소재지가 지점 영업구역(경기 수원시)인 기업을 찾고, 지점 포트폴리오와 업종이 겹치지 않으면서 재무구성 · 예상재무등급이 우수한 기업을 추렸습니다.",
        },
        {
          type: "table",
          table: {
            caption: "마케팅 후보 기업 — 본부 추천 여신가망 재무우량 기업 중 선정",
            columns: [
              { key: "rank", label: "순위", align: "right" },
              { key: "corp", label: "기업명" },
              { key: "industry", label: "업종(중분류)" },
              { key: "model", label: "규모(NICS)" },
              { key: "grade", label: "예상재무등급" },
              { key: "asset", label: "자산총계(억원)", align: "right" },
              { key: "debt", label: "부채비율(%)", align: "right" },
              { key: "sales", label: "매출액(억원)", align: "right" },
              { key: "loan", label: "신규 여신 가정(억원)", align: "right" },
              { key: "weight", label: "가중치", align: "right" },
              { key: "weighted", label: "가중 실적(억원)", align: "right" },
            ],
            rows: T.prospects,
            note: NOTE_PROSPECT,
          },
        },
      ],
    },
    {
      id: "bp-effect",
      heading: "5. 기대 효과",
      level: 2,
      blocks: [
        {
          type: "kv",
          kv: [
            { label: "후보 기업", value: "[[fig:br_prospect_cnt]]개 · 신규 여신 가정 [[fig:br_prospect_amt]]" },
            { label: "후보 평균 등급", value: "[[fig:br_prospect_avg_grade]]단계 (금액 가중)" },
            { label: "지점 평균 등급", value: "[[fig:br_avg_grade]] → [[fig:br_avg_grade_after]]단계 ([[fig:br_avg_grade_improve]]단계 개선)" },
            { label: "등급 가중 실적", value: "[[fig:br_prime_actual]] → +[[fig:br_prospect_weighted]] (만점 목표 [[fig:br_prime_target]])" },
            { label: "우량기업여신 득점", value: "[[fig:br_prime_score_now]] → [[fig:br_prime_score_after]]점 (+[[fig:br_prime_uplift]]점)" },
          ],
        },
        {
          type: "callout",
          tone: "success",
          text: "업적평가 가점을 확보하면서 지점 포트폴리오의 평균 신용등급을 끌어올리고 업종 집중을 완화하는 방향입니다. 우량 차주는 충당금 부담이 작아 재무KPI 건전성 · 수익성에도 부담이 적습니다.",
        },
      ],
    },
    {
      id: "bp-caution",
      heading: "6. 영업 시 유의사항",
      level: 2,
      blocks: [
        {
          type: "ul",
          items: [
            "사업KPI 가점을 위해 기업여신을 늘리더라도 등급이 낮은 차주가 늘면 충당금 전입이 늘어 재무KPI 건전성 항목에서 감점될 수 있습니다 — 예상재무등급 3B 이내 우량 차주 중심으로 유치합니다.",
            "후보의 등급은 재무등급 시산 결과입니다. 실제 취급은 신용평가 · 담보 · 한도 심사를 거쳐 확정합니다.",
            "기존 거래 차주의 대환 · 기한연장은 신규 · 증액 실적에서 제외됩니다(세부기준 91p).",
            "음식점 · 도매 · 부동산 임대 등 지점 집중 업종은 후보에서 제외했습니다. 신규 유치 시에도 업종 분산을 유지합니다.",
          ],
        },
      ],
    },
  ],
  figures: figs(...Object.keys(SPEC).filter((k) => !k.includes("seomin") && !k.includes("retail") && !k.includes("lowcredit") && !k.startsWith("br_seg") && !k.startsWith("br_kpi"))),
  opinions: [PRIME_OPINION],
  evidence: [EV_H2_PRIME, EV_H2_PRIME_NOTE, EV_H1_CORE, EV_H2_SCHEME, EV_NOTICE, EV_DATA_CORP, EV_DATA_PROSPECT, EV_GOV_CORP],
  limitations: [
    "업적평가 세부기준(상 · 하반기) 원본을 받기 전이라 배점 · 가중치 · 목표는 시뮬레이션 가정입니다.",
    "기업 익스포저 · 가망기업 명세는 컬럼 정의서 구조에 맞춘 시뮬레이션 데이터입니다. 실제 파일을 올리면 같은 정의로 다시 계산됩니다.",
  ],
};

/* ── 3화면 · 생산적·포용금융 > 서민금융 ─────────────────────── */
export const SEOMIN_REPORT: ReportDoc = {
  id: "rpt-branch-seomin",
  kind: "branch_seomin",
  title: "생산적·포용금융 · 서민금융 — 신규 유치 적정 규모",
  subtitle: `${BRANCH_OFFICE.name} · ${PERIOD_LABEL} 업적평가 세부기준 신설 대응 · 기준일 2026.08.31`,
  asOf: AS_OF,
  generatedAt: GENERATED_AT,
  dataOrigin: "simulated",
  office: BRANCH_OFFICE,
  toc: [
    { id: "bs-change", label: "1. 업적평가 기준 신설", level: 2 },
    { id: "bs-portfolio", label: "2. 지점 소매여신 포트폴리오", level: 2 },
    { id: "bs-level", label: "3. 서민금융 보유 수준", level: 2 },
    { id: "bs-size", label: "4. 신규 유치 적정 규모", level: 2 },
    { id: "bs-effect", label: "5. 기대 효과와 영향", level: 2 },
    { id: "bs-caution", label: "6. 유의사항", level: 2 },
  ],
  sections: [
    {
      id: "bs-change",
      heading: "1. 업적평가 기준 신설 — 사업KPI > 생산적·포용금융 > ① 서민금융",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "2026년 하반기 업적평가 세부기준(126p)은 생산적·포용금융에 서민금융([[fig:br_seomin_points]]점)을 신설했습니다. NH새희망홀씨대출을 신규 유치하면 건수에 따라 득점을 인정하고, 해당 차주는 상대적으로 건전성이 낮을 수 있어 건전성평가 중 연체평가에서 제외합니다. 상반기에는 이 항목이 없었습니다.",
        },
        {
          type: "kv",
          kv: [
            { label: "대상 상품", value: "NH새희망홀씨대출 (용도코드 1031 · 1032)" },
            { label: "배점", value: "[[fig:br_seomin_points]]점 · 만점 목표 [[fig:br_seomin_target]]" },
            { label: "평가 특례", value: "건전성평가 중 연체평가 제외" },
            { label: "동일차주 한도", value: "연간 최고 [[fig:br_seomin_limit]]" },
          ],
        },
        {
          type: "callout",
          tone: "info",
          text: "신설 배경(외부 정책) — 금융위원회 포용금융 확대방안은 서민 · 취약계층 금융공급 확대 기조를 제시했습니다. 영업점 단위 서민금융 공급 실적을 평가에 넣고 연체평가에서 예외로 두어, 연체 부담으로 공급이 위축되지 않도록 한 것으로 보입니다.",
        },
      ],
    },
    {
      id: "bs-portfolio",
      heading: "2. 지점 소매여신 포트폴리오",
      level: 2,
      blocks: [
        {
          type: "kv",
          kv: [
            { label: "소매여신 익스포저", value: "[[fig:br_retail_amt]] · [[fig:br_retail_cnt]]" },
            { label: "저신용자 Pool 비중", value: "[[fig:br_lowcredit_share]] (전행 [[fig:bank_lowcredit_share]])" },
            { label: "연체율(금액)", value: "[[fig:br_retail_dlq_rate]] (전행 [[fig:bank_retail_dlq_rate]])" },
          ],
        },
        { type: "chart", chart: { kind: "bar", title: "상품군별 금액 비중 — 지점 vs 전행", series: CHART_POOL, unit: "PCT" } },
        {
          type: "table",
          table: {
            caption: "소매여신 Pool별 익스포저 — 지점 vs 전행",
            columns: [
              { key: "pool", label: "Pool" },
              { key: "name", label: "Pool 명" },
              { key: "seomin", label: "서민금융" },
              { key: "lowCredit", label: "저신용" },
              { key: "brCnt", label: "지점 건수", align: "right" },
              { key: "brAmt", label: "지점 익스포저(백만원)", align: "right" },
              { key: "brShare", label: "지점 비중(%)", align: "right" },
              { key: "bankShare", label: "전행 비중(%)", align: "right" },
              { key: "brDlq", label: "지점 연체율(%)", align: "right" },
              { key: "provRate", label: "충당금률(%·가정)", align: "right" },
            ],
            rows: T.pool,
            highlightRowKey: "pool",
            highlightRowValue: "P07",
            note: "Pool 정의(서민금융 인정 · 저신용 · 충당금률 = PD × LGD)는 시뮬레이션 가정 — 실제 Pool 체계 수령 시 마스터만 교체.",
          },
        },
      ],
    },
    {
      id: "bs-level",
      heading: "3. 서민금융 보유 수준 — 전행 대비",
      level: 2,
      blocks: [
        {
          type: "ul",
          items: [
            "지점 서민금융(업적평가 인정 Pool) 익스포저는 [[fig:br_seomin_amt]] · [[fig:br_seomin_cnt]]입니다.",
            "금액 비중 [[fig:br_seomin_share]]로 전행 [[fig:bank_seomin_share]]보다 [[fig:br_seomin_share_gap]] 낮고, 건수 비중도 [[fig:br_seomin_cnt_share]](전행 [[fig:bank_seomin_cnt_share]])로 낮습니다.",
            "하반기 서민금융 신규 실적은 [[fig:br_seomin_actual]]이며 현재 득점은 [[fig:br_seomin_score_now]]점입니다.",
          ],
        },
      ],
    },
    {
      id: "bs-size",
      heading: "4. 신규 유치 적정 규모",
      level: 2,
      blocks: [
        {
          type: "p",
          text: "세 가지 한도로 최대 유치액을 구하고 가장 작은 값을 권고 규모로 정했습니다. 평균 취급액은 전행 서민금융 차주당 평균([[fig:br_seomin_ticket_avg]])을 동일차주 최고 한도([[fig:br_seomin_limit]]) 이내로 적용한 [[fig:br_seomin_ticket]]입니다.",
        },
        {
          type: "table",
          table: {
            caption: "신규 유치 규모 산정 — 한도별 비교",
            columns: [
              { key: "limit", label: "한도" },
              { key: "basis", label: "산정 기준" },
              { key: "amount", label: "최대 유치액(백만원)", align: "right" },
              { key: "count", label: "건수", align: "right" },
              { key: "applied", label: "적용" },
            ],
            rows: T.seomin,
            highlightRowKey: "applied",
            highlightRowValue: "권고",
          },
        },
        {
          type: "kv",
          kv: [
            { label: "충당금률(가정)", value: "[[fig:br_seomin_prov_rate]]" },
            { label: "충당금 증가 허용액", value: "[[fig:br_seomin_prov_limit]] (시뮬레이션 가정)" },
            { label: "반기 신규 가능 건수", value: "[[fig:br_seomin_max_cnt]] (시뮬레이션 가정)" },
          ],
        },
      ],
    },
    {
      id: "bs-effect",
      heading: "5. 기대 효과와 영향",
      level: 2,
      blocks: [
        {
          type: "kv",
          kv: [
            { label: "권고 신규 유치", value: "[[fig:br_seomin_rec_cnt]] · [[fig:br_seomin_rec_amt]]" },
            { label: "유치 후 서민금융 비중", value: "[[fig:br_seomin_share]] → [[fig:br_seomin_share_after]]" },
            { label: "서민금융 득점", value: "[[fig:br_seomin_score_now]] → [[fig:br_seomin_score_after]]점 (+[[fig:br_seomin_uplift]]점)" },
            { label: "예상 추가 충당금", value: "[[fig:br_seomin_add_prov]] (업적평가와 별개로 지점 손익에 반영)" },
            { label: "전행 서민금융 연체율", value: "[[fig:bank_seomin_dlq_rate]]" },
          ],
        },
      ],
    },
    {
      id: "bs-caution",
      heading: "6. 유의사항",
      level: 2,
      blocks: [
        {
          type: "ul",
          items: [
            "동일차주 연간 최고 대출한도는 [[fig:br_seomin_limit]]입니다. 한도를 나눠 쓰는 쪼개기 취급은 실적으로 인정되지 않을 수 있습니다.",
            "연체평가 예외는 업적평가에만 적용됩니다. 실제 연체 · 부실은 충당금 전입으로 지점 손익과 재무KPI에 반영되므로 상환능력 심사 기준을 지킵니다.",
            "한 번에 늘리기보다 월별로 나눠 유치하고, 취급 후 3개월 연체 발생을 점검합니다.",
            "권고 규모는 세 한도 중 최소값입니다. 어떤 한도가 적용됐는지는 표의 적용 열에서 확인하고, 충당금 증가 허용액 · 신규 가능 건수는 지점 여건에 맞게 규칙(BRANCH_SEOMIN_POLICY)에서 조정할 수 있습니다.",
          ],
        },
      ],
    },
  ],
  figures: figs(...Object.keys(SPEC).filter((k) => k.includes("seomin") || k.includes("retail") || k.includes("lowcredit"))),
  opinions: [SEOMIN_OPINION],
  evidence: [EV_H2_SEOMIN, EV_SOUND, EV_H2_SCHEME, EV_DATA_RETAIL, EV_GOV_INCL],
  limitations: [
    "업적평가 세부기준 원본을 받기 전이라 배점 · 목표 건수 · 용도코드는 시뮬레이션 가정입니다.",
    "TB_JC_PM_C_LA 상세 컬럼명이 확정되지 않아 컬럼명은 가정이며 한글 별칭으로도 받습니다.",
    "충당금률 · 충당금 증가 허용액 · 신규 가능 건수는 규칙(BRANCH_SEOMIN_POLICY)의 시뮬레이션 가정입니다.",
  ],
};

export const BRANCH_REPORTS: Record<string, ReportDoc> = { "prime-corp": PRIME_REPORT, seomin: SEOMIN_REPORT };

/* ── 탭 ─────────────────────────────────────────────────────── */
const TABS: AnalysisTab[] = [
  { tabKey: "prime-corp", label: "핵심사업 · 우량기업여신", reportKind: "branch_prime_corp", reportKey: "report.branch-prime-corp", insightId: PRIME_OPINION.id, severity: "watch", generation: "current", asOf: AS_OF, generatedAt: GENERATED_AT },
  { tabKey: "seomin", label: "생산적·포용금융 · 서민금융", reportKind: "branch_seomin", reportKey: "report.branch-seomin", insightId: SEOMIN_OPINION.id, severity: "watch", generation: "current", asOf: AS_OF, generatedAt: GENERATED_AT },
];
export const BRANCH_TABS: BranchTabs = { office: BRANCH_OFFICE, current: TABS, previous: [] };

/* ── 1화면 · 대시보드 ───────────────────────────────────────── */
const ALERTS: BranchKpiAlert[] = [
  {
    id: "alert-prime-corp",
    path: "사업KPI > 핵심사업 > 우량기업여신",
    changeType: "신설",
    title: PRIME_OPINION.title,
    summary: "신용등급 가중 실적으로 평가 — 지점 평균 등급 [[fig:br_avg_grade]]단계(전행 [[fig:bank_avg_grade]]단계). 본부 추천 우량기업 [[fig:br_prospect_cnt]]개 유치 시 +[[fig:br_prime_uplift]]점",
    tabKey: "prime-corp",
    insightId: PRIME_OPINION.id,
    severity: "watch",
    uplift: F("br_prime_uplift"),
  },
  {
    id: "alert-seomin",
    path: "사업KPI > 생산적·포용금융 > 서민금융",
    changeType: "신설",
    title: SEOMIN_OPINION.title,
    summary: "NH새희망홀씨 신규 유치 건수로 평가 · 연체평가 예외 — 지점 비중 [[fig:br_seomin_share]](전행 [[fig:bank_seomin_share]]). [[fig:br_seomin_rec_cnt]] 유치 시 +[[fig:br_seomin_uplift]]점",
    tabKey: "seomin",
    insightId: SEOMIN_OPINION.id,
    severity: "watch",
    uplift: F("br_seomin_uplift"),
  },
];

const SEGMENTS: DomainCardInfo[] = [
  { domainCode: "loan", name: "여신", status: "active", headline: F("br_loan_total"), sub: [{ label: "기업여신", figure: F("br_corp_amt") }, { label: "소매여신", figure: F("br_retail_amt") }] },
  { domainCode: "deposit", name: "수신", status: "placeholder", headline: F("br_seg_deposit"), note: "평잔 기준" },
  { domainCode: "fx", name: "외환", status: "placeholder", headline: F("br_seg_fx"), note: "누적 실적" },
  { domainCode: "pension", name: "퇴직연금", status: "placeholder", headline: F("br_seg_pension"), note: "적립금" },
  { domainCode: "card", name: "카드", status: "placeholder", headline: F("br_seg_card"), note: "누적 이용실적" },
];

export const BRANCH_DASHBOARD: Omit<BranchDashboard, "available" | "viewer"> = {
  office: BRANCH_OFFICE,
  asOf: AS_OF,
  generatedAt: GENERATED_AT,
  dataOrigin: "simulated",
  periodLabel: PERIOD_LABEL,
  asOfLabel: "2026.08.31 (하반기 2개월 경과)",
  scorecard: { total: F("br_kpi_total"), max: F("br_kpi_max"), adjustments: F("br_kpi_adj"), uplift: F("br_kpi_uplift"), totalAfter: F("br_kpi_total_after"), groups: KPI_GROUPS },
  alerts: ALERTS,
  figures: figs("br_avg_grade", "bank_avg_grade", "br_prospect_cnt", "br_prime_uplift", "br_seomin_share", "bank_seomin_share", "br_seomin_rec_cnt", "br_seomin_uplift", "br_kpi_cust", "br_kpi_biz", "br_kpi_fin"),
  segments: SEGMENTS,
  loan: { total: F("br_loan_total"), corp: F("br_corp_amt"), corpCount: F("br_corp_cnt"), retail: F("br_retail_amt"), retailCount: F("br_retail_cnt"), avgGrade: F("br_avg_grade"), bankAvgGrade: F("bank_avg_grade"), avgGradeGap: F("br_avg_grade_gap") },
  evidence: [EV_H2_SCHEME, EV_H2_PRIME, EV_H2_SEOMIN, EV_GOV_CORP, EV_GOV_INCL] satisfies Evidence[],
};
