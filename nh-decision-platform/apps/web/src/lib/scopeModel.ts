/**
 * 업무 영역 모델 (Phase K · SCP-01~03 · Q151) — 서버 메뉴(`/me/menu`)의 묶음을 영역(종류) × 단위(부서 · 지점)로 묶는다.
 * 묶음이 어느 영역 · 조직인지는 서버가 붙인 `scope` · `orgCode`(관리자 [화면 설정 › 업무 영역])로 정하고, 주소 접두어로 짐작하지 않는다.
 * 화면 없이 시험할 수 있도록 React 를 쓰지 않는 순수 함수만 둔다(셸 훅은 components/layout/nav-model).
 */
import type { MenuItem, MenuPayload, MenuSection } from "@/components/providers/SessionProvider";
import { withOffice } from "./branchOffice";
import { matchLength, type NavItem } from "./nav";
import { EMPTY_CONFIG } from "./uiConfig";

export type ScopeKind = "hq" | "dept" | "branch" | "other";

/** 영역 안의 단위 — 사업부서 하나 · 지점 하나 */
export interface ScopeUnit {
  id: string;
  /** 조직(부서) · 사무소(지점) 코드 */
  code: string | null;
  name: string;
  /** 첫 화면 — 화면이 아직 없으면 null(준비 중) */
  home: string | null;
  available: boolean;
  /** 지점 단위 — 주소에 ?office= 를 붙여 그 지점을 본다 */
  office?: boolean;
  flow: NavItem[];
  reference: NavItem[];
}

export interface Scope {
  /** 안정적인 식별자 — 종류(hq · dept · branch), 그 밖의 묶음은 other:<묶음> */
  id: string;
  kind: ScopeKind;
  /** 전환 컨트롤에 쓰는 짧은 이름 (설정 ui.scopes.<종류>.label) */
  label: string;
  /** 지금 단위의 조직 · 지점 이름 (예: 신용리스크관리부) */
  orgName: string;
  home: string;
  flow: NavItem[];
  reference: NavItem[];
  /** 고를 수 있는 단위 — 둘 이상이면 전환 메뉴 */
  units: ScopeUnit[];
  unitId: string | null;
}

const KIND_ORDER: ScopeKind[] = ["hq", "dept", "branch", "other"];

export function toItem(i: MenuItem): NavItem {
  return {
    label: i.label,
    href: i.href,
    match: i.match.map((m) => m.replace(/^=/, "")),
    step: i.step ?? undefined,
    countKey: i.countKey ?? undefined,
    exact: i.match.some((m) => m.startsWith("=")),
  };
}

