import type { ReactNode } from "react";
import { RichText } from "@/components/data/RichText";
import { EvidenceChips } from "@/components/evidence/EvidenceChips";
import { VerificationRow } from "@/components/domain/Verification";
import { IconSparkle } from "@/components/ui/icons";
import type { Evidence, Figure, Verification } from "@/lib/types";

/**
 * AI 해설 블록 — 분석 화면 공통. AI 영역 = primary/100 박스 + ✦ 라벨 + 흰 내부 카드 (가이드 G04).
 * 서술은 보고문서 어투, 수치는 모두 계산 추적 마커로 렌더된다(PRIN-05).
 */
export function AgentNote({
  label = "AI 해설",
  title,
  text,
  figures,
  evidence,
  evidenceTitle,
  verifications,
  footer,
}: {
  label?: string;
  title?: ReactNode;
  text: string;
  figures?: Record<string, Figure>;
  evidence?: Evidence[];
  evidenceTitle?: string;
  verifications?: Verification[];
  footer?: ReactNode;
}) {
  return (
    <section className="rounded-xl bg-info-soft p-3">
      <span className="inline-flex h-7 items-center gap-1.5 rounded-pill bg-canvas px-3 text-[12px] font-bold text-primary">
        <IconSparkle />
        {label}
      </span>
      <div className="mt-3 rounded-lg bg-canvas px-6 py-5">
        {title ? <h3 className="text-[16px] font-bold leading-[1.4] text-ink-deep">{title}</h3> : null}
        <RichText text={text} figures={figures} className="mt-1 text-[14px] leading-[1.7] text-ink-deep" />
        {evidence || verifications || footer ? (
          <div className="mt-4 flex flex-wrap items-center gap-xs">
            {evidence ? <EvidenceChips items={evidence} title={evidenceTitle ?? "근거"} /> : null}
            {verifications ? <VerificationRow items={verifications} /> : null}
            {footer ? <div className="ml-auto">{footer}</div> : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
