import type { ReactNode } from "react";
import { RichText } from "@/components/data/RichText";
import { EvidenceChips } from "@/components/evidence/EvidenceChips";
import { VerificationRow } from "@/components/domain/Verification";
import type { Evidence, Figure, Verification } from "@/lib/types";

/**
 * AI 해설 블록 — 분석 화면 공통.
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
    <section className="rounded-2xl bg-surface-soft px-lg py-lg">
      <p className="text-[11.5px] font-bold text-steel">{label}</p>
      {title ? <h3 className="mt-1.5 text-[16px] font-bold leading-snug text-ink-deep">{title}</h3> : null}
      <RichText
        text={text}
        figures={figures}
        className="mt-2 text-[14px] leading-[1.7] text-charcoal"
      />
      {evidence || verifications || footer ? (
        <div className="mt-base flex flex-wrap items-center gap-xs">
          {evidence ? <EvidenceChips items={evidence} title={evidenceTitle ?? "근거"} /> : null}
          {verifications ? <VerificationRow items={verifications} /> : null}
          {footer ? <div className="ml-auto">{footer}</div> : null}
        </div>
      ) : null}
    </section>
  );
}