/** 메뉴 묶음 → 영역(종류)별 단위 묶음. office = 주소의 지점(?office=) */
export function scopesFromMenu(menu: MenuPayload, office: string | null): Scope[] {
  const cfg = menu.config ?? EMPTY_CONFIG;
  const withFlow = menu.sections.filter((s) => !s.admin && s.flow.length > 0);
  const byKind = new Map<ScopeKind, MenuSection[]>();
  const others: MenuSection[] = [];
  for (const s of withFlow) {
    const kind = (s.scope ?? null) as ScopeKind | null;
    if (kind && kind !== "other") byKind.set(kind, [...(byKind.get(kind) ?? []), s]);
    else others.push(s);
  }
  const sectionUnit = (s: MenuSection, kind: ScopeKind): ScopeUnit => {
    const flow = s.flow.map(toItem);
    return { id: `${kind}:${s.orgCode ?? s.section}`, code: s.orgCode ?? null, name: s.orgName || s.section, home: flow[0].href, available: true, flow, reference: s.reference.map(toItem) };
  };
  const out: Scope[] = [];
  for (const [kind, sections] of byKind) {
    let units = sections.map((s) => sectionUnit(s, kind));
    if (kind === "dept") {
      // 설정에 있지만 화면이 아직 없는 부서 — '준비 중'으로 보이고 고를 수 없다 (SCP-02)
      const known = new Set(sections.map((s) => s.section));
      const pending = (cfg.scopes.dept?.units ?? []).filter((u) => !u.available && !known.has(u.section));
      units = [...units, ...pending.map((u): ScopeUnit => ({ id: `dept:${u.code ?? u.section}`, code: u.code, name: u.name, home: null, available: false, flow: [], reference: [] }))];
    }
    if (kind === "branch" && sections.length === 1 && cfg.offices.offices.length > 0) {
      // 영업점 = 같은 화면에 지점만 다르다 — 지점 목록(볼 수 있는 계산 대상 지점)이 단위 (SCP-03)
      const base = sectionUnit(sections[0], kind);
      units = cfg.offices.offices.map((o): ScopeUnit => ({ ...base, id: `branch:${o.code}`, code: o.code, name: o.name, home: withOffice(base.home ?? "", o.code), available: true, office: true }));
    }
    const unitId =
      kind === "branch" && units.some((u) => u.office)
        ? (units.find((u) => u.code === (office ?? cfg.offices.default))?.id ?? units[0]?.id ?? null)
        : (units.find((u) => u.available)?.id ?? null);
    const unit = units.find((u) => u.id === unitId) ?? units[0];
    out.push({
      id: kind,
      kind,
      label: cfg.scopes[kind as "hq" | "dept" | "branch"]?.label ?? unit.name,
      orgName: unit.name,
      home: unit.home ?? sections[0].flow[0].href,
      flow: unit.flow,
      reference: unit.reference,
      units,
      unitId: unit.id,
    });
  }
  for (const s of others) {
    const u = sectionUnit(s, "other");
    out.push({ id: `other:${s.section}`, kind: "other", label: s.section, orgName: s.section, home: u.home ?? "/", flow: u.flow, reference: u.reference, units: [u], unitId: u.id });
  }
  return out.sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind));
}

/** 주소가 이 단위의 화면인가 — 일치 길이(0 = 아님) */
export function unitMatch(u: ScopeUnit, pathname: string): number {
  return Math.max(0, ...[...u.flow, ...u.reference].map((it) => matchLength(it, pathname)));
}

/** 현재 주소의 단위로 영역을 맞춘다 — 사업부서는 주소가 맞는 부서, 영업점은 주소의 지점(이미 반영) */
export function focusUnit(scope: Scope, pathname: string): Scope {
  if (scope.units.some((u) => u.office)) return scope;
  let best: ScopeUnit | null = null;
  let len = 0;
  for (const u of scope.units) {
    const n = unitMatch(u, pathname);
    if (n > len) {
      best = u;
      len = n;
    }
  }
  if (!best || best.id === scope.unitId) return scope;
  return { ...scope, orgName: best.name, home: best.home ?? scope.home, flow: best.flow, reference: best.reference, unitId: best.id };
}

/** 주소에 맞는 영역 — 가장 길게 일치하는 단위의 영역, 없으면 null */
export function scopeOfPath(scopes: Scope[], pathname: string): Scope | null {
  let best: Scope | null = null;
  let len = 0;
  for (const s of scopes) {
    const n = Math.max(0, ...s.units.map((u) => unitMatch(u, pathname)));
    if (n > len) {
      best = s;
      len = n;
    }
  }
  return best;
}

/** 지금 영역이 지점 단위(영업점)이면 고른 지점(?office=)을 그 영역 화면 링크에 잇는다 (B.47 · SCP-03) */
export function officeHrefOf(model: { current: Scope | null }): (item: NavItem) => string {
  const scope = model.current;
  const unit = scope?.units.find((u) => u.id === scope.unitId);
  const office = unit?.office ? unit.code : null;
  const own = new Set([...(scope?.flow ?? []), ...(scope?.reference ?? [])].map((i) => i.href));
  return (item: NavItem) => (office && own.has(item.href) ? withOffice(item.href, office) : item.href);
}
