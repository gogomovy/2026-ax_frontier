import { describe, expect, it } from "vitest";
import { GRADE_KO, opText } from "./opText";

/* Phase M · AGG-04 — 변경 제안 연산을 관리자가 읽는 말로 */
describe("opText", () => {
  it("객체 유형 · 원천", () => {
    expect(opText({ op: "add_class", class: { label: "Branch", ko: "영업점", backing: [{ dataset: "BRANCH_MASTER", key_col: "code" }] } })).toBe("객체 유형 추가 — 영업점 (Branch) · 원천 BRANCH_MASTER(code)");
    expect(opText({ op: "add_backing", label: "Product", backing: { dataset: "P", key_col: "pc" } })).toBe("원천 추가 — Product ← P(pc)");
  });
  it("링크 · 링크 원천 · 별칭 · 속성", () => {
    expect(opText({ op: "add_relation", relation: { type: "IN_GROUP", ko: "상품군 소속", from: "Product", to: "ProductGroup", cardinality: "N:1" } })).toBe("링크 유형 추가 — 상품군 소속: Product → ProductGroup (N:1)");
    expect(opText({ op: "add_link_backing", type: "IN_GROUP", backing: { dataset: "P", from_col: "pc", to_col: "grp" } })).toBe("링크 원천 — IN_GROUP ← P.pc → grp");
    expect(opText({ op: "add_alias", label: "ProductGroup", key: "햇살론", aliases: ["햇살론15", "햇살론뱅크"] })).toBe("별칭 — ProductGroup '햇살론' ← 햇살론15, 햇살론뱅크");
    expect(opText({ op: "add_property", label: "Product", property: { name: "group", ko: "상품군" } })).toBe("속성 추가 — Product.group (상품군)");
  });
  it("고침 · 모르는 연산 · 등급 이름", () => {
    expect(opText({ op: "update_class", label: "Product", set: { ko: "상품", description: "x" } })).toBe("객체 유형 고침 — Product: ko, description");
    expect(opText({ op: "unknown_op" })).toBe("unknown_op");
    expect(GRADE_KO.risk).toBe("위험");
  });
});
