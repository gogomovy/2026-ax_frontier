import { describe, expect, it } from "vitest";
import { branchBankPair, figureIds, findTable, labelParts, num, politeTitle, severityFromText, shortTabLabel, shortUnit, splitGuideItem, stripCorp, stripTrailingParen } from "./analysisReport";
import type { Figure, ReportDoc, Severity } from "./types";

const fig = (id: string, value: number | null, unit: Figure["unit"] = "PCT", decimals = 2): Figure => ({ id, label: id, value, unit, decimals, dataOrigin: "unknown" });

describe("2단계 분석 결과 — 탭 이름 · 숫자 읽기", () => {
  it("탭 이름은 원 숫자를 빼고 마지막 조각만", () => {
    expect(shortTabLabel("핵심사업 · 우량기업여신")).toBe("우량기업여신");
    expect(shortTabLabel("생산적·포용금융 · 서민금융")).toBe("서민금융");
    expect(shortTabLabel("① 소기업 6B 등급 부도율 특이사항")).toBe("소기업 6B 등급 부도율 특이사항");
    expect(shortTabLabel("② 포용금융 확대 관련 신용리스크")).toBe("포용금융 확대 관련 신용리스크");
  });
  it("표 칸 글자를 숫자로", () => {
    expect(num("8,204")).toBe(8204);
    expect(num("+6,750")).toBe(6750);
    expect(num("150%")).toBe(150);
    expect(num("-24.0")).toBe(-24);
    expect(num("0.45")).toBe(0.45);
    expect(num("-")).toBeNull();
    expect(num("")).toBeNull();
    expect(num(null)).toBeNull();
    expect(num(3)).toBe(3);
  });
  it("표 머리의 단위 · 보조 말", () => {
    expect(labelParts("자산총계(억원)")).toEqual({ text: "자산총계", unit: "억원", qualifier: null });
    expect(labelParts("업종(중분류)")).toEqual({ text: "업종", unit: null, qualifier: "중분류" });
    expect(labelParts("가중치")).toEqual({ text: "가중치", unit: null, qualifier: null });
    expect(shortUnit("억원")).toBe("억");
    expect(shortUnit("백만원")).toBe("백만원");
  });
});

describe("2단계 분석 결과 — 보고서에서 찾기", () => {
  const report = {
    sections: [
      { id: "a", heading: "a", level: 2, blocks: [{ type: "table", table: { columns: [{ key: "x", label: "X" }], rows: [] } }] },
      { id: "b", heading: "b", level: 2, blocks: [{ type: "table", table: { caption: "후보", columns: [{ key: "corp", label: "기업명" }, { key: "grade", label: "등급" }, { key: "weighted", label: "가중" }], rows: [] } }] },
    ],
  } as unknown as ReportDoc;
  it("열 키를 모두 가진 표", () => {
    expect(findTable(report, ["corp", "grade", "weighted"])?.caption).toBe("후보");
    expect(findTable(report, ["nope"])).toBeNull();
  });
  it("수치 표식 · 지점 vs 전행 짝", () => {
    const text = "신용등급 가중 실적으로 평가 — 지점 평균 등급 [[fig:br_avg_grade]]단계(전행 [[fig:bank_avg_grade]]단계). 본부 추천 우량기업 [[fig:br_prospect_cnt]]개";
    expect(figureIds(text)).toEqual(["br_avg_grade", "bank_avg_grade", "br_prospect_cnt"]);
    const figures = { br_avg_grade: fig("br_avg_grade", 8.39, "NONE"), bank_avg_grade: fig("bank_avg_grade", 6.16, "NONE"), br_prospect_cnt: fig("br_prospect_cnt", 5, "NONE") };
    const pair = branchBankPair(text, figures);
    expect(pair?.ours.value).toBe(8.39);
    expect(pair?.bank.value).toBe(6.16);
    expect(branchBankPair("[[fig:br_prospect_cnt]]", figures)).toBeNull();
  });
  it("기업명 · 괄호 · 심각도 글자", () => {
    expect(stripCorp("신동에너지(주)")).toBe("신동에너지");
    expect(stripCorp("㈜영통상사")).toBe("영통상사");
    expect(stripTrailingParen("충당금 증가 허용액 (시뮬레이션 가정)")).toBe("충당금 증가 허용액");
    const labels: Record<Severity, string> = { info: "정상", watch: "관찰", caution: "주의", critical: "긴급" };
    expect(severityFromText("주의", labels)).toBe("caution");
    expect(severityFromText("없음", labels)).toBeNull();
  });
});

