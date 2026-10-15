import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, DataTable, ProgressBar, RowEmpty, SectionHead, Td } from "@/components/ui/primitives";
import { getRegionKpi } from "@/lib/data";
import type { RegionKpi, RegionKpiBranch } from "@/lib/types";

// 지역본부 소속 · 고른 지역에 따라 달라지고 영업점 흐름이 갱신하므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";

const fmt = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "–" : v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d }));

function regionParam(sp: Record<string, string | string[] | undefined>): string | null {
  const v = Array.isArray(sp.region) ? sp.region[0] : sp.region;
  return v && /^[A-Za-z0-9_-]{1,20}$/.test(v) ? v : null;
}

/** 지역 선택 — 관리자만(지역본부 직원은 자기 지역 하나). 스크립트 없이 동작하는 GET 양식 */
function RegionPicker({ data }: { data: RegionKpi }) {
  if (data.regions.length < 2) return null;
  return (
    <form method="get" action="/region" className="flex flex-wrap items-center gap-2" data-region-picker>
      <label htmlFor="region_code" className="text-[12px] font-bold text-steel">
        지역본부
      </label>
      <select id="region_code" name="region" defaultValue={data.region?.code ?? ""} className="input max-w-[240px] py-1.5 text-[13px]">
        {data.regions.map((r) => (
          <option key={r.code} value={r.code}>
            {r.name}
          </option>
        ))}
      </select>
      <Button type="submit" size="sm" variant="quiet">
        보기
      </Button>
    </form>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-hairline-soft bg-canvas p-base">
      <p className="text-[12px] font-bold text-steel">{label}</p>
      <p className="tnum mt-1 text-[22px] font-bold text-ink-deep">{value}</p>
      {sub ? <p className="mt-0.5 text-[11.5px] text-stone">{sub}</p> : null}
    </div>
  );
}

function BranchRow({ b, groups }: { b: RegionKpiBranch; groups: string[] }) {
  const href = `/branch?office=${encodeURIComponent(b.code)}`;
  if (!b.available) {
    return (
      <tr data-region-branch={b.code}>
        <Td align="center">–</Td>
        <Td strong>{b.name}</Td>
        <Td className="text-stone" align="left">
          자료 대기 — 이 영업점의 업적평가 자료(사무소 마스터 · 득점 현황)가 올라오면 계산됩니다
        </Td>
        {groups.map((g) => (
          <Td key={g} align="right">
            –
          </Td>
        ))}
        <Td align="right">–</Td>
        <Td>–</Td>
      </tr>
    );
  }
  const byCode = new Map(b.groups.map((g) => [String(g.code), g]));
  return (
    <tr data-region-branch={b.code}>
      <Td align="center" strong>
        {b.rank ?? "–"}
      </Td>
      <Td strong>
        <Link href={href} className="text-primary-text hover:underline">
          {b.name}
        </Link>
      </Td>
      <Td>
        <div className="flex min-w-[160px] flex-col gap-1">
          <span className="tnum text-[13px] font-bold text-ink-deep">
            {fmt(b.total)} / {fmt(b.max)}점 <span className="font-normal text-steel">({fmt(b.rate)}%)</span>
          </span>
          {/* 득점률 막대 — 판정 구간은 화면에 두지 않는다(순위 · 득점 · 만점은 산출물 값 그대로) */}
          {b.rate !== null ? <ProgressBar value={b.rate} /> : null}
        </div>
      </Td>
      {groups.map((g) => {
        const x = byCode.get(g);
        return (
          <Td key={g} align="right">
            {x ? `${fmt(x.score)}${x.max ? ` / ${fmt(x.max)}` : ""}` : "–"}
          </Td>
        );
      })}
      <Td align="right">{b.totalAfter !== null ? `${fmt(b.totalAfter)}${b.uplift ? ` (+${fmt(b.uplift)})` : ""}` : "–"}</Td>
      <Td>
        {b.alertCount ? (
          <span className="flex flex-col gap-0.5">
            <Badge tone="attention">주의 {b.alertCount}</Badge>
            {b.alerts[0]?.title ? <span className="text-[11.5px] text-steel">{b.alerts[0].title}</span> : null}
          </span>
        ) : (
          <span className="text-stone">없음</span>
        )}
      </Td>
    </tr>
  );
}

