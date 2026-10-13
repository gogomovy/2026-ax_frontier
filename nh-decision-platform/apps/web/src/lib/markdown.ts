/**
 * 채팅 답변용 마크다운 파서 — 외부 라이브러리 없이 안전한 AST 로 바꾼다(HTML 을 만들지 않고, 화면 쪽은 React 요소로만 그린다).
 *
 * 지원: 제목(#~####) · 문단(한 줄 바꿈은 줄바꿈으로) · 굵게/기울임/취소선 · 인라인 코드 · 코드 블록(```언어) · 인용(>) ·
 *       순서 있는/없는 목록(들여쓰기 중첩) · 표(GFM, 정렬) · 구분선 · 링크([글](주소) · 맨 주소) · 인용 표시([지표:코드] · [분석:제목] · [문서:제목] · [1]).
 * 스트리밍 중간 상태를 견딘다 — 닫히지 않은 코드 블록은 열린 채로(open=true), 아직 구분선이 오지 않은 표 머리줄은 문단으로 보인다.
 * 링크 주소는 http · https · mailto · 사이트 안 경로(/…)만 허용한다(javascript: 등은 글자로만 남김).
 */

export type CiteKind = "metric" | "analysis" | "doc" | "num";

export type Inline =
  | { t: "text"; v: string }
  | { t: "code"; v: string }
  | { t: "strong"; c: Inline[] }
  | { t: "em"; c: Inline[] }
  | { t: "del"; c: Inline[] }
  | { t: "link"; href: string; c: Inline[] }
  | { t: "br" }
  | { t: "cite"; kind: CiteKind; ref: string; raw: string };

export type Block =
  | { t: "p"; c: Inline[] }
  | { t: "h"; level: 1 | 2 | 3 | 4; c: Inline[] }
  | { t: "list"; ordered: boolean; start: number; items: Block[][] }
  | { t: "quote"; c: Block[] }
  | { t: "code"; lang: string; v: string; open: boolean }
  | { t: "table"; align: (("left" | "right" | "center") | null)[]; head: Inline[][]; rows: Inline[][][] }
  | { t: "hr" };

const CITE_LABEL: Record<string, CiteKind> = { 지표: "metric", 분석: "analysis", 문서: "doc" };

/** 링크 주소 검사 — 안전한 것만 돌려주고 아니면 null */
export function safeHref(raw: string): string | null {
  const href = raw.trim();
  if (!href) return null;
  if (/^(https?:\/\/|mailto:)/i.test(href)) return href;
  if (href.startsWith("/") && !href.startsWith("//")) return href;
  return null;
}

const ESCAPABLE = /[\\`*_{}[\]()#+\-.!|~>]/;

function findClosing(s: string, from: number, token: string): number {
  let i = from;
  while (i < s.length) {
    if (s[i] === "\\") {
      i += 2;
      continue;
    }
    if (s[i] === "`") {
      // 코드 안의 표시는 무시
      const end = s.indexOf("`", i + 1);
      if (end < 0) return -1;
      i = end + 1;
      continue;
    }
    if (s.startsWith(token, i)) return i;
    i++;
  }
  return -1;
}

const isWordChar = (ch: string | undefined) => !!ch && /[\p{L}\p{N}]/u.test(ch);

