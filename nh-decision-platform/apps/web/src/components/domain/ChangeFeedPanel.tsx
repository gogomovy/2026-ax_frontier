import { Badge, RowEmpty, SectionHead } from "@/components/ui/primitives";
import { formatDateTime, formatFigure, formatSigned } from "@/lib/format";
import type { ChangeFeed, ChangeItem, Figure } from "@/lib/types";

const fig = (i: ChangeItem, value: number, unit: Figure["unit"] = i.unit): Figure => ({ id: i.code, label: i.label, value, unit, decimals: i.decimals ?? undefined, dataOrigin: "simulated" });

/**
 * 최근 감지된 변화 (B.30) — 변화 감지 에이전트가 직전 확정값 대비 유의 기준(규칙 CHANGE_SIGNIFICANCE)을 넘은 변화만 기록한다.
 * 수치는 커널 계산 결과이며, 데이터 변경은 새로 확정된 파일과 행 수 증감을 보여준다.
 */
export function ChangeFeedPanel({ feed, title = "최근 감지된 변화" }: { feed: ChangeFeed; title?: string }) {
  return (
    <section aria-label={title}>
      <SectionHead title={title} hint={`변화 감지 에이전트 · 직전 확정값 대비${feed.updatedAt ? ` · ${formatDateTime(feed.updatedAt)}` : ""}`} />
      {feed.items.length === 0 ? (
        <RowEmpty title="유의 기준을 넘은 변화가 없습니다" description="데이터 · 규칙 · 문서가 바뀌어 수치가 유의하게 움직이면 여기에 기록됩니다." />
      ) : (
        <ul className="divide-y divide-hairline-soft overflow-hidden rounded-2xl border border-hairline-soft" data-change-feed>
          {feed.items.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-x-md gap-y-1 px-lg py-2.5 text-[13px]">
              <Badge tone={i.level === "major" ? "attention" : "neutral"}>{i.level === "major" ? "주요" : "일반"}</Badge>
              <Badge tone={i.kind === "data" ? "dark" : "info"}>{i.kind === "data" ? "데이터" : "지표"}</Badge>
              <span className="min-w-0 flex-1 font-bold text-ink-deep">{i.label}</span>
              <span className="tnum text-charcoal">
                {i.kind === "data" ? `${formatFigure(fig(i, i.before, "CNT"))} → ${formatFigure(fig(i, i.after, "CNT"))} 행` : `${formatFigure(fig(i, i.before))} → ${formatFigure(fig(i, i.after))}`}
                <span className={i.direction === "down" ? "ml-1.5 text-critical" : "ml-1.5 text-primary"}>
                  ({formatSigned(fig(i, i.delta, i.kind === "data" ? "CNT" : i.unit))}
                  {i.deltaPct !== null ? ` · ${i.deltaPct > 0 ? "+" : ""}${i.deltaPct.toFixed(1)}%` : ""})
                </span>
              </span>
              <span className="w-full text-[11.5px] text-stone md:w-auto">
                {i.workflowName}
                {i.files?.length ? ` · ${i.files.join(", ")}` : ""} · {formatDateTime(i.at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
