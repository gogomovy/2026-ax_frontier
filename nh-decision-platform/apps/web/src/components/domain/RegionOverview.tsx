"use client";

import Link from "next/link";
import clsx from "clsx";
import { CARD, CardHead } from "@/components/domain/BranchOverview";
import { Fig } from "@/components/domain/overviewKit";
import { IconChevron, RowEmpty } from "@/components/ui/primitives";
import { withOffice } from "@/lib/branchOffice";
import { derivedFigure } from "@/lib/derived";
import { NO_VALUE } from "@/lib/period";
import { barWidths, fmt1, fmtPts, groupOf, opportunityNote, pendingNote, ratePct, regionMax, scoreGroups, signed1, upliftNote } from "@/lib/regionView";
import type { Figure, RegionKpi, RegionKpiBranch, RegionKpiGroup } from "@/lib/types";

/** 득점률 축 눈금(%) — 그리기 눈금이다(판정 경계 아님) */
const AXIS_TICKS = [0, 25, 50, 75, 100];
/** 총득점 막대 옆 숫자 자리(px) — 만점 막대 끝에 '593.7 +26.7' 이 들어갈 폭 (시안 387:23) */
const TOTAL_LABEL_ROOM = 84;
/** 대기 지점 안내 — 영업점 업적평가 자료(사무소 마스터 · 득점 현황) 이름 안내 */
const PENDING_HINT = "사무소 마스터 · 득점 현황이 올라오면 계산돼요";

/** 범례 한 칸 — 8px 네모 + 11px 글자 */
function Legend({ items }: { items: { tone: string; label: string }[] }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-3.5 gap-y-1">
      {items.map((it) => (
        <li key={it.label} className="inline-flex items-center gap-1 text-[11px] leading-none text-steel">
          <span aria-hidden="true" className={clsx("h-2 w-2 rounded-[2px]", it.tone)} />
          {it.label}
        </li>
      ))}
    </ul>
  );
}

/** 요약 띠 한 칸 — 라벨 12 · 큰 숫자 30 + 단위 14 · 보조 11 (시안 386:52) */
function BandCell({ label, first, children, foot }: { label: string; first?: boolean; children: React.ReactNode; foot: React.ReactNode }) {
  return (
    <div className={clsx("relative min-w-0 pb-3 pt-[19px]", first ? "pl-[23px] pr-6" : "px-6")}>
      {first ? null : <span aria-hidden="true" className="absolute bottom-[19px] left-0 top-[19px] hidden w-px bg-track lg:block" />}
      <dt className="text-[12px] font-medium leading-[1.4] text-steel">{label}</dt>
      <dd className="mt-[5px] flex h-[35px] items-center">{children}</dd>
      <dd className="mt-[13px] truncate tnum text-[11px] leading-[1.4] text-steel">{foot}</dd>
    </div>
  );
}

/** 지역 요약 수치 — 큰 숫자 롤링 · 계산 추적 (지점 값이 입력) */
function summaryFigures(data: RegionKpi) {
  const done = data.branches.filter((b) => b.available);
  const asOf = done.find((b) => b.asOf)?.asOf ?? "";
  const s = data.summary;
  const inputs = (pick: (b: RegionKpiBranch) => number | null | undefined, unit: string) =>
    done.map((b) => ({ key: b.code, label: b.name, value: String(pick(b) ?? ""), unit, source: "영업점 업적평가 산출물" }));
  const fig = (id: string, label: string, value: number | null | undefined, decimals: number, expression: string, ins: ReturnType<typeof inputs>): Figure => ({
    ...derivedFigure({ id: `region_${id}`, label, value: value ?? null, unit: "NONE", decimals, expression, inputs: ins, asOf }),
    undefinedLabel: NO_VALUE,
  });
  return {
    computed: fig("computed", "계산 완료 영업점", s.computed, 0, "업적평가가 계산된 영업점 수", inputs((b) => b.total, "점")),
    avg: fig("avg_total", "평균 득점", s.avgTotal, 1, "계산 완료 영업점 총득점 평균", inputs((b) => b.total, "점")),
    after: fig("avg_after", "AI 가이드 반영 시 평균", s.avgTotalAfter, 1, "계산 완료 영업점 가이드 반영 시 총득점 평균", inputs((b) => b.totalAfter, "점")),
    chances: fig("opportunities", "득점 향상 기회", s.opportunities ?? 0, 0, "계산 완료 영업점 신설 · 변경 평가기준 알림 수 합", inputs((b) => b.alertCount, "건")),
  };
}