/** 인라인 서식 */
export function parseInline(s: string): Inline[] {
  const out: Inline[] = [];
  let buf = "";
  const flush = () => {
    if (buf) {
      out.push({ t: "text", v: buf });
      buf = "";
    }
  };
  let i = 0;
  while (i < s.length) {
    const ch = s[i];
    if (ch === "\\" && i + 1 < s.length && ESCAPABLE.test(s[i + 1])) {
      buf += s[i + 1];
      i += 2;
      continue;
    }
    if (ch === "\n") {
      flush();
      out.push({ t: "br" });
      i++;
      continue;
    }
    if (ch === "`") {
      let n = 1;
      while (s[i + n] === "`") n++;
      const fence = "`".repeat(n);
      const end = s.indexOf(fence, i + n);
      if (end >= 0) {
        flush();
        out.push({ t: "code", v: s.slice(i + n, end).replace(/^ (.*) $/, "$1") });
        i = end + n;
        continue;
      }
      buf += fence;
      i += n;
      continue;
    }
    if (ch === "[") {
      const cite = /^\[(지표|분석|문서)\s*:\s*([^\]\n]+)\]/.exec(s.slice(i));
      if (cite) {
        flush();
        out.push({ t: "cite", kind: CITE_LABEL[cite[1]], ref: cite[2].trim(), raw: cite[0] });
        i += cite[0].length;
        continue;
      }
      const num = /^\[(\d{1,3})\](?!\()/.exec(s.slice(i));
      if (num) {
        flush();
        out.push({ t: "cite", kind: "num", ref: num[1], raw: num[0] });
        i += num[0].length;
        continue;
      }
      const link = /^\[([^\]\n]+)\]\(\s*([^)\s]+)(?:\s+"[^"]*")?\s*\)/.exec(s.slice(i));
      if (link) {
        const href = safeHref(link[2]);
        flush();
        if (href) out.push({ t: "link", href, c: parseInline(link[1]) });
        else out.push(...parseInline(link[1]));
        i += link[0].length;
        continue;
      }
    }
    if (s.startsWith("**", i) || s.startsWith("__", i)) {
      const tok = s.slice(i, i + 2);
      const end = findClosing(s, i + 2, tok);
      const leftOk = tok === "**" || !isWordChar(s[i - 1]);
      if (end > i + 2 && leftOk && !/^\s/.test(s.slice(i + 2, i + 3)) && (tok === "**" || !isWordChar(s[end + 2]))) {
        flush();
        out.push({ t: "strong", c: parseInline(s.slice(i + 2, end)) });
        i = end + 2;
        continue;
      }
    }
    if (s.startsWith("~~", i)) {
      const end = findClosing(s, i + 2, "~~");
      if (end > i + 2) {
        flush();
        out.push({ t: "del", c: parseInline(s.slice(i + 2, end)) });
        i = end + 2;
        continue;
      }
    }
    if ((ch === "*" || ch === "_") && s[i + 1] !== ch) {
      const end = findClosing(s, i + 1, ch);
      const leftOk = ch === "*" || !isWordChar(s[i - 1]);
      if (end > i + 1 && leftOk && !/\s/.test(s[i + 1]) && !/\s/.test(s[end - 1]) && (ch === "*" || !isWordChar(s[end + 1]))) {
        flush();
        out.push({ t: "em", c: parseInline(s.slice(i + 1, end)) });
        i = end + 1;
        continue;
      }
    }
    if ((ch === "h" || ch === "H") && /^https?:\/\//i.test(s.slice(i, i + 8))) {
      const m = /^https?:\/\/[^\s<>]+/i.exec(s.slice(i));
      if (m) {
        const url = m[0].replace(/[.,;:!?)\]]+$/, "");
        flush();
        out.push({ t: "link", href: url, c: [{ t: "text", v: url }] });
        i += url.length;
        continue;
      }
    }
    buf += ch;
    i++;
  }
  flush();
  return out;
}

const FENCE = /^(\s*)(`{3,}|~{3,})\s*([\w+#.-]*)\s*$/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const HR = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
const ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
const TABLE_SEP = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;

function splitRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|") && !s.endsWith("\\|")) s = s.slice(0, -1);
  const cells: string[] = [];
  let cur = "";
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "\\" && s[i + 1] === "|") {
      cur += "|";
      i++;
    } else if (s[i] === "`") {
      const end = s.indexOf("`", i + 1);
      if (end > 0) {
        cur += s.slice(i, end + 1);
        i = end;
      } else cur += s[i];
    } else if (s[i] === "|") {
      cells.push(cur.trim());
      cur = "";
    } else cur += s[i];
  }
  cells.push(cur.trim());
  return cells;
}

const isBlockStart = (line: string) => FENCE.test(line) || HEADING.test(line) || HR.test(line) || /^\s*>/.test(line) || ITEM.test(line);

function parseList(lines: string[], from: number): { block: Block; next: number } {
  const first = ITEM.exec(lines[from])!;
  const baseIndent = first[1].replace(/\t/g, "    ").length;
  const ordered = /\d/.test(first[2]);
  const start = ordered ? parseInt(first[2], 10) : 1;
  const items: Block[][] = [];
  let i = from;
  let cur: string[] | null = null;
  const closeItem = () => {
    if (cur) items.push(parseBlocks(cur));
    cur = null;
  };
  while (i < lines.length) {
    const line = lines[i];
    const m = ITEM.exec(line);
    const indent = (m ? m[1] : /^\s*/.exec(line)![0]).replace(/\t/g, "    ").length;
    if (m && indent <= baseIndent + 1 && indent >= baseIndent - 1) {
      if (/\d/.test(m[2]) !== ordered) break; // 다른 종류의 목록이 시작
      closeItem();
      cur = [m[3]];
      i++;
      continue;
    }
    if (m && indent > baseIndent + 1 && cur) {
      cur.push(line.slice(Math.min(line.length, baseIndent + 2))); // 중첩 목록 — 들여쓴 줄을 항목 안으로
      i++;
      continue;
    }
    if (!line.trim()) {
      // 빈 줄 뒤에 같은 목록의 항목이나 들여쓴 이어지는 줄이 오면 계속
      let j = i + 1;
      while (j < lines.length && !lines[j].trim()) j++;
      if (j < lines.length && (ITEM.test(lines[j]) || /^\s{2,}\S/.test(lines[j]))) {
        const nm = ITEM.exec(lines[j]);
        const nIndent = (nm ? nm[1] : /^\s*/.exec(lines[j])![0]).replace(/\t/g, "    ").length;
        if (nm && nIndent < baseIndent - 1) break;
        if (nm && nIndent <= baseIndent + 1 && /\d/.test(nm[2]) !== ordered) break;
        if (cur) cur.push("");
        i++;
        continue;
      }
      break;
    }
    if (indent > baseIndent && cur) {
      cur.push(line.slice(Math.min(line.length, baseIndent + 2))); // 항목의 이어지는 줄
      i++;
      continue;
    }
    break;
  }
  closeItem();
  return { block: { t: "list", ordered, start, items }, next: i };
}

