"use client";

import { OrgPicker } from "@/components/admin/OrgPicker";
import { Badge } from "@/components/ui/primitives";

/** 자료 소유 조직 — 관리자가 자료를 올릴 때 어느 팀 · 영업점 자료인지 고른다(빈 값 = 전행 공통). 업무 사용자는 소속 팀으로 올라간다 (§33 OWN) */
export interface OwnerOrg {
  code: string;
  name: string;
  unitType?: string | null;
}

/** 팀 · 부서 · 영업점(본부 · 국 같은 상위 단위도 고를 수 있다) — 조직이 수천 곳이어도 멈추지 않게 검색해서 고른다. 사용 중인 조직만 */
export function OwnerOrgSelect({ value, onChange, label = "자료를 둘 팀 · 영업점" }: { value: string; onChange: (v: string) => void; label?: string }) {
  return <OrgPicker label={label} value={value} onChange={(code) => onChange(code)} empty="전행 공통 (소유 팀 없음)" />;
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
