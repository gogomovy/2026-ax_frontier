import clsx from "clsx";

const STROKE = { primary: "var(--color-primary)", warning: "var(--color-attention)", danger: "var(--color-critical)" } as const;

/**
 * 반원 게이지 — 한도 소진율 · 배분 소진율 · 목표 진행률.
 * 색은 의미 있는 값에만: 보라 = 정상 진행, 주황 = 한도 근접, 빨강 = 초과.
 * 가운데 큰 숫자 아래에 무엇의 비율인지 한 줄로 쓴다.
 */
export function SemiGauge({
  percent,
  label,
  tone = "primary",
  className,
}: {
  /** 0~100 (100 을 넘으면 가득 찬 것으로 그린다) */
  percent: number;
  label: string;
  tone?: keyof typeof STROKE;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, percent));
  const text = `${percent.toFixed(1)}`;
  return (
    <div className={clsx("relative h-[96px] w-[160px] shrink-0", className)} role="img" aria-label={`${label} ${text}%`}>
      <svg viewBox="0 0 160 96" width="160" height="96" aria-hidden="true">
        <path d="M 14 86 A 66 66 0 0 1 146 86" fill="none" stroke="var(--color-track)" strokeWidth="14" strokeLinecap="round" pathLength={100} />
        {clamped > 0 ? (
          <path
            d="M 14 86 A 66 66 0 0 1 146 86"
            fill="none"
            stroke={STROKE[tone]}
            strokeWidth="14"
            strokeLinecap="round"
            pathLength={100}
            strokeDasharray={`${clamped} 100`}
            className="motion-safe:animate-draw"
          />
        ) : null}
      </svg>
      <div className="absolute inset-x-0 bottom-0 flex flex-col items-center leading-none">
        <span className="tnum text-[22px] font-bold text-ink-deep">
          {text}
          <span className="num-unit">%</span>
        </span>
        <span className="mt-1.5 text-[12px] text-steel">{label}</span>
      </div>
    </div>
  );
}