describe("2단계 분석 결과 — 유의사항 한 줄 나누기", () => {
  it("(a) 줄표 뒤가 제목", () => {
    const r = splitGuideItem("사업KPI 가점을 위해 기업여신을 늘리더라도 등급이 낮은 차주가 늘면 충당금 전입이 늘어 재무KPI 건전성 항목에서 감점될 수 있습니다 — 예상재무등급 3B 이내 우량 차주 중심으로 유치합니다.");
    expect(r.title).toBe("예상재무등급 3B 이내 우량 차주 중심으로 유치해요");
    expect(r.detail).toBe("사업KPI 가점을 위해 기업여신을 늘리더라도 등급이 낮은 차주가 늘면 충당금 전입이 늘어 재무KPI 건전성 항목에서 감점될 수 있어요");
  });
  it("(b) 첫 문장이 제목", () => {
    const r = splitGuideItem("후보의 등급은 재무등급 시산 결과입니다. 실제 취급은 신용평가 · 담보 · 한도 심사를 거쳐 확정합니다.");
    expect(r).toEqual({ title: "후보의 등급은 재무등급 시산 결과예요", detail: "실제 취급은 신용평가 · 담보 · 한도 심사를 거쳐 확정해요" });
  });
  it("(b) 수치로 끝나는 첫 문장 — 수치 글자 받침으로 '이에요'", () => {
    const figures = { br_seomin_limit: fig("br_seomin_limit", 35, "KRW_MN", 0) };
    const r = splitGuideItem("동일차주 연간 최고 대출한도는 [[fig:br_seomin_limit]]입니다. 한도를 나눠 쓰는 쪼개기 취급은 실적으로 인정되지 않을 수 있습니다.", figures);
    expect(r.title).toBe("동일차주 연간 최고 대출한도는 [[fig:br_seomin_limit]]이에요");
    expect(r.detail).toBe("한도를 나눠 쓰는 쪼개기 취급은 실적으로 인정되지 않을 수 있어요");
    expect(politeTitle("비중은 [[fig:x]]입니다.", { x: fig("x", 2.14, "PCT") })).toBe("비중은 [[fig:x]]예요");
  });
  it("(c) 끝 괄호가 설명", () => {
    expect(splitGuideItem("기존 거래 차주의 대환 · 기한연장은 신규 · 증액 실적에서 제외됩니다(세부기준 91p).")).toEqual({ title: "기존 거래 차주의 대환 · 기한연장은 신규 · 증액 실적에서 제외돼요", detail: "세부기준 91p" });
    expect(splitGuideItem("월 단위 연체 발생 건수·금액 및 연체율 추이 모니터링(소매모형 스코어 구간별)")).toEqual({ title: "월 단위 연체 발생 건수·금액 및 연체율 추이 모니터링", detail: "소매모형 스코어 구간별" });
  });
  it("(d) 제목만", () => {
    expect(splitGuideItem("신규 취급 후 3·6개월 경과 시점의 초기 연체(Vintage) 지표 관리")).toEqual({ title: "신규 취급 후 3·6개월 경과 시점의 초기 연체(Vintage) 지표 관리", detail: null });
    expect(splitGuideItem("한 번에 늘리기보다 월별로 나눠 유치하고, 취급 후 3개월 연체 발생을 점검합니다.")).toEqual({ title: "한 번에 늘리기보다 월별로 나눠 유치하고, 취급 후 3개월 연체 발생을 점검해요", detail: null });
  });
});
