import { LinkButton } from "@/components/ui/primitives";

export interface BranchReason {
  office: string;
  verdict: string;
  /** 관리자에게만 — 단계별 점검(조직 · 필요한 자료 · 계산 대상 · 실행 · 산출물) */
  steps?: { key: string; ok: boolean; detail: string }[] | null;
}

/** 사용자 영업점의 분석 산출물이 없을 때 (다른 영업점 산출물은 보여주지 않는다 — Q44) — 서버가 짚은 이유를 함께 보인다 */
export function BranchUnavailable({ officeName, reason }: { officeName?: string | null; reason?: BranchReason | null }) {
  return (
    <div className="shell">
      <section className="soft flex flex-col items-center gap-2 px-xl py-section text-center">
        <p className="text-[15px] font-bold text-charcoal">{officeName ? `${officeName}의 ` : ""}업적평가 분석은 아직 준비 중입니다</p>
        {reason?.verdict ? (
          <p className="max-w-[640px] text-[13px] font-bold leading-relaxed text-attention" role="status" data-branch-reason>
            {reason.verdict}
          </p>
        ) : (
          <p className="max-w-[560px] text-[13px] leading-relaxed text-steel">
            영업점 분석은 영업점 데이터(기업 · 소매 익스포저, 업적평가 득점)가 올라온 영업점부터 제공됩니다. 그동안 본부에서 전파된 목표와 가이드를 확인할 수 있습니다.
          </p>
        )}
        {reason?.steps?.length ? (
          <ul className="mt-1 max-w-[720px] text-left text-[12px] leading-relaxed" aria-label="지점 계산 점검">
            {reason.steps.map((s) => (
              <li key={s.key} className={s.ok ? "text-steel" : "font-bold text-critical"}>
                {s.ok ? "✓" : "✕"} {s.detail}
              </li>
            ))}
          </ul>
        ) : null}
        <div className="mt-2">
          <LinkButton href="/branch/targets">본부 전파 목표·가이드 보기</LinkButton>
        </div>
      </section>
    </div>
  );
}
