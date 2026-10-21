"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { IconChevron, IconDoc, SEVERITY_TEXT, StatusDot } from "@/components/ui/primitives";
import { api } from "@/lib/api-client";
import { asOfText, isSharedHref, normalizeLinked, type LinkedAnalysisResponse } from "@/lib/linkedAnalysis";
import type { ActionPlan } from "@/lib/types";

/**
 * 수행방안 상세의 '연결 분석' — 보고서를 열 수 있으면 보고서 링크(공간 주소는 서버가 정한다),
 * 열 수 없으면(영업점 · 다른 부서) 연결 분석 요약(의견 · 주요 수치 · 절 요약)을 그 자리에서 보여 준다.
 * 영업점 참고가 켜진 진행사업이면 사업부서에게도 '영업점에 이 요약이 보인다'고 알려 준다.
 */
export function LinkedAnalysisSection({ plan }: { plan: ActionPlan }) {
  const [res, setRes] = useState<{ id: string; data: LinkedAnalysisResponse | null; error: boolean } | null>(null);
  const linked = Boolean(plan.linkedTabKey || plan.sourceInsightId);

  useEffect(() => {
    if (!linked) return;
    let alive = true;
    api<LinkedAnalysisResponse>(`/screens/plans/${encodeURIComponent(plan.id)}/linked-analysis`)
      .then((r) => alive && setRes({ id: plan.id, data: normalizeLinked(r), error: false }))
      .catch(() => alive && setRes({ id: plan.id, data: null, error: true }));
    return () => {
      alive = false;
    };
  }, [plan.id, linked, plan.branchShared, plan.linkedTabKey]);

  if (!linked) return <p className="text-[12.5px] text-stone">연결된 분석이 없습니다.</p>;
  const cur = res?.id === plan.id ? res : null;
  if (!cur) return <p className="text-[12.5px] text-stone">불러오는 중…</p>;
  const a = cur.data?.analysis ?? null;
  const label = plan.linkedAnalysisLabel ?? a?.title ?? plan.linkedTabKey ?? "연결 분석";
  if (cur.error || !a) {
    return (
      <p className="rounded-xl border border-hairline-soft px-base py-3 text-[12.5px] text-steel">
        <span className="font-bold text-ink-deep">{label}</span> — {cur.error ? "연결 분석을 볼 수 없습니다." : "아직 자료로 계산된 결과가 없습니다."}
      </p>
    );
  }
  const href = cur.data?.href ?? null;
  const shared = isSharedHref(href);
  return (
    <div className="flex flex-col gap-sm" data-linked-analysis={a.tabKey}>
      {href ? (
        <Link href={href} className="flex items-center gap-md rounded-xl border border-hairline-soft px-base py-3">
          <IconDoc className="shrink-0 text-steel" />
          <span className="min-w-0 flex-1 text-[13px] font-bold text-ink-deep">{label}</span>
          <span className="inline-flex shrink-0 items-center gap-1 text-[12px] font-bold text-primary">
            {shared ? "공유 보고서 열기" : "보고서 열기"} <IconChevron />
          </span>
        </Link>
      ) : null}
      {href && !shared && plan.branchShared && plan.status === "in_progress" ? (
        <p className="text-[11.5px] text-steel">
          영업점 참고 중 — 영업본부 · 영업점이 이 보고서 · 근거 문서 · 연결 데이터를 화면 · 질문하기 · 영업점 AI에서 함께 씁니다(지금 결과 기준, 다시 계산하면 그대로 반영).
        </p>
      ) : null}
      {!href || shared ? <AnalysisSummary a={a} /> : null}
    </div>
  );
}

function AnalysisSummary({ a }: { a: NonNullable<LinkedAnalysisResponse["analysis"]> }) {
  return (
    <article className="rounded-xl border border-hairline-soft px-base py-3" aria-label={`연결 분석 요약 — ${a.title}`}>
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <StatusDot severity={a.severity} />
        <h4 className="text-[13.5px] font-bold text-ink-deep">{a.title}</h4>
        <span className="text-[11.5px] text-steel">
          {a.analysisFrom}
          {a.asOf ? ` · ${asOfText(a.asOf)} 기준` : ""} · {SEVERITY_TEXT[a.severity]}
        </span>
      </header>
      {a.subtitle ? <p className="mt-0.5 text-[12px] text-steel">{a.subtitle}</p> : null}
      {a.summary.length ? (
        <ul className="mt-2.5 flex flex-col gap-2">
          {a.summary.map((s, i) => (
            <li key={i} className="text-[12.5px] leading-relaxed text-charcoal">
              <span className="inline-flex items-center gap-1.5 font-bold text-ink-deep">
                <StatusDot severity={s.severity} />
                {s.title}
              </span>
              {s.text ? <span className="mt-0.5 block">{s.text}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {a.keyFigures.length ? (
        <div className="mt-2.5 flex flex-wrap gap-1.5" aria-label="주요 수치">
          {a.keyFigures.map((f) => (
            <span key={f} className="rounded-pill bg-surface-soft px-2.5 py-1 text-[11.5px] text-charcoal tnum">
              {f}
            </span>
          ))}
        </div>
      ) : null}
      {a.sections.length ? (
        <div className="mt-2.5 flex flex-col gap-1">
          {a.sections.map((s, i) => (
            <details key={i} className="rounded-lg bg-surface-soft px-3 py-1.5">
              <summary className="cursor-pointer text-[12px] font-bold text-ink-deep">{s.heading || `절 ${i + 1}`}</summary>
              <ul className="mt-1 flex flex-col gap-0.5 pb-1">
                {s.lines.map((ln, j) => (
                  <li key={j} className="text-[12px] leading-relaxed text-charcoal">
                    {ln}
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      ) : null}
      {a.limitations.length ? (
        <p className="mt-2 text-[11px] leading-relaxed text-stone">한계 · {a.limitations.join(" · ")}</p>
      ) : null}
      <p className="mt-2 text-[10.5px] text-stone">사업부서 분석 결과의 요약입니다(지금 보고서 기준). 수치는 사업부서 기준이며 지점 수치와 다를 수 있습니다.</p>
    </article>
  );
}
