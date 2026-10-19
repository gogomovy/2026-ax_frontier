/**
 * 파일 이름 → 올릴 자료 추천 (Phase E · UXF-02 · Q121) — 업무 [자료 올리기] · 관리자 [데이터셋·문서]가 함께 쓴다.
 *
 * 점수: 이름 규칙 정규식(filePattern) 일치 100 · 데이터셋 코드가 파일 이름에 있음 60 ·
 *       보고서 번호(이름의 4자리 숫자, 예 7790)가 파일 이름의 숫자 묶음과 같음 50 · 이름 낱말(2자 이상) 겹침 낱말당 10(최대 40).
 * 정규식이 브라우저에서 해석되지 않으면(파이썬 전용 문법) 건너뛴다. 자동 확정은 하지 않는다 — 1순위를 추천으로 보여 준다.
 */

export interface MatchableDataset {
  code: string;
  name: string;
  filePattern?: string | null;
}

export interface DatasetSuggestion {
  code: string;
  score: number;
  reasons: string[];
}

const ext = (name: string) => {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
};

/** accept(".csv,.xlsx …")에 확장자가 있는지 */
export function acceptsFile(name: string, accept: string): boolean {
  const list = accept
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  return !list.length || list.includes(ext(name));
}

/** 확장자로 정형 자료 · 문서 구분 — 둘 다 아니면 null */
export function kindOf(name: string, accept: { dataset: string; document: string }): "dataset" | "document" | null {
  if (acceptsFile(name, accept.dataset)) return "dataset";
  if (acceptsFile(name, accept.document)) return "document";
  return null;
}

/** 마크다운에 데이터 행이 있는 파이프 표('| a | b |' 아래 '|---|---|')가 있는가 — 서버 data/mdtable.is_md_table 과 같은 기준 (Phase Q · MD-04) */
export function hasMdTable(text: string): boolean {
  const sep = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
  const lines = text.split(/\r?\n/);
  for (let i = 0; i + 2 < lines.length; i++) {
    if (lines[i].includes("|") && !sep.test(lines[i]) && sep.test(lines[i + 1]) && lines[i + 2].includes("|") && lines[i + 2].trim()) return true;
  }
  return false;
}

/** .md 는 내용으로 구분 — 표가 있으면 정형 자료, 없으면 문서. 그 밖은 확장자 (kindOf) */
export function kindOfContent(name: string, text: string | null, accept: { dataset: string; document: string }): "dataset" | "document" | null {
  if (ext(name) === ".md") {
    if (text !== null && !hasMdTable(text)) return acceptsFile(name, accept.document) ? "document" : null;
    return acceptsFile(name, accept.dataset) ? "dataset" : acceptsFile(name, accept.document) ? "document" : null;
  }
  return kindOf(name, accept);
}

/** 파일 이름에서 확장자를 뺀 제목 */
export function titleFromFile(name: string): string {
  const base = name.replace(/\.[^.]+$/, "");
  return base.replace(/[_]+/g, " ").replace(/\s+/g, " ").trim();
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)}KB`;
  return `${(n / 1024 / 1024).toFixed(1)}MB`;
}

const words = (s: string) =>
  (s.toLowerCase().match(/[0-9a-z가-힣]+/g) ?? []).filter((w) => w.length >= 2 && !/^\d+$/.test(w));

function patternMatches(pattern: string, fileName: string): boolean {
  try {
    return new RegExp(pattern, "i").test(fileName);
  } catch {
    return false;
  }
}

export function suggestDatasets(fileName: string, datasets: MatchableDataset[]): DatasetSuggestion[] {
  const low = fileName.toLowerCase();
  const norm = low.replace(/[\s_\-·()[\]]+/g, "");
  const fileNums = new Set(fileName.match(/\d+/g) ?? []);
  const fileWords = new Set(words(fileName.replace(/\.[^.]+$/, "")));
  const out: DatasetSuggestion[] = [];
  for (const d of datasets) {
    let score = 0;
    const reasons: string[] = [];
    if (d.filePattern && patternMatches(d.filePattern, fileName)) {
      score += 100;
      reasons.push("파일 이름 규칙 일치");
    }
    const code = d.code.toLowerCase();
    if (low.includes(code) || norm.includes(code.replace(/_/g, ""))) {
      score += 60;
      reasons.push(`코드 ${d.code} 포함`);
    }
    const report = (d.name.match(/\b\d{4}\b/g) ?? []).find((n) => fileNums.has(n));
    if (report) {
      score += 50;
      reasons.push(`보고서 번호 ${report} 일치`);
    }
    const shared = words(d.name).filter((w) => fileWords.has(w) || [...fileWords].some((f) => f.length >= 3 && (f.includes(w) || w.includes(f))));
    if (shared.length) {
      score += Math.min(40, shared.length * 10);
      reasons.push(`이름 낱말 ${shared.length}개 겹침(${shared.slice(0, 3).join(" · ")})`);
    }
    if (score > 0) out.push({ code: d.code, score, reasons });
  }
  return out.sort((a, b) => b.score - a.score || a.code.localeCompare(b.code));
}

/** 추천으로 바로 고를 만큼 확실한가 — 이름 규칙 · 코드 · 보고서 번호 중 하나는 맞아야(낱말만 겹치면 목록에서 고르게) */
export function confidentSuggestion(s: DatasetSuggestion[] | null | undefined): DatasetSuggestion | null {
  const top = s?.[0];
  return top && top.score >= 50 ? top : null;
}