/** ① 지역 요약 띠 — 계산 완료 · 평균 득점 · AI 가이드 반영 시 평균 · 득점 향상 기회 */
function SummaryBand({ data }: { data: RegionKpi }) {
  const s = data.summary;
  const f = summaryFigures(data);
  const max = regionMax(data.branches);
  return (
    <section aria-label="지역 영업점 업적평가 요약" className={clsx(CARD, "mt-[15px]")}>
      <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <BandCell first label="계산 완료 영업점" foot={pendingNote(data.branches) ?? "모든 영업점 계산 완료"}>
          <span className="flex min-w-[130px] items-baseline gap-1">
            <Fig figure={f.computed} size={30} unitLabel="" />
            <span className="tnum text-[14px] font-bold text-steel">/ {fmtPts(s.branches)}개</span>
          </span>
          {s.branches > 0 ? (
            <span aria-hidden="true" className="flex flex-wrap items-center gap-1">
              {Array.from({ length: s.branches }, (_, i) => (
                <span key={i} className={clsx("h-[5px] w-[18px] rounded-pill", i < s.computed ? "bg-primary" : "bg-track")} />
              ))}
            </span>
          ) : null}
        </BandCell>
        <BandCell label="평균 득점" foot="계산 완료 영업점 기준">
          <span className="flex items-baseline gap-1">
            <Fig figure={f.avg} size={30} unitLabel="" />
            {s.avgTotal != null ? <span className="tnum text-[14px] font-bold text-steel">{max != null ? `/ ${fmtPts(max)}점` : "점"}</span> : null}
          </span>
        </BandCell>
        <BandCell label="AI 가이드 반영 시 평균" foot={upliftNote(s) ?? NO_VALUE}>
          <span className="flex items-baseline gap-1">
            <Fig figure={f.after} size={30} unitLabel="" valueClass="text-primary-deep" />
            {s.avgTotalAfter != null ? <span className="text-[14px] font-bold text-primary-deep">점</span> : null}
          </span>
        </BandCell>
        <BandCell label="득점 향상 기회" foot={opportunityNote(s)}>
          <span className="flex items-baseline gap-1">
            <Fig figure={f.chances} size={30} unitLabel="" />
            <span className="text-[14px] font-bold text-steel">건</span>
          </span>
        </BandCell>
      </dl>
    </section>
  );
}

/** 순위 배지 — 1위만 보라 옅은 바탕 */
function RankBadge({ rank }: { rank?: number }) {
  if (!rank) return <span className="pl-[7px] text-[11px] text-stone">{NO_VALUE}</span>;
  return (
    <span className={clsx("tnum inline-flex h-5 w-5 items-center justify-center rounded-circle text-[11px] font-bold", rank === 1 ? "bg-info-soft text-primary-deep" : "bg-surface-soft text-steel")}>
      {rank}
      <span className="sr-only">위</span>
    </span>
  );
}

/** 총득점 칸 — 현재(연보라) + AI 가이드 반영 시 추가(보라) 두 겹 막대, 막대 끝에 숫자. 0 · 값 없음이면 막대 없이 숫자 하나 */
function TotalCell({ b, i }: { b: RegionKpiBranch; i: number }) {
  const { now, extra } = barWidths(b);
  const filled = now + extra;
  return (
    <div className="flex items-center">
      {filled > 0 ? (
        <span
          aria-hidden="true"
          className="flex h-2 shrink-0 origin-left overflow-hidden rounded-r-[4px] motion-safe:animate-grow-x"
          style={{ width: `calc((100% - ${TOTAL_LABEL_ROOM}px) * ${filled / 100})`, ["--i" as string]: i }}
        >
          <span className="h-full bg-info-line-soft" style={{ flexGrow: now, flexBasis: 0 }} />
          {extra > 0 ? <span className="h-full bg-primary" style={{ flexGrow: extra, flexBasis: 0 }} /> : null}
        </span>
      ) : null}
      <span className={clsx("flex shrink-0 items-baseline gap-1 whitespace-nowrap", filled > 0 && "pl-2")}>
        <b className={clsx("tnum text-[13px] font-bold leading-[1.4]", b.total == null ? "text-stone" : "text-ink-deep")}>{b.total === 0 ? "0" : fmt1(b.total)}</b>
        {typeof b.uplift === "number" && b.uplift !== 0 ? <span className="tnum text-[11px] font-medium leading-[1.4] text-primary-deep">{signed1(b.uplift)}</span> : null}
      </span>
    </div>
  );
}

