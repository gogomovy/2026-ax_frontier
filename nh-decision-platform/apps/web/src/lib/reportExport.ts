/**
 * 분석 결과 → 보고서 파일 변환 (요구사항 MDL-14)
 *
 * ReportDoc 모델을 그대로 직렬화하므로 화면 DOM 상태와 무관하게 같은 결과가 나온다.
 * 수치는 계산 결과(Figure)를 포맷해 넣고, 마커가 해결되지 않으면 그 사실을 본문에 남긴다
 * (리터럴 숫자 생성 금지 원칙 — PRIN-05).
 * 분석 탭 보고서는 서버 변환(`GET /reports/{tabKey}/export?format=pdf|hwpx|hwp|html`, F.17)을 내려받고,
 * 그 밖의 보고서는 자체 완결 HTML 을 브라우저에서 만든다.
 */
import { EVIDENCE_CATEGORY_LABEL, formatDateTime, formatFigure } from "./format";
import type { Evidence, Figure, ReportBlock, ReportDoc } from "./types";

const FIG_TOKEN = /\[\[fig:([a-zA-Z0-9_\-]+)\]\]/g;
const TERM_TOKEN = /\{\{term:([A-Z_0-9]+)(?:\|([^}]+))?\}\}/g;

function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** 마커를 계산된 수치·용어 표기로 치환한다 */
export function resolveMarkers(text: string, figures: Record<string, Figure> = {}): string {
  return esc(text)
    .replace(FIG_TOKEN, (_m, id: string) => {
      const figure = figures[id];
      return figure ? formatFigure(figure) : `[수치 참조 누락: ${id}]`;
    })
    .replace(TERM_TOKEN, (_m, code: string, label?: string) => label ?? code);
}

function renderEvidence(items: Evidence[]): string {
  if (items.length === 0) return "<p class='muted'>연결된 근거가 없습니다.</p>";
  return `<ul class="evidence">${items
    .map((e) => {
      const category = EVIDENCE_CATEGORY_LABEL[e.category];
      const doc = e.doc
        ? `${esc(e.doc.title)}${e.doc.page ? ` p.${e.doc.page}` : ""}${e.doc.issuer ? ` · ${esc(e.doc.issuer)}` : ""}`
        : esc(e.tableRef ?? "내부 집계");
      const snippet = e.snippet ? `<span class="snippet">${esc(e.snippet)}</span>` : "";
      return `<li><span class="cat">${category}</span> <b>${esc(e.label)}</b><span class="src">${doc}</span>${snippet}</li>`;
    })
    .join("")}</ul>`;
}

