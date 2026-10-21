/**
 * 업무 소속 — 가입 승인 때 관리자가 정하는 '화면이 붙는 조직 단위' (/admin/users/affiliations · /admin/users/{사번}/affiliation).
 * 영역: 종합기획부(hq) · 사업부서(dept) · 영업본부(region) · 영업점(branch). 이름은 서버 설정(ui.scopes)에서 온다.
 */
export type AffGroupKey = "hq" | "dept" | "region" | "branch";
export type AffPickGroup = AffGroupKey | "custom";

export interface AffOption {
  code: string;
  name: string;
  unitType: string | null;
  unitLabel: string;
  active: boolean;
  /** 최상위 → 바로 위 조직 이름 */
  path: string[];
}

export interface AffGroup {
  key: AffGroupKey;
  label: string;
  options: AffOption[];
  /** 목록 밖도 검색해서 고를 수 있는 유형(영업점) */
  search: { types: string[] } | null;
}

export interface AffClass {
  group: AffGroupKey;
  label: string;
  code: string;
  /** 추천 단위의 표시 정보(추천에만) */
  org?: AffOption | null;
}

export interface AffPreview {
  org: AffOption;
  affiliation: AffClass | null;
  home: { path: string; label: string } | null;
  screens: { code: string; label: string; section: string }[];
}

export interface AffInfo {
  empNo: string;
  current: AffOption | null;
  hrOffice: AffOption | null;
  assigned: { code: string; by: string; at: string; from?: string } | null;
  suggested: AffClass | null;
  preview: AffPreview | null;
}

export interface AffPick {
  group: AffPickGroup;
  code: string;
}

/** 처음 고른 값 — 신청 소속 경로에서 찾은 단위(추천), 없으면 신청 소속 그대로(직접 선택) */
export function defaultPick(info: Pick<AffInfo, "suggested" | "current"> | null | undefined): AffPick | null {
  if (!info) return null;
  if (info.suggested) return { group: info.suggested.group, code: info.suggested.code };
  return { group: "custom", code: info.current?.code ?? "" };
}

/** 영역을 바꾸면 — 지금 단위가 그 영역 목록에 있으면 그대로, 아니면 목록 첫 단위(없으면 비움) */
export function switchGroup(groups: AffGroup[], cur: AffPick | null, key: AffPickGroup): AffPick {
  if (key === "custom") return { group: "custom", code: cur?.code ?? "" };
  const g = groups.find((x) => x.key === key);
  const opts = g?.options ?? [];
  if (cur && opts.some((o) => o.code === cur.code)) return { group: key, code: cur.code };
  return { group: key, code: opts.length === 1 || !g?.search ? (opts[0]?.code ?? "") : "" };
}

/** 조직 경로 한 줄 — '여신본부 > 기업여신부 > 기업금융팀' */
export function orgLine(o: Pick<AffOption, "name" | "path"> | null | undefined): string {
  return o ? [...o.path, o.name].join(" > ") : "-";
}

/** 볼 수 있는 화면 한 줄 — 앞의 max 개 + '외 n개' */
export function screensLine(screens: { label: string }[], max = 6): string {
  if (!screens.length) return "";
  const head = screens.slice(0, max).map((s) => s.label).join(" · ");
  return screens.length > max ? `${head} 외 ${screens.length - max}개` : head;
}
