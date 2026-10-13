"use client";

import clsx from "clsx";
import { Fragment, useMemo, useState, type ReactNode } from "react";
import { ScrollRegion } from "@/components/ui/ScrollRegion";
import type { CiteTarget } from "@/lib/assist-chat";
import { copyText } from "@/lib/clipboard";
import { parseMarkdown, type Block, type Inline } from "@/lib/markdown";

/** 인용 표시를 그릴 때 필요한 것 — `kind:ref` → 번호가 붙은 출처, 눌렀을 때 동작 */
export interface CiteApi {
  resolve: (kind: string, ref: string) => CiteTarget | undefined;
  onOpen: (t: CiteTarget) => void;
}

function CiteChip({ node, api }: { node: Extract<Inline, { t: "cite" }>; api?: CiteApi }) {
  const t = api?.resolve(node.kind, node.ref);
  if (!t) {
    // 출처에서 찾지 못한 인용은 번호를 꾸며내지 않고 흐린 글자로 둔다
    return <span className="mx-0.5 align-baseline text-[11px] text-stone">{node.raw}</span>;
  }
  return (
    <button
      type="button"
      onClick={() => api?.onOpen(t)}
      aria-label={`출처 ${t.n}: ${t.label}`}
      title={t.label}
      className="mx-0.5 inline-flex h-[18px] min-w-[18px] translate-y-[-1px] items-center justify-center rounded-pill bg-info-soft px-1 align-middle text-[10.5px] font-bold leading-none text-primary transition-colors hover:bg-primary hover:text-on-primary"
    >
      {t.n}
    </button>
  );
}