/** ② 영업점별 업적평가 — 총득점 순 표 (계산된 지점 = 순위 순, 대기 지점 = 조직표 순) */
function BranchTable({ data, groups }: { data: RegionKpi; groups: RegionKpiGroup[] }) {
  const max = regionMax(data.branches);
  const name = data.region?.name ?? "영업본부";
  return (
    <section aria-labelledby="rg-branches" className={clsx(CARD, "mt-4 px-[15px] pb-[17px] pt-[19px]")}>
      <div className="px-2">
        <CardHead
          id="rg-branches"
          title="영업점별 업적평가"
          hint={`총득점 순${data.periodLabel ? ` · ${data.periodLabel}` : ""}`}
          right={
            <Legend
              items={[
                { tone: "bg-info-line-soft", label: "현재 득점" },
                { tone: "bg-primary", label: "AI 가이드 반영 시 추가 득점" },
              ]}
            />
          }
        />
      </div>
      {data.branches.length === 0 ? (
        <div className="mt-4">
          <RowEmpty title="이 지역본부 아래 영업점이 없습니다" description="관리자 [조직]에서 영업점의 상위 조직을 지역본부로 두면 여기에 보입니다." />
        </div>
      ) : (
        <>
          {/* relative — 표 안 sr-only(absolute) 글자가 스크롤 상자 밖으로 문서 폭을 늘리지 않게 */}
          <div className="relative mt-4 overflow-x-auto">
            <table className="w-full min-w-[960px] table-fixed border-separate border-spacing-0 text-left">
              <caption className="sr-only">{name} 영업점별 업적평가 — 총득점 순</caption>
              <colgroup>
                <col className="w-[59px]" />
                <col className="w-[160px]" />
                <col />
                {groups.map((g) => (
                  <col key={g.code} className="w-[110px]" />
                ))}
                <col className="w-[150px]" />
                <col className="w-[30px]" />
              </colgroup>
              <thead>
                <tr className="text-[11px] font-bold leading-[1.4] text-steel">
                  <th scope="col" className="h-7 rounded-l-[7px] bg-surface-soft pl-4 font-bold">
                    순위
                  </th>
                  <th scope="col" className="bg-surface-soft font-bold">
                    영업점
                  </th>
                  <th scope="col" className="bg-surface-soft font-bold">
                    {max != null ? `총득점 · ${fmtPts(max)}점 만점` : "총득점"}
                  </th>
                  {groups.map((g) => (
                    <th key={g.code} scope="col" className="bg-surface-soft font-bold">
                      {g.label}
                      {g.max != null ? ` · ${fmtPts(g.max)}` : ""}
                    </th>
                  ))}
                  <th scope="col" className="bg-surface-soft font-bold">
                    득점 향상 기회
                  </th>
                  <th scope="col" className="rounded-r-[7px] bg-surface-soft">
                    <span className="sr-only">현황 보기</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.branches.map((b, i) => (b.available ? <BranchRow key={b.code} b={b} groups={groups} i={i} /> : <PendingRow key={b.code} b={b} groups={groups} />))}
              </tbody>
            </table>
          </div>
          <p className="mt-2.5 px-2 text-[11px] leading-[1.4] text-steel">영업점을 누르면 그 영업점의 현황 화면으로 이동해요</p>
        </>
      )}
    </section>
  );
}

const ROW_TD = "border-b border-track align-middle";