function renderBlock(block: ReportBlock, figures: Record<string, Figure>): string {
  switch (block.type) {
    case "p":
      return `<p>${resolveMarkers(block.text ?? "", figures)}</p>`;

    case "ul":
      return `<ul>${(block.items ?? []).map((i) => `<li>${resolveMarkers(i, figures)}</li>`).join("")}</ul>`;

    case "callout":
      return `<div class="callout ${block.tone ?? "info"}">${resolveMarkers(block.text ?? "", figures)}</div>`;

    case "kv":
      return `<dl>${(block.kv ?? [])
        .map((item) => `<div><dt>${esc(item.label)}</dt><dd>${esc(String(item.value))}</dd></div>`)
        .join("")}</dl>`;

    case "table": {
      const t = block.table;
      if (!t) return "";
      const head = t.columns.map((c) => `<th class="${c.align ?? "left"}">${esc(c.label)}</th>`).join("");
      const body = t.rows
        .map((row) => {
          const highlight =
            t.highlightRowKey && String(row[t.highlightRowKey]) === String(t.highlightRowValue) ? " class='hl'" : "";
          const cells = t.columns
            .map((c) => `<td class="${c.align ?? "left"}">${esc(String(row[c.key] ?? "-"))}</td>`)
            .join("");
          return `<tr${highlight}>${cells}</tr>`;
        })
        .join("");
      return `<table>${t.caption ? `<caption>${esc(t.caption)}</caption>` : ""}<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${
        t.note ? `<p class="muted">${esc(t.note)}</p>` : ""
      }`;
    }

    /** 차트는 파일에서 동일 데이터를 표로 제공한다(그래픽 재현 의존 제거) */
    case "chart": {
      const c = block.chart;
      if (!c) return "";
      const categories = c.series[0]?.points.map((p) => p.label) ?? [];
      const head = ["구분", ...c.series.map((s) => s.name)].map((h) => `<th>${esc(h)}</th>`).join("");
      const body = categories
        .map((label, i) => {
          const cells = c.series
            .map((s) => `<td class="right">${s.points[i]?.value ?? "-"}</td>`)
            .join("");
          return `<tr><td>${esc(label)}</td>${cells}</tr>`;
        })
        .join("");
      return `<table><caption>${esc(c.title)} (데이터 표)</caption><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    default:
      return "";
  }
}

export function buildReportHtml(report: ReportDoc): string {
  const opinions = report.opinions
    .map(
      (o) => `<li>
        <p class="op-title">${esc(o.title)}</p>
        <p>${resolveMarkers(o.statement, o.figures)}</p>
        ${renderEvidence(o.evidence)}
      </li>`,
    )
    .join("");

  const sections = report.sections
    .map(
      (s) => `<section>
        <h${s.level}>${esc(s.heading)}</h${s.level}>
        ${s.blocks.map((b) => renderBlock(b, report.figures)).join("")}
      </section>`,
    )
    .join("");

  return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8" />
<title>${esc(report.title)}</title>
<style>
  :root { color-scheme: light }
  body { font-family: "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif;
         max-width: 920px; margin: 40px auto; padding: 0 24px; color: #1c1e21; line-height: 1.6; }
  h1 { font-size: 24px; margin: 0 0 4px }
  h2 { font-size: 18px; margin: 32px 0 8px; padding-bottom: 6px; border-bottom: 1px solid #dee3e9 }
  h3 { font-size: 15px; margin: 20px 0 6px; color: #444950 }
  p, li, td, th { font-size: 13.5px }
  .meta { color: #5d6c7b; font-size: 12px; margin: 0 0 24px }
  .muted { color: #616f7f; font-size: 11.5px }
  .op { background: #f1f4f7; border-radius: 12px; padding: 16px 20px; margin: 0 0 24px }
  .op > p { margin: 0 0 8px; font-weight: 700; font-size: 12px; color: #5d6c7b }
  .op ol { margin: 0; padding-left: 20px }
  .op-title { font-weight: 700; color: #0a1317; margin: 0 0 4px }
  table { width: 100%; border-collapse: collapse; margin: 12px 0 }
  caption { text-align: left; font-size: 12px; color: #5d6c7b; padding-bottom: 6px }
  th, td { border-bottom: 1px solid #dee3e9; padding: 6px 8px; text-align: left }
  th { background: #f1f4f7; font-weight: 700 }
  td.right, th.right { text-align: right; font-variant-numeric: tabular-nums }
  tr.hl td { background: rgba(242,169,24,.14); font-weight: 700 }
  .callout { border-radius: 10px; padding: 10px 14px; margin: 12px 0; background: rgba(0,100,224,.05) }
  .callout.attention { background: rgba(242,169,24,.1) }
  .callout.critical { background: rgba(228,30,63,.06) }
  .callout.success { background: rgba(49,162,76,.07) }
  ul.evidence { list-style: none; padding: 0; margin: 8px 0 0 }
  ul.evidence li { border-top: 1px dashed #dee3e9; padding: 6px 0; font-size: 12px }
  .cat { display: inline-block; background: #e9eef4; border-radius: 10px; padding: 1px 8px; font-size: 11px; margin-right: 6px }
  .src { display: block; color: #5d6c7b; font-size: 11.5px }
  .snippet { display: block; color: #616f7f; font-size: 11.5px }
  dl { margin: 12px 0 }
  dl > div { display: flex; gap: 12px; border-bottom: 1px solid #dee3e9; padding: 4px 0 }
  dt { width: 180px; color: #5d6c7b; font-size: 12px }
  dd { margin: 0; font-size: 13px }
  footer { margin-top: 40px; border-top: 1px solid #dee3e9; padding-top: 12px; color: #616f7f; font-size: 11.5px }
</style></head>
<body>
  <h1>${esc(report.title)}</h1>
  <p class="meta">${esc(report.subtitle)}<br />
    기준일 ${esc(report.asOf)} · 생성 ${esc(formatDateTime(report.generatedAt))} ·
    데이터 성격 ${report.dataOrigin === "simulated" ? "시뮬레이션" : report.dataOrigin === "mixed" ? "혼합" : "실데이터"}
  </p>

  <div class="op">
    <p>AGENT 의견</p>
    <ol>${opinions}</ol>
  </div>

  ${sections}

  <h2>근거</h2>
  ${renderEvidence(report.evidence)}

  <footer>
    본 문서는 AI 분석 결과를 보조 자료로 변환한 것입니다. 최종 판단과 책임은 담당자·의사결정권자에게 있습니다.<br />
    ${esc(report.id)} · ${esc(report.kind)}
  </footer>
</body></html>`;
}

/** 브라우저에서 HTML 보고서 파일을 내려준다 */
export function downloadReport(report: ReportDoc): string {
  const html = buildReportHtml(report);
  const fileName = `${report.asOf.replace(/-/g, "")}_${report.kind}_보고서.html`;
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  return fileName;
}

/** 서버 변환 형식 표시명 */
export const EXPORT_FORMAT_LABEL: Record<string, string> = {
  pdf: "PDF",
  hwpx: "한글 (HWPX)",
  hwp: "한글 (HWP)",
  html: "HTML",
};
/** Content-Disposition 의 filename*(UTF-8) → filename 순으로 파일명을 읽는다 */
function dispositionName(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      /* 잘못된 인코딩 — 아래 폴백 */
    }
  }
  const plain = header.match(/filename="([^"]+)"/i);
  return plain ? plain[1] : fallback;
}
/** 서버에서 변환한 보고서 파일을 내려받는다 (API 모드) */
export async function downloadServerReport(tabKey: string, format: string, office?: string | null): Promise<string> {
  // 영업점 보고서는 지점 인자(B.47 · 다지점)를 함께 — 비우면 서버가 사용자 소속 → 기본 지점
  const officeQs = office ? `&office=${encodeURIComponent(office)}` : "";
  const res = await fetch(`/backend/reports/${encodeURIComponent(tabKey)}/export?format=${encodeURIComponent(format)}${officeQs}`, {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!res.ok) {
    let message = `요청 실패 (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* 본문 없음 */
    }
    throw new Error(message);
  }
  const fileName = dispositionName(res.headers.get("Content-Disposition"), `report.${format}`);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  return fileName;
}