function Inlines({ xs, api }: { xs: Inline[]; api?: CiteApi }) {
  return (
    <>
      {xs.map((x, i) => {
        switch (x.t) {
          case "text":
            return <Fragment key={i}>{x.v}</Fragment>;
          case "br":
            return <br key={i} />;
          case "code":
            return (
              <code key={i} className="rounded-md bg-surface-soft px-1.5 py-0.5 font-mono text-[0.88em] text-ink-deep">
                {x.v}
              </code>
            );
          case "strong":
            return (
              <strong key={i} className="font-bold text-ink-deep">
                <Inlines xs={x.c} api={api} />
              </strong>
            );
          case "em":
            return (
              <em key={i}>
                <Inlines xs={x.c} api={api} />
              </em>
            );
          case "del":
            return (
              <del key={i} className="text-stone">
                <Inlines xs={x.c} api={api} />
              </del>
            );
          case "link": {
            const external = /^(https?:|mailto:)/i.test(x.href);
            return (
              <a key={i} href={x.href} className="text-primary underline underline-offset-2" {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
                <Inlines xs={x.c} api={api} />
                {external ? <span className="sr-only"> (새 창)</span> : null}
              </a>
            );
          }
          case "cite":
            return <CiteChip key={i} node={x} api={api} />;
        }
      })}
    </>
  );
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (await copyText(code)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };
  return (
    <figure className="my-3 overflow-hidden rounded-xl border border-hairline-soft bg-surface-soft">
      <figcaption className="flex items-center justify-between border-b border-hairline-soft px-3 py-1.5 text-[11px] text-steel">
        <span className="font-mono">{lang || "코드"}</span>
        <button type="button" onClick={copy} className="rounded-md px-2 py-0.5 font-bold text-charcoal hover:bg-canvas">
          {copied ? "복사됨" : "복사"}
          <span className="sr-only"> — {lang || "코드"} 블록</span>
        </button>
      </figcaption>
      <ScrollRegion label={`${lang || "코드"} 블록`} className="overflow-x-auto">
        <pre className="m-0 p-3 text-[12.5px] leading-relaxed text-ink-deep">
          <code className="font-mono">{code}</code>
        </pre>
      </ScrollRegion>
    </figure>
  );
}

const ALIGN = { left: "text-left", right: "text-right", center: "text-center" } as const;

function Blocks({ bs, api, trailing }: { bs: Block[]; api?: CiteApi; trailing?: ReactNode }) {
  return (
    <>
      {bs.map((b, i) => (
        <BlockView key={i} b={b} api={api} trailing={i === bs.length - 1 ? trailing : undefined} />
      ))}
    </>
  );
}

function BlockView({ b, api, trailing }: { b: Block; api?: CiteApi; trailing?: ReactNode }) {
  switch (b.t) {
    case "p":
      return (
        <p className="my-2 first:mt-0 last:mb-0">
          <Inlines xs={b.c} api={api} />
          {trailing}
        </p>
      );
    case "h": {
      // 채팅 안의 제목은 화면 제목(h1~h2)보다 낮은 단계로 — 문서 구조를 해치지 않게 h3 부터
      const cls = ["mt-4 mb-2 text-[18px] font-bold text-ink-deep", "mt-4 mb-2 text-[16px] font-bold text-ink-deep", "mt-3 mb-1.5 text-[14.5px] font-bold text-ink-deep", "mt-3 mb-1 text-[13.5px] font-bold text-steel"][b.level - 1];
      const H = (["h3", "h3", "h4", "h5"] as const)[b.level - 1];
      return (
        <H className={clsx(cls, "first:mt-0")}>
          <Inlines xs={b.c} api={api} />
          {trailing}
        </H>
      );
    }
    case "list": {
      const items = b.items.map((item, i) => (
        <li key={i} className="pl-0.5 [&>p]:my-0.5 [&>ol]:my-1 [&>ul]:my-1">
          <Blocks bs={item} api={api} trailing={i === b.items.length - 1 ? trailing : undefined} />
        </li>
      ));
      const cls = "my-2 space-y-1 pl-5 marker:text-stone first:mt-0 last:mb-0";
      return b.ordered ? (
        <ol className={clsx(cls, "list-decimal")} start={b.start}>
          {items}
        </ol>
      ) : (
        <ul className={clsx(cls, "list-disc")}>{items}</ul>
      );
    }
    case "quote":
      return (
        <blockquote className="my-3 border-l-4 border-hairline pl-3 text-steel">
          <Blocks bs={b.c} api={api} trailing={trailing} />
        </blockquote>
      );
    case "code":
      return (
        <>
          <CodeBlock lang={b.lang} code={b.v} />
          {trailing}
        </>
      );
    case "table":
      return (
        <div className="my-3 rounded-xl border border-hairline-soft">
          <ScrollRegion label="표" className="overflow-x-auto rounded-xl">
            <table className="w-full border-collapse text-[13px]">
              <thead className="bg-surface-soft">
                <tr>
                  {b.head.map((h, k) => (
                    <th key={k} scope="col" className={clsx("whitespace-nowrap px-3 py-2 font-bold text-ink-deep", ALIGN[b.align[k] ?? "left"])}>
                      <Inlines xs={h} api={api} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {b.rows.map((r, ri) => (
                  <tr key={ri}>
                    {r.map((c, k) => (
                      <td key={k} className={clsx("border-t border-hairline-soft px-3 py-2 align-top text-charcoal tabular-nums", ALIGN[b.align[k] ?? "left"])}>
                        <Inlines xs={c} api={api} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollRegion>
          {trailing}
        </div>
      );
    case "hr":
      return <hr className="my-4 border-hairline-soft" />;
  }
}

/** 답변 마크다운 — HTML 을 거치지 않고 React 요소로만 그린다(스크립트 · 이벤트 속성이 들어갈 길이 없다). trailing 은 마지막 글줄 끝에 붙는다(스트리밍 커서) */
export function Markdown({ source, cites, trailing, className }: { source: string; cites?: CiteApi; trailing?: ReactNode; className?: string }) {
  const blocks = useMemo(() => parseMarkdown(source), [source]);
  return (
    <div className={clsx("break-words text-[14px] leading-[1.7] text-ink", className)}>
      {blocks.length ? <Blocks bs={blocks} api={cites} trailing={trailing} /> : trailing}
    </div>
  );
}