function BranchRow({ b, groups, i }: { b: RegionKpiBranch; groups: RegionKpiGroup[]; i: number }) {
  const href = withOffice("/branch", b.code);
  const types = (b.changeTypes ?? []).filter(Boolean).join(" · ");
  return (
    <tr className="h-[50px]" data-region-branch={b.code}>
      <td className={clsx(ROW_TD, "pl-4")}>
        <RankBadge rank={b.rank} />
      </td>
      <td className={ROW_TD}>
        <Link href={href} className="block truncate rounded-sm text-[14px] font-bold leading-[1.4] text-ink-deep hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
          {b.name}
        </Link>
      </td>
      <td className={clsx(ROW_TD, "pr-4")}>
        <TotalCell b={b} i={i} />
      </td>
      {groups.map((g) => {
        const x = groupOf(b, g.code);
        return (
          <td key={g.code} className={clsx(ROW_TD, "tnum text-[12px] leading-[1.4]", x?.score == null ? "text-stone" : "text-ink-deep")}>
            {x?.score === 0 ? "0" : fmt1(x?.score)}
          </td>
        );
      })}
      <td className={clsx(ROW_TD, "whitespace-nowrap leading-[1.4]")}>
        {b.alertCount > 0 ? (
          <>
            <span className="tnum text-[12px] font-medium text-ink-deep">{fmtPts(b.alertCount)}건</span>
            {types ? <span className="ml-1 text-[11px] text-steel">{types} 평가항목</span> : null}
          </>
        ) : (
          <span className="text-[12px] text-stone">없음</span>
        )}
      </td>
      <td className={clsx(ROW_TD, "pr-2 text-right")}>
        <Link href={href} aria-label={`${b.name} 현황 보기`} className="inline-flex h-6 w-6 items-center justify-center rounded-md text-icon hover:bg-surface-soft hover:text-ink-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
          <IconChevron className="h-2.5 w-2.5" />
        </Link>
      </td>
    </tr>
  );
}

function PendingRow({ b, groups }: { b: RegionKpiBranch; groups: RegionKpiGroup[] }) {
  return (
    <tr className="h-10" data-region-branch={b.code}>
      <td className={clsx(ROW_TD, "pl-4")}>
        <RankBadge />
      </td>
      <td className={clsx(ROW_TD, "truncate text-[13px] font-medium leading-[1.4] text-steel")}>{b.name}</td>
      <td className={clsx(ROW_TD, "whitespace-nowrap")}>
        <span className="inline-flex h-[15px] items-center rounded-pill bg-track px-1.5 text-[10px] font-bold leading-none text-slate">자료 대기</span>
        <span className="ml-2 text-[11px] leading-[1.4] text-stone">{PENDING_HINT}</span>
      </td>
      {groups.map((g) => (
        <td key={g.code} className={clsx(ROW_TD, "text-[12px] text-stone")}>
          {NO_VALUE}
        </td>
      ))}
      <td className={clsx(ROW_TD, "text-[12px] text-stone")}>{NO_VALUE}</td>
      <td className={ROW_TD} />
    </tr>
  );
}

/** 그룹별 득점률 한 줄 — 지점명 · 막대 · '68.5%' + '137.0점'. 0 · 값 없음이면 막대 없이 숫자 하나 */
function rateLine({ name, g, lowest, i }: { name: string; g: RegionKpiGroup | undefined; lowest: boolean; i: number }) {
  const width = ratePct(g?.score, g?.max);
  const rate = g?.rate ?? (g?.score != null && g?.max ? (g.score / g.max) * 100 : null);
  const zero = g?.score === 0;
  return { name, bar: width, rate, score: g?.score ?? null, zero, lowest, i };
}

