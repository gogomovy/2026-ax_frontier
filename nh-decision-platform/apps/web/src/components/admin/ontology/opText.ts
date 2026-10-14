/* 온톨로지 변경 제안의 연산 한 줄 설명(업무 말) · 품질 등급 이름 — 화면 없이 시험하는 순수 함수 (Phase M · AGG-04) */

export type Op = Record<string, unknown> & { op: string };

export const GRADE_KO: Record<string, string> = { ok: "양호", warn: "주의", risk: "위험" };

function s(v: unknown): string {
  return v === undefined || v === null ? "" : String(v);
}

export function opText(o: Op): string {
  const c = (o.class ?? {}) as Record<string, unknown>;
  const r = (o.relation ?? {}) as Record<string, unknown>;
  const b = (o.backing ?? {}) as Record<string, unknown>;
  const p = (o.property ?? {}) as Record<string, unknown>;
  switch (o.op) {
    case "add_class": {
      const bk = Array.isArray(c.backing) && c.backing.length ? ` · 원천 ${(c.backing as Record<string, unknown>[]).map((x) => `${s(x.dataset)}(${s(x.key_col)})`).join(", ")}` : "";
      return `객체 유형 추가 — ${s(c.ko) || s(c.label)} (${s(c.label)})${bk}`;
    }
    case "update_class":
      return `객체 유형 고침 — ${s(o.label)}: ${Object.keys((o.set ?? {}) as object).join(", ")}`;
    case "add_property":
      return `속성 추가 — ${s(o.label)}.${s(p.name)}${p.ko ? ` (${s(p.ko)})` : ""}`;
    case "add_backing":
      return `원천 추가 — ${s(o.label)} ← ${s(b.dataset)}(${s(b.key_col)})`;
    case "add_relation":
      return `링크 유형 추가 — ${s(r.ko) || s(r.type)}: ${s(r.from)} → ${s(r.to)}${r.cardinality ? ` (${s(r.cardinality)})` : ""}`;
    case "update_relation":
      return `링크 유형 고침 — ${s(o.type)}: ${Object.keys((o.set ?? {}) as object).join(", ")}`;
    case "add_link_backing":
      return `링크 원천 — ${s(o.type)} ← ${s(b.dataset)}.${s(b.from_col)} → ${s(b.to_col)}`;
    case "add_alias":
      return `별칭 — ${s(o.label)} '${s(o.key)}' ← ${(Array.isArray(o.aliases) ? o.aliases : []).map(String).join(", ")}`;
    default:
      return o.op;
  }
}