/** 영업본부 STEP 1 — 지역본부 아래 영업점 업적평가 통합 (§37 RGN). 지점 점수는 영업점 흐름이 계산한 값 그대로 */
export default async function RegionKpiPage(props: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const data = await getRegionKpi(regionParam(await props.searchParams));
  const name = data.region?.name ?? "영업본부";
  const groups = (data.groups ?? []).filter((g) => g.kind !== "adjustment");
  const s = data.summary;
  return (
    <>
      <PageHeader
        eyebrow="1단계 · 영업점 업적평가 통합"
        title={`${name} 영업점 업적평가`}
        description={`${data.periodLabel ? `${data.periodLabel} ` : ""}지역 영업점의 업적평가 득점을 한 화면에서 비교합니다. 점수는 영업점별 분석 에이전트가 계산한 값이고, 순위 · 평균만 이 화면에서 셉니다.`}
        actions={<RegionPicker data={data} />}
      />
      <div className="shell flex flex-col gap-xxl">
        <section className="grid grid-cols-2 gap-sm md:grid-cols-4" data-region-summary>
          <Stat label="영업점" value={`${s.computed} / ${s.branches}`} sub="계산된 영업점 / 지역 영업점" />
          <Stat label="평균 득점" value={fmt(s.avgTotal)} sub={s.avgRate !== null && s.avgRate !== undefined ? `평균 득점률 ${fmt(s.avgRate)}%` : undefined} />
          <Stat label="가점 반영 평균" value={fmt(s.avgTotalAfter)} />
          <Stat label="주의 항목" value={`${s.alerts ?? 0}건`} sub={s.top ? `1위 ${s.top.name}` : undefined} />
        </section>

        <section>
          <SectionHead title="영업점별 업적평가" hint={data.asOfLabel ?? undefined} />
          {data.branches.length === 0 ? (
            <RowEmpty title="이 지역본부 아래 영업점이 없습니다" description="관리자 [조직]에서 영업점의 상위 조직을 지역본부로 두면 여기에 보입니다." />
          ) : (
            <DataTable
              caption={`${name} 영업점 업적평가 비교`}
              columns={[
                { key: "rank", label: "순위", align: "center", width: "56px" },
                { key: "name", label: "영업점" },
                { key: "total", label: "득점 / 만점" },
                ...groups.map((g) => ({ key: `g-${g.code}`, label: g.label, align: "right" as const })),
                { key: "after", label: "가점 반영", align: "right" as const },
                { key: "alerts", label: "주의" },
              ]}
            >
              {data.branches.map((b) => (
                <BranchRow key={b.code} b={b} groups={groups.map((g) => String(g.code))} />
              ))}
            </DataTable>
          )}
        </section>

        {groups.length ? (
          <section>
            <SectionHead title="평가 그룹별 지역 평균" />
            <DataTable
              columns={[
                { key: "label", label: "평가 그룹" },
                { key: "avg", label: "지역 평균", align: "right" },
                { key: "max", label: "만점", align: "right" },
              ]}
            >
              {groups.map((g) => (
                <tr key={g.code}>
                  <Td strong>{g.label}</Td>
                  <Td align="right">{fmt(g.avg)}</Td>
                  <Td align="right">{fmt(g.max)}</Td>
                </tr>
              ))}
            </DataTable>
          </section>
        ) : null}

        <p className="text-[12px] text-stone">
          영업점 이름을 누르면 그 영업점의 현황 화면으로 이동합니다. 본부에서 이 지역으로 전파된 목표는{" "}
          <Link href="/branch/targets" className="font-bold text-primary-text">
            본부 전파 목표·가이드
          </Link>
          에서 봅니다.
        </p>
      </div>
    </>
  );
}
