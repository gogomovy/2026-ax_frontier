import type { CSSProperties, ReactNode } from "react";
import clsx from "clsx";
/**
 * 화면 로딩 스켈레톤 (가이드 G06) — 각 화면 loading.tsx 가 실제 레이아웃과 같은 자리 · 크기로 회색 블록을 먼저 그린다.
 * 블록은 보조기기에서 숨기고, 화면 전체에 '불러오는 중' 상태 하나만 알린다. 움직임 줄이기 설정이면 깜빡이지 않는다.
 */
/** 회색 블록 하나 (글자 줄 · 큰 숫자 · 막대 · 차트 자리). 파란 안내 영역 위에서는 tone="canvas"(흰 블록) */
export function Bone({ className, style, round = "rounded-md", tone = "track" }: { className?: string; style?: CSSProperties; round?: string; tone?: "track" | "canvas" }) {
  return <div aria-hidden="true" className={clsx(round, tone === "canvas" ? "bg-canvas" : "bg-track", "motion-safe:animate-pulse", className)} style={style} />;
}
/** 화면 전체 감싸개 — 상태 알림 + 화면 읽기용 문구 */
export function SkeletonScreen({ children, label = "불러오는 중" }: { children: ReactNode; label?: string }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}
/** 제목 줄 (22px 제목 · 옆 설명 · 오른쪽 기준월 · 기준 시각 · 내보내기) — 높이 31px */
export function SkelTitleRow({ title = "w-[180px]", meta = true, tools = true }: { title?: string; meta?: boolean; tools?: boolean }) {
  return (
    <div className="flex h-[31px] items-center justify-between gap-x-6" aria-hidden="true">
      <div className="flex items-center gap-x-8">
        <Bone className={clsx("h-[26px]", title)} />
        {meta ? <Bone className="h-3.5 w-[200px]" /> : null}
      </div>
      {tools ? (
        <div className="flex items-center gap-x-6">
          <Bone className="h-4 w-[96px]" />
          <Bone className="h-3.5 w-[230px]" />
          <Bone className="h-4 w-[72px]" />
        </div>
      ) : null}
    </div>
  );
}
/** 화면 내부 탭 줄 (높이 43px · 아래 구분선) */
export function SkelTabs({ widths = ["w-[150px]", "w-[170px]"], className }: { widths?: string[]; className?: string }) {
  return (
    <div className={clsx("flex h-[43px] items-center gap-x-6 border-b border-hairline-soft", className)} aria-hidden="true">
      {widths.map((w, i) => (
        <Bone key={i} className={clsx("h-4", w)} />
      ))}
    </div>
  );
}
/** 머리말 (PageHeader compact 와 같은 여백) — 제목 줄 + 선택 탭 */
export function SkelPageHeader({ tabs, title, meta = false }: { tabs?: string[]; title?: string; meta?: boolean }) {
  return (
    <div className="shell pb-4 pt-5">
      <SkelTitleRow title={title} meta={meta} />
      {tabs ? <SkelTabs widths={tabs} className="mt-4" /> : null}
    </div>
  );
}
/** 흰 카드 (실제 카드와 같은 모서리 · 테두리 · 안쪽 여백). 여백이 다른 카드는 pad 로 통째로 바꾼다 */
export function SkelCard({ className, pad = "px-6 pb-6 pt-5", children }: { className?: string; pad?: string; children?: ReactNode }) {
  return <section className={clsx("min-w-0 rounded-[10px] border border-hairline-soft bg-canvas", pad, className)}>{children}</section>;
}
/** 파란 안내 영역 (AI 의견 · 제안 묶음) */
export function SkelPanel({ className, children }: { className?: string; children?: ReactNode }) {
  return <section className={clsx("min-w-0 rounded-[10px] bg-info-soft", className)}>{children}</section>;
}
/** 카드 제목 줄 (16px 제목 + 보조 설명 · 선택 오른쪽 링크) */
export function SkelCardTitle({ title = "w-[120px]", sub = "w-[200px]", right, height = "h-[22px]", className }: { title?: string; sub?: string | null; right?: string; height?: string; className?: string }) {
  return (
    <div className={clsx("flex items-center justify-between gap-x-4", height, className)} aria-hidden="true">
      <div className="flex items-center gap-x-3">
        <Bone className={clsx("h-[18px]", title)} />
        {sub ? <Bone className={clsx("h-3", sub)} /> : null}
      </div>
      {right ? <Bone className={clsx("h-3.5", right)} /> : null}
    </div>
  );
}
/** 지표 하나 (작은 라벨 · 큰 숫자 · 보조 줄) */
export function SkelStat({ value = "w-[96px]", className }: { value?: string; className?: string }) {
  return (
    <div className={clsx("flex min-w-0 flex-col", className)} aria-hidden="true">
      <Bone className="h-3 w-[72px]" />
      <Bone className={clsx("mt-2.5 h-7", value)} />
      <Bone className="mt-2.5 h-3 w-[120px]" />
    </div>
  );
}
/** 표 · 목록 줄 — 줄마다 위 구분선 */
export function SkelRows({ count, rowClass = "h-16", cols = ["w-[18%]", "w-[26%]", "w-[22%]", "w-[14%]"], className }: { count: number; rowClass?: string; cols?: string[]; className?: string }) {
  return (
    <ul className={clsx("divide-y divide-hairline-soft", className)} aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <li key={i} className={clsx("flex items-center justify-between gap-x-6", rowClass)}>
          {cols.map((w, j) => (
            <Bone key={j} className={clsx("h-3.5", w)} />
          ))}
        </li>
      ))}
    </ul>
  );
}
/** 표 머리 줄 (회색 바탕 36px) */
export function SkelTableHead({ className }: { className?: string }) {
  return <div className={clsx("h-9 rounded-lg bg-surface-soft", className)} aria-hidden="true" />;
}
const BAR_HEIGHTS = [46, 64, 38, 72, 55, 88, 60, 78, 50, 68, 42, 58];
/** 막대 차트 자리 (아래 축선 · 막대 높이는 고정 패턴) */
export function SkelBars({ className, count = 12 }: { className?: string; count?: number }) {
  return (
    <div className={clsx("flex items-end gap-3 border-b border-hairline-soft px-2", className)} aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <Bone key={i} className="flex-1" round="rounded-t-md" style={{ height: `${BAR_HEIGHTS[i % BAR_HEIGHTS.length]}%` }} />
      ))}
    </div>
  );
}
/** 선 · 영역 차트 자리 (가로 눈금선 위 옅은 면) */
export function SkelChart({ className }: { className?: string }) {
  return (
    <div className={clsx("relative flex flex-col justify-between", className)} aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="border-t border-hairline-soft" />
      ))}
      <Bone className="absolute inset-x-0 bottom-0 top-1/3 opacity-60" round="rounded-none" />
    </div>
  );
}
/** 가로 진행 막대 목록 (라벨 · 막대 · 값) */
export function SkelProgressList({ count, className, rowClass = "py-2.5" }: { count: number; className?: string; rowClass?: string }) {
  return (
    <ul className={className} aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <li key={i} className={rowClass}>
          <div className="flex items-center justify-between">
            <Bone className="h-3.5 w-[96px]" />
            <Bone className="h-3.5 w-[56px]" />
          </div>
          <Bone className="mt-2 h-1.5 w-full" round="rounded-pill" />
        </li>
      ))}
    </ul>
  );
}
/** 다음 단계 카드 (높이 80px) */
export function SkelNextStep({ className }: { className?: string }) {
  return (
    <section className={clsx("flex h-20 items-center gap-3 rounded-[10px] border border-hairline-soft bg-canvas pl-5 pr-[18px]", className)} aria-hidden="true">
      <Bone className="h-[30px] w-[30px]" round="rounded-circle" />
      <div className="min-w-0 flex-1">
        <Bone className="h-4 w-[160px]" />
        <Bone className="mt-2 h-3 w-[360px] max-w-full" />
      </div>
      <Bone className="h-10 w-[120px]" />
    </section>
  );
}
/** 최근 감지된 변화 카드 (제목 · 3줄 · 더 보기). dense = 영업점 현황(제목 줄 3px 낮음) */
export function SkelChangeFeed({ className, dense }: { className?: string; dense?: boolean }) {
  return (
    <section className={clsx("rounded-[10px] border border-hairline-soft bg-canvas", className)} aria-hidden="true">
      <div className={clsx("px-6 pb-3", dense ? "pt-[19px]" : "pt-5")}>
        <SkelCardTitle title="w-[110px]" sub="w-[260px]" height={dense ? "h-5" : undefined} />
      </div>
      <SkelRows count={3} rowClass="h-9" cols={["w-[22%]", "w-[18%]", "w-[22%]"]} className="mx-6 border-t border-track" />
      <div className="flex h-10 items-center justify-center border-t border-hairline-soft">
        <Bone className="h-3 w-[90px]" />
      </div>
    </section>
  );
}
/** 2단계 분석 결과 — AI 의견 영역 (태그 · 제목 · 본문 · 지표 칸) */
export function SkelOpinionPanel({ tiles = 4, lines = 2, height }: { tiles?: number; lines?: number; height?: number }) {
  return (
    <SkelPanel className="px-6 pb-6 pt-5">
      <div style={height ? { height: height - 44 } : undefined} className="flex flex-col">
        <div className="flex h-6 items-center justify-between" aria-hidden="true">
          <Bone className="h-[23px] w-[89px]" round="rounded-pill" tone="canvas" />
          <Bone className="h-3.5 w-[180px]" tone="canvas" />
        </div>
        <Bone className="mt-3 h-[22px] w-[360px]" tone="canvas" />
        <div className="mt-2 space-y-2" aria-hidden="true">
          {Array.from({ length: lines }, (_, i) => (
            <Bone key={i} className={clsx("h-3.5", i === lines - 1 ? "w-3/5" : "w-full max-w-[1110px]")} tone="canvas" />
          ))}
        </div>
        <div className={clsx("mt-auto grid grid-cols-1 gap-3 pt-5", tiles === 3 ? "md:grid-cols-3" : "md:grid-cols-2 lg:grid-cols-4")}>
          {Array.from({ length: tiles }, (_, i) => (
            <div key={i} className="h-[94px] rounded-lg bg-canvas px-4 pb-3.5 pt-3">
              <SkelStat />
            </div>
          ))}
        </div>
      </div>
    </SkelPanel>
  );
}
/** 2단계 분석 결과 — 차트 카드 (왼쪽 큰 차트 · 구분선 · 오른쪽 보조 목록). height = 카드 전체 높이 */
export function SkelSplitChartCard({ height, wide = "1.9fr" }: { height: number; wide?: "1fr" | "1.9fr" }) {
  return (
    <SkelCard className="flex flex-col overflow-hidden">
      <div className="flex flex-col" style={{ height: height - 46 }}>
        <SkelCardTitle title="w-[110px]" sub="w-[300px]" height="h-[25px]" />
        <div className={clsx("mt-4 grid min-h-0 flex-1 grid-cols-1 gap-y-8 lg:gap-x-6", wide === "1fr" ? "lg:grid-cols-[minmax(0,1fr)_1px_minmax(0,1fr)]" : "lg:grid-cols-[minmax(0,1.9fr)_1px_minmax(0,1fr)]")}>
          <div className="flex min-w-0 flex-col">
            <div className="flex items-center justify-between" aria-hidden="true">
              <Bone className="h-4 w-[150px]" />
              <Bone className="h-3 w-[110px]" />
            </div>
            <SkelBars className="mt-4 min-h-0 flex-1" />
            <Bone className="mt-4 h-3 w-[420px] max-w-full" />
          </div>
          <div className="hidden bg-hairline-soft lg:block" />
          <div className="flex min-w-0 flex-col">
            <div className="flex items-center justify-between" aria-hidden="true">
              <Bone className="h-4 w-[90px]" />
              <Bone className="h-3 w-[80px]" />
            </div>
            <SkelProgressList count={5} className="mt-3" />
          </div>
        </div>
      </div>
    </SkelCard>
  );
}
/** 2단계 분석 결과 — 특이사항 · 가이드 / 근거 목록 카드. height = 카드 전체 높이, twoCol = 영업점 가이드(2열) */
export function SkelListCard({ height, rows, rowClass = "h-[70px]", right, twoCol }: { height: number; rows: number; rowClass?: string; right?: string; twoCol?: boolean }) {
  return (
    <SkelCard className="overflow-hidden">
      <div style={{ height: height - 46 }}>
        <SkelCardTitle title="w-[120px]" sub="w-[200px]" right={right} height="h-[25px]" />
        {twoCol ? (
          <ul className="mt-4 grid grid-cols-1 gap-x-10 gap-y-5 md:grid-cols-2" aria-hidden="true">
            {Array.from({ length: rows }, (_, i) => (
              <li key={i} className="space-y-2">
                <Bone className="h-4 w-3/5" />
                <Bone className="h-3 w-11/12" />
                <Bone className="h-3 w-2/3" />
              </li>
            ))}
          </ul>
        ) : (
          <SkelRows count={rows} rowClass={rowClass} cols={["w-[44%]", "w-[10%]"]} className="mt-4 border-t border-hairline-soft" />
        )}
      </div>
    </SkelCard>
  );
}
/** 2단계 분석 결과 화면 배치 (ReportShell) — 화면별 실제 카드 높이(1440px 기준) */
const REPORT_LAYOUT = {
  // 신용리스크관리부 — 모형 모니터링 탭: 지표 4칸 · 차트 1.9:1 · 특이사항 4줄 · 근거 6줄
  risk: { tiles: 4, lines: 2, opinion: 269, wide: "1.9fr", charts: [387, 436], guides: 401, guideRows: 4, twoCol: false, details: 355, detailRows: 6 },
  // 영업점 — 우량기업여신 탭: 지표 3칸 · 차트 1:1 · 가이드 2열 · 근거 7줄
  branch: { tiles: 3, lines: 3, opinion: 289, wide: "1fr", charts: [404, 483], guides: 190, guideRows: 2, twoCol: true, details: 399, detailRows: 7 },
} as const;
/** 2단계 분석 결과 화면 (영업점 · 신용리스크관리부 공통 ReportShell 구조) */
export function SkelReportScreen({ space }: { space: keyof typeof REPORT_LAYOUT }) {
  const l = REPORT_LAYOUT[space];
  return (
    <SkeletonScreen>
      <SkelPageHeader title="w-[236px]" tabs={["w-[176px]", "w-[180px]"]} />
      <div className="shell flex flex-col gap-4 pb-6">
        <SkelOpinionPanel tiles={l.tiles} lines={l.lines} height={l.opinion} />
        {l.charts.map((h) => (
          <SkelSplitChartCard key={h} height={h} wide={l.wide} />
        ))}
        <SkelListCard height={l.guides} rows={l.guideRows} twoCol={l.twoCol} />
        <SkelListCard height={l.details} rows={l.detailRows} rowClass="h-[44px]" right="w-[64px]" />
        <SkelNextStep />
      </div>
    </SkeletonScreen>
  );
}
/** 그 밖의 화면 (관리자 · 보조 화면) — 제목 줄 + 카드 3개 */
export function SkelGenericScreen() {
  return (
    <SkeletonScreen>
      <div className="shell flex flex-col gap-4 pb-6 pt-8">
        <Bone className="h-[30px] w-[220px]" />
        <div className="mt-1 grid grid-cols-1 gap-4 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <SkelCard key={i} className={i > 0 ? "hidden lg:block" : undefined}>
              <SkelCardTitle title="w-[110px]" sub={null} />
              <SkelStat className="mt-5" value="w-[140px]" />
              <SkelBars className="mt-6 h-[72px]" count={8} />
            </SkelCard>
          ))}
        </div>
        <SkelCard>
          <SkelCardTitle />
          <SkelRows count={4} rowClass="h-12" className="mt-4 border-t border-hairline-soft" />
        </SkelCard>
      </div>
    </SkeletonScreen>
  );
}