/** 블록 파서 */
export function parseBlocks(lines: string[]): Block[] {
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const fence = FENCE.exec(line);
    if (fence) {
      const mark = fence[2][0];
      const len = fence[2].length;
      const body: string[] = [];
      i++;
      let open = true;
      while (i < lines.length) {
        const close = new RegExp(`^\\s*${mark === "`" ? "`" : "~"}{${len},}\\s*$`).test(lines[i]);
        if (close) {
          open = false;
          i++;
          break;
        }
        body.push(lines[i]);
        i++;
      }
      out.push({ t: "code", lang: fence[3] || "", v: body.join("\n"), open });
      continue;
    }
    const h = HEADING.exec(line);
    if (h) {
      out.push({ t: "h", level: Math.min(4, h[1].length) as 1 | 2 | 3 | 4, c: parseInline(h[2]) });
      i++;
      continue;
    }
    if (HR.test(line)) {
      out.push({ t: "hr" });
      i++;
      continue;
    }
    if (/^\s*>/.test(line)) {
      const body: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        body.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      out.push({ t: "quote", c: parseBlocks(body) });
      continue;
    }
    if (ITEM.test(line)) {
      const { block, next } = parseList(lines, i);
      out.push(block);
      i = next;
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const head = splitRow(line);
      const sep = splitRow(lines[i + 1]);
      if (sep.length === head.length || sep.length >= 1) {
        const align = head.map((_, k) => {
          const c = sep[k] ?? "";
          const l = c.startsWith(":");
          const r = c.endsWith(":");
          return l && r ? "center" : r ? "right" : l ? "left" : null;
        }) as ("left" | "right" | "center" | null)[];
        const rows: Inline[][][] = [];
        i += 2;
        while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
          const cells = splitRow(lines[i]);
          rows.push(head.map((_, k) => parseInline(cells[k] ?? "")));
          i++;
        }
        out.push({ t: "table", align, head: head.map((c) => parseInline(c)), rows });
        continue;
      }
    }
    // 문단 — 다른 블록이 시작하기 전까지 이어 붙인다(줄바꿈은 그대로 줄바꿈으로)
    const body: string[] = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i]) && !(lines[i].includes("|") && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1]) && lines[i + 1].includes("-"))) {
      body.push(lines[i]);
      i++;
    }
    out.push({ t: "p", c: parseInline(body.map((l) => l.trim()).join("\n")) });
  }
  return out;
}

export function parseMarkdown(src: string): Block[] {
  return parseBlocks((src ?? "").replace(/\r\n?/g, "\n").split("\n"));
}

/** 답변 안의 인용 표시를 나온 순서대로(중복 제거) — 번호 매기기용 */
export function collectCites(blocks: Block[]): { kind: CiteKind; ref: string }[] {
  const seen = new Set<string>();
  const out: { kind: CiteKind; ref: string }[] = [];
  const add = (kind: CiteKind, ref: string) => {
    const k = `${kind}:${ref}`;
    if (!seen.has(k)) {
      seen.add(k);
      out.push({ kind, ref });
    }
  };
  const inl = (xs: Inline[]) => {
    for (const x of xs) {
      if (x.t === "cite") add(x.kind, x.ref);
      else if ("c" in x) inl(x.c);
    }
  };
  const blk = (bs: Block[]) => {
    for (const b of bs) {
      if (b.t === "p" || b.t === "h") inl(b.c);
      else if (b.t === "list") b.items.forEach(blk);
      else if (b.t === "quote") blk(b.c);
      else if (b.t === "table") {
        b.head.forEach(inl);
        b.rows.forEach((r) => r.forEach(inl));
      }
    }
  };
  blk(blocks);
  return out;
}

/** 클립보드에 복사할 순수 글 — 마크다운 기호는 두고(표 · 목록 구조 유지) 인용 표시만 읽기 좋게 */
export function plainForCopy(src: string): string {
  return (src ?? "").replace(/\[(지표|분석|문서)\s*:\s*([^\]\n]+)\]/g, "[$1: $2]").trim();
}