/** ③ 평가 그룹별 득점률 — 그룹마다 계산된 지점 막대(0–100% 축) + 지역 평균 */
function GroupRates({ data, groups }: { data: RegionKpi; groups: RegionKpiGroup[] }) {
  const done = data.branches.filter((b) => b.available);
  if (done.length === 0 || groups.length === 0) return null;
  return (
    <section aria-labelledby="rg-groups" className={clsx(CARD, "mt-4 px-6 pb-5 pt-[19px]")}>
      <CardHead
        id="rg-groups"
        title="평가 그룹별 득점률"
        hint="배점 대비 득점 · 영업점별"
        right={
          <Legend
            items={[
              { tone: "bg-primary", label: "지역 평균이 가장 낮은 그룹" },
              { tone: "bg-info-line-soft", label: "그 외 그룹" },
            ]}
          />
        }
      />
      <div className="relative overflow-x-auto">
        <div className="min-w-[760px]">
          <p className="mt-1.5 text-right text-[11px] font-medium leading-[1.4] text-steel">지역 평균</p>
          <div className="relative mt-[7px] grid grid-cols-[246px_minmax(0,1fr)_183px]">
            {/* 축 격자 — 0% 선만 진하게 */}
            <div aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-[246px] right-[183px]">
              {AXIS_TICKS.map((t) => (
                <span key={t} className={clsx("absolute inset-y-0 w-px", t === 0 ? "bg-hairline" : "bg-track")} style={{ left: `${t}%` }} />
              ))}
            </div>
            {groups.map((g, gi) => {
              const lines = done.map((b, i) => rateLine({ name: b.name, g: groupOf(b, g.code), lowest: !!g.lowest, i: gi * done.length + i }));
              const last = gi === groups.length - 1;
              return (
                <div key={g.code} role="group" aria-label={`${g.label} 득점률`} className="contents">
                  <div className={clsx("mr-3 grid grid-cols-[136px_minmax(0,1fr)] items-center py-2.5", !last && "border-b border-track")}>
                    <div>
                      <p className="text-[13px] font-bold leading-[1.4] text-ink-deep">{g.label}</p>
                      {g.max != null ? <p className="tnum mt-0.5 text-[10px] leading-[1.4] text-stone">만점 {fmtPts(g.max)}점</p> : null}
                    </div>
                    <ul className="flex flex-col">
                      {lines.map((l) => (
                        <li key={l.name} className="flex h-[22px] items-center truncate text-[11px] leading-[1.4] text-steel">
                          {l.name}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <ul className="relative flex flex-col justify-center py-2.5">
                    {lines.map((l) => (
                      <li key={l.name} className="flex h-[22px] items-center">
                        {l.bar > 0 ? (
                          <span
                            aria-hidden="true"
                            className={clsx("h-2 shrink-0 origin-left rounded-r-[4px] motion-safe:animate-grow-x", l.lowest ? "bg-primary" : "bg-info-line-soft")}
                            style={{ width: `${l.bar}%`, ["--i" as string]: l.i }}
                          />
                        ) : null}
                        <span className={clsx("flex shrink-0 items-baseline gap-1 whitespace-nowrap", l.bar > 0 && "pl-[7px]")}>
                          {l.zero ? (
                            <b className="tnum text-[11px] font-bold text-ink-deep">0</b>
                          ) : l.rate == null ? (
                            <span className="text-[11px] text-stone">{NO_VALUE}</span>
                          ) : (
                            <>
                              <b className="tnum text-[11px] font-bold text-ink-deep">{fmt1(l.rate)}%</b>
                              <span className="tnum text-[10px] text-steel">{fmt1(l.score)}점</span>
                            </>
                          )}
                          <span className="sr-only"> — {l.name}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  <div className="flex items-center justify-end">
                    <p className={clsx("tnum text-[14px] font-bold leading-[1.4]", g.avgRate == null ? "text-stone" : g.lowest ? "text-primary-deep" : "text-ink-deep")}>
                      <span className="sr-only">{g.label} 지역 평균 </span>
                      {g.avgRate == null ? NO_VALUE : g.avgRate === 0 ? "0" : `${fmt1(g.avgRate)}%`}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
          {/* 축 눈금 글자 — 0% 는 선 오른쪽, 나머지는 선 가운데 */}
          <div aria-hidden="true" className="relative ml-[246px] mr-[183px] mt-1.5 h-[14px]">
            {AXIS_TICKS.map((t) => (
              <span key={t} className={clsx("tnum absolute top-0 whitespace-nowrap text-[10px] leading-[1.4] text-stone", t > 0 && "-translate-x-1/2")} style={{ left: `${t}%` }}>
                {t}%
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/**
 * 영업본부 통합 업적평가 본문 — Figma '영업본부 · 영업점 업적평가 통합'(386:2).
 * 요약 띠 · 영업점별 업적평가 표 · 평가 그룹별 득점률. 수치는 모두 /screens/region/kpi(영업점 흐름 산출물) 값이다.
 * 시안의 'Agent 의견' 상자는 지역 수준 AI 서술 산출물이 없어 그리지 않는다 (사용자 원칙: AI 제안이 없으면 그 영역은 보이지 않는다).
 */
export function RegionOverview({ data }: { data: RegionKpi }) {
  const groups = scoreGroups(data);
  return (
    <>
      <SummaryBand data={data} />
      <BranchTable data={data} groups={groups} />
      <GroupRates data={data} groups={groups} />
    </>
  );
}
