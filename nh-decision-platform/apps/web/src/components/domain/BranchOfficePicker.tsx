import { Button } from "@/components/ui/primitives";
import type { BranchOfficeList } from "@/lib/types";

/**
 * 지점 선택 (B.47 · 다지점 · BRM-05) — 볼 수 있는 계산 대상 지점이 둘 이상일 때만(지역본부 · 관리자).
 * 영업점 직원은 자기 지점 하나라 보이지 않는다. 스크립트 없이 동작하는 GET 양식(주소 `?office=`).
 */
export function BranchOfficePicker({ list, current, action }: { list: BranchOfficeList; current: string | null; action: string }) {
  if (list.offices.length < 2) return null;
  return (
    <form method="get" action={action} className="flex flex-nowrap items-center gap-2" data-office-picker>
      <label htmlFor="branch_office" className="shrink-0 whitespace-nowrap text-[12px] font-bold text-steel">
        지점
      </label>
      <select id="branch_office" name="office" defaultValue={current ?? list.default ?? ""} className="input !h-8 w-[180px] py-1 text-[13px]">
        {list.offices.map((o) => (
          <option key={o.code} value={o.code}>
            {o.name}
            {o.available ? "" : " (준비 중)"}
          </option>
        ))}
      </select>
      <Button type="submit" size="sm" variant="quiet">
        보기
      </Button>
    </form>
  );
}
