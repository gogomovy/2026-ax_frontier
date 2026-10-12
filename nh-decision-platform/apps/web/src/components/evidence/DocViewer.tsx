"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { Badge, IconDoc, IconWarn } from "@/components/ui/primitives";
import type { DocumentView, DocumentViewPage } from "@/lib/types";

/** 면 본문을 하이라이트 구간으로 나눠 그린다 */
function PageText({ page }: { page: DocumentViewPage }) {
  const parts = useMemo(() => {
    const out: { text: string; mark: boolean }[] = [];
    let at = 0;
    for (const h of [...page.highlights].sort((a, b) => a.start - b.start)) {
      if (h.start > at) out.push({ text: page.text.slice(at, h.start), mark: false });
      out.push({ text: page.text.slice(Math.max(h.start, at), h.end), mark: true });
      at = Math.max(at, h.end);
    }
    if (at < page.text.length) out.push({ text: page.text.slice(at), mark: false });
    return out;
  }, [page]);
  return (
    <div className="whitespace-pre-wrap break-words text-[14px] leading-[1.85] text-ink" data-doc-page={page.page}>
      {parts.map((p, i) =>
        p.mark ? (
          <mark key={i} data-highlight className="rounded-sm bg-highlight px-0.5 text-ink-deep">
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </div>
  );
}

/**
 * 원본 문서 뷰어 (F.12 · DB-07)
 *  - 면 목록 · 이전/다음 면 · 근거 인용 위치 하이라이트(첫 위치로 자동 이동)
 *  - 원본 파일이 저장된 문서는 원본 열기(새 창), 시드 문서는 인용이 실린 면만 표시
 */
export function DocViewer({ view }: { view: DocumentView }) {
  const pages = view.pages;
  const initial = Math.max(
    0,
    pages.findIndex((p) => p.page === view.focusPage),
  );
  const [index, setIndex] = useState(initial);
  const current = pages[index];
  const bodyRef = useRef<HTMLDivElement>(null);

  /* 면을 바꾸면 첫 하이라이트(없으면 본문 맨 위)로 이동 */
  useEffect(() => {
    const first = bodyRef.current?.querySelector("mark[data-highlight]");
    if (first) first.scrollIntoView({ block: "center" });
    else bodyRef.current?.scrollTo({ top: 0 });
  }, [index]);

  const go = (next: number) => setIndex(Math.min(Math.max(next, 0), pages.length - 1));

  return (
    <div className="grid grid-cols-1 gap-lg lg:grid-cols-[200px_1fr]">
      <nav aria-label="면 목록" className="lg:sticky lg:top-lg lg:self-start">
        <p className="mb-2 text-[11px] font-bold text-steel">
          {view.source === "excerpt" ? `수록 면 ${pages.length} / 전체 ${view.pageCount}면` : `전체 ${pages.length}면`}
        </p>
        <ul className="flex max-h-[60vh] flex-row flex-wrap gap-1.5 overflow-y-auto lg:flex-col lg:flex-nowrap">
          {pages.map((p, i) => (
            <li key={p.page}>
              <button
                type="button"
                aria-current={i === index ? "page" : undefined}
                onClick={() => go(i)}
                className={clsx(
                  "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-[12.5px]",
                  i === index ? "bg-ink-deep font-bold text-white" : "bg-surface-soft text-charcoal",
                )}
              >
                <span>p.{p.page}</span>
                {p.highlights.length ? (
                  <span
                    className={clsx(
                      "rounded-pill px-1.5 text-[10.5px] font-bold",
                      i === index ? "bg-white/20 text-white" : "bg-attention-soft text-warning",
                    )}
                  >
                    인용 {p.highlights.length}
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <section aria-label="본문" className="panel flex min-h-[420px] flex-col">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline-soft px-xl py-base">
          <div className="flex items-center gap-2">
            <IconDoc className="text-steel" />
            <h2 className="text-[14px] font-bold text-ink-deep">
              p.{current?.page ?? "-"}
              {current?.section ? <span className="ml-2 text-[12px] font-normal text-steel">{current.section}</span> : null}
            </h2>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => go(index - 1)}
              disabled={index === 0}
              className="rounded-pill bg-surface-soft px-3 py-1.5 text-[12px] font-bold text-charcoal disabled:opacity-40"
            >
              이전 면
            </button>
            <button
              type="button"
              onClick={() => go(index + 1)}
              disabled={index >= pages.length - 1}
              className="rounded-pill bg-surface-soft px-3 py-1.5 text-[12px] font-bold text-charcoal disabled:opacity-40"
            >
              다음 면
            </button>
          </div>
        </header>

        {view.query && !view.matched ? (
          <p className="mx-xl mt-base flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-[12px] text-warning">
            <IconWarn className="mt-0.5" />
            인용문과 일치하는 위치를 본문에서 찾지 못했습니다. 근거가 요약 인용이거나 문서 버전이 바뀌었을 수 있습니다.
          </p>
        ) : null}

        <div ref={bodyRef} className="max-h-[70vh] flex-1 overflow-y-auto px-xl py-lg">
          {current && current.text ? (
            <PageText page={current} />
          ) : (
            <p className="text-[13px] text-stone">이 면에서 추출된 텍스트가 없습니다(스캔 이미지일 수 있습니다).</p>
          )}
        </div>
      </section>
    </div>
  );
}

/** 뷰어 머리말 우측 — 출처 성격 · 원본 파일 열기 */
export function DocViewerActions({ view }: { view: DocumentView }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {view.source === "file" ? <Badge tone="success">원본 파일 본문</Badge> : null}
      {view.source === "excerpt" ? <Badge tone="warning">원본 미등록 · 근거 발췌</Badge> : null}
      {view.source === "chunks" ? <Badge tone="info">업로드 텍스트</Badge> : null}
      {view.hasFile ? (
        <a
          href={`/backend/documents/${view.origin}/${encodeURIComponent(view.docId)}/file`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-pill bg-ink-deep px-4 py-2 text-[12px] font-bold text-white"
        >
          <IconDoc />
          원본 파일 열기
        </a>
      ) : null}
    </div>
  );
}
