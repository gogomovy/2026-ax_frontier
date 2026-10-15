"use client";

import { Select, useApiData } from "@/components/admin/kit";
import { Badge } from "@/components/ui/primitives";

/** 자료 소유 조직 — 관리자가 자료를 올릴 때 어느 팀 · 영업점 자료인지 고른다(빈 값 = 전행 공통). 업무 사용자는 소속 팀으로 올라간다 (§33 OWN) */
export interface OwnerOrg {
  code: string;
  name: string;
  unitType?: string | null;
}

interface OrgRow {
  code: string;
  name: string;
  level: number;
  unitType?: string | null;
  unitLabel?: string | null;
  active: boolean;
}

/** 팀 · 부서 · 영업점만 고를 수 있게(본부 · 국 같은 상위 단위도 고를 수 있다 — 조직 트리 순) */
export function OwnerOrgSelect({ value, onChange, label = "자료를 둘 팀 · 영업점" }: { value: string; onChange: (v: string) => void; label?: string }) {
  const orgs = useApiData<{ orgs: OrgRow[] }>("/admin/orgs");
  const rows = (orgs.data?.orgs ?? []).filter((o) => o.active);
  const options = [
    { value: "", label: "전행 공통 (소유 팀 없음)" },
    ...rows.map((o) => ({ value: o.code, label: `${"　".repeat(Math.max(0, (o.level ?? 1) - 1))}${o.name}${o.unitLabel ? ` · ${o.unitLabel}` : ""} (${o.code})` })),
  ];
  return <Select label={label} value={value} onChange={onChange} options={options} ariaLabel={label} />;
}

/** 목록의 소유 조직 표시 */
export function OwnerBadge({ owner }: { owner?: OwnerOrg | null }) {
  if (!owner) return <span className="text-[11px] text-stone">전행 공통</span>;
  return (
    <Badge tone={owner.unitType === "BRANCH" ? "info" : "neutral"}>
      {owner.name}
    </Badge>
  );
}
