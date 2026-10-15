import { FigureText } from "@/components/data/FigureText";
import { BranchGuides } from "@/components/domain/BranchGuides";
import { ReportRequestForm } from "@/components/domain/ReportRequestForm";
import { PageHeader } from "@/components/layout/PageHeader";
import { BandProgress } from "@/components/ui/BandProgress";
import { RowEmpty, SectionHead } from "@/components/ui/primitives";
import { getBranchTargets } from "@/lib/data";

/** 영업점 참고 — 본부에서 전파된 목표와 사업부서 가이드 (요구사항 BR-01 / BR-02) */
export default async function BranchTargetsPage() {
  const targets = await getBranchTargets();
  const orgs = Array.from(new Set(targets.map((t) => t.orgName)));

  return (
    <>
      <PageHeader
        eyebrow="참고"
        title="본부 전파 목표·가이드"
        description="경영목표에서 내려온 영업점 목표와, 사업부서가 영업점 참고를 허용한 가이드입니다. 각 항목은 출처 목표와 수행방안까지 추적됩니다."
      />

      <div className="shell flex flex-col gap-xxl">
        <section>
          <SectionHead title="전파된 목표" hint={`${targets.length}건${orgs.length ? ` · ${orgs.join(" · ")}` : ""}`} />
          {targets.length === 0 ? (
            <RowEmpty title="전파된 목표가 없습니다" description="경영목표 · 실적 자료가 올라와 목표가 계산되면 영업점 목표가 이곳에 표시됩니다." />
          ) : null}
          <div className="grid grid-cols-1 gap-md lg:grid-cols-3">
            {targets.map((target) => (
              <article key={target.id} className="flex flex-col gap-3 rounded-2xl border border-hairline-soft p-lg">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[12px] font-bold text-steel">{target.periodLabel}</span>
                  <span className="text-[11.5px] text-stone">{target.metricLabel}</span>
                </div>
                <h3 className="text-[15px] font-bold leading-snug text-ink-deep">{target.title}</h3>

                <div className="flex items-end justify-between gap-2">
                  <div>
                    <p className="text-[11.5px] text-steel">목표</p>
                    <p className="mt-0.5 text-[20px] font-bold leading-none text-ink-deep">
                      <FigureText figure={target.target} strong />
                    </p>
                  </div>
                  {target.actual ? (
                    <div className="text-right">
                      <p className="text-[11.5px] text-steel">실적</p>
                      <p className="mt-0.5 text-[20px] font-bold leading-none">
                        <FigureText figure={target.actual} />
                      </p>
                    </div>
                  ) : null}
                </div>

                {target.progress != null ? (
                  <BandProgress value={target.progress} band="targetProgress" label={`진행률 ${target.progress}%`} />
                ) : null}

                {target.guideline ? (
                  <p className="rounded-xl bg-surface-soft px-3 py-2.5 text-[12.5px] leading-relaxed text-charcoal">{target.guideline}</p>
                ) : null}

                <p className="text-[11.5px] leading-snug text-stone">
                  {target.sourceGoalTitle}
                  <br />
                  {target.sourcePlanTitle}
                </p>
              </article>
            ))}
          </div>
        </section>

        <BranchGuides />

        <section>
          <SectionHead title="확인·보고 요청" hint="현장에서 확인이 필요한 사항을 본부로 올립니다" />
          <ReportRequestForm />
        </section>
      </div>
    </>
  );
}
