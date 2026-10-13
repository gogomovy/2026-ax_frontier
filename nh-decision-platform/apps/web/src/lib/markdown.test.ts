import { describe, expect, it } from "vitest";
import { collectCites, parseInline, parseMarkdown, safeHref, type Block, type Inline } from "./markdown";

const text = (xs: Inline[]): string =>
  xs
    .map((x) => {
      if (x.t === "text") return x.v;
      if (x.t === "code") return `\`${x.v}\``;
      if (x.t === "br") return "\n";
      if (x.t === "cite") return x.raw;
      if (x.t === "link") return `<${x.href}|${text(x.c)}>`;
      return `${x.t}(${text(x.c)})`;
    })
    .join("");
const first = (src: string): Block => parseMarkdown(src)[0];

describe("인라인", () => {
  it("굵게 · 기울임 · 취소선 · 코드", () => {
    expect(text(parseInline("충당금 비중은 **9.16%** 입니다"))).toBe("충당금 비중은 strong(9.16%) 입니다");
    expect(text(parseInline("*강조* 와 ~~삭제~~ 와 `code`"))).toBe("em(강조) 와 del(삭제) 와 `code`");
    expect(text(parseInline("**굵게 *안의 기울임* 끝**"))).toBe("strong(굵게 em(안의 기울임) 끝)");
  });

  it("단어 안의 밑줄 · 별표는 서식이 아니다", () => {
    expect(text(parseInline("지표 calc_run_id 와 share_now"))).toBe("지표 calc_run_id 와 share_now");
    expect(text(parseInline("2 * 3 * 4"))).toBe("2 * 3 * 4");
    expect(text(parseInline("__init__ 이름"))).toBe("strong(init) 이름"); // 단어 경계에서 시작하는 __ 는 굵게
  });

  it("닫히지 않은 서식은 글자 그대로 둔다(스트리밍 중간 상태)", () => {
    expect(text(parseInline("비중은 **9.16"))).toBe("비중은 **9.16");
    expect(text(parseInline("코드 `미완"))).toBe("코드 `미완");
    expect(text(parseInline("[링크]("))).toBe("[링크](");
  });

  it("코드 안의 서식 표시는 그대로", () => {
    expect(text(parseInline("`**x**` 와 ``a`b``"))).toBe("`**x**` 와 `a`b`");
  });

  it("줄바꿈은 br", () => {
    expect(text(parseInline("가\n나"))).toBe("가\n나");
    expect(parseInline("가\n나").some((x) => x.t === "br")).toBe(true);
  });

  it("역슬래시로 서식 기호를 글자로", () => {
    expect(text(parseInline("\\*글자\\* 와 \\[1\\]"))).toBe("*글자* 와 [1]");
  });

  it("링크는 안전한 주소만 링크가 된다", () => {
    expect(text(parseInline("[홈](https://nh.example/a?b=1)"))).toBe("<https://nh.example/a?b=1|홈>");
    expect(text(parseInline("[화면](/risk/analysis)"))).toBe("</risk/analysis|화면>");
    expect(text(parseInline("[메일](mailto:a@b.kr)"))).toBe("<mailto:a@b.kr|메일>");
    for (const bad of ["javascript:alert(1)", "data:text/html,x", "//evil.example", "vbscript:x", "JaVaScRiPt:1"]) {
      const out = parseInline(`[클릭](${bad})`);
      expect(out.some((x) => x.t === "link"), bad).toBe(false);
      expect(text(out), bad).toMatch(/^클릭/); // 링크 글자만 남는다(주소 안의 괄호가 만든 남은 ')' 는 글자로)
    }
    expect(safeHref(" https://a.b ")).toBe("https://a.b");
    expect(safeHref("javascript:1")).toBeNull();
    expect(safeHref("//x.y")).toBeNull();
  });

  it("맨 주소는 링크 — 끝의 문장부호는 뺀다", () => {
    expect(text(parseInline("자료: https://nh.example/doc.pdf)."))).toBe("자료: <https://nh.example/doc.pdf|https://nh.example/doc.pdf>).");
  });

  it("HTML 은 해석하지 않고 글자로 남는다", () => {
    const out = parseInline('<img src=x onerror="alert(1)"> <script>x</script>');
    expect(out.every((x) => x.t === "text")).toBe(true);
    expect(text(out)).toBe('<img src=x onerror="alert(1)"> <script>x</script>');
  });

  it("인용 표시", () => {
    const out = parseInline("근거 [지표:share_now] · [분석:포용금융 확대 분석] · [문서:가계부채 관리방안] · [2] · [x](/a)");
    const cites = out.filter((x) => x.t === "cite");
    expect(cites.map((c) => (c.t === "cite" ? `${c.kind}:${c.ref}` : ""))).toEqual(["metric:share_now", "analysis:포용금융 확대 분석", "doc:가계부채 관리방안", "num:2"]);
    expect(out.some((x) => x.t === "link")).toBe(true);
  });
});

describe("블록", () => {
  it("제목 · 문단 · 구분선", () => {
    const b = parseMarkdown("# 큰 제목\n\n본문 첫 줄\n둘째 줄\n\n---\n\n#### 작은 제목");
    expect(b.map((x) => x.t)).toEqual(["h", "p", "hr", "h"]);
    expect(b[0]).toMatchObject({ t: "h", level: 1 });
    expect(b[3]).toMatchObject({ t: "h", level: 4 });
    expect(parseMarkdown("###### 여섯")[0]).toMatchObject({ level: 4 }); // 4단계까지만
    const p = b[1] as Extract<Block, { t: "p" }>;
    expect(text(p.c)).toBe("본문 첫 줄\n둘째 줄");
  });

  it("순서 없는 목록 — 표시(-, *, +)가 섞여도 같은 종류면 한 목록", () => {
    const ul = first("- 하나\n* 둘\n+ 셋") as Extract<Block, { t: "list" }>;
    expect(ul).toMatchObject({ t: "list", ordered: false });
    expect(ul.items).toHaveLength(3);
  });

  it("번호 목록과 시작 번호", () => {
    const ol = first("3. 셋\n4. 넷") as Extract<Block, { t: "list" }>;
    expect(ol).toMatchObject({ ordered: true, start: 3 });
    expect(ol.items).toHaveLength(2);
    // 종류가 바뀌면 새 목록
    const b = parseMarkdown("1. 가\n2. 나\n- 다\n- 라");
    expect(b.map((x) => (x.t === "list" ? (x.ordered ? "ol" : "ul") : x.t))).toEqual(["ol", "ul"]);
  });

  it("중첩 목록 — 들여쓰기", () => {
    const ul = first("- 부모\n  - 자식 1\n  - 자식 2\n    - 손자\n- 다음") as Extract<Block, { t: "list" }>;
    expect(ul.items).toHaveLength(2);
    const [item] = ul.items;
    expect(item.map((b) => b.t)).toEqual(["p", "list"]);
    const child = item[1] as Extract<Block, { t: "list" }>;
    expect(child.items).toHaveLength(2);
    expect(child.items[1].map((b) => b.t)).toEqual(["p", "list"]);
  });

  it("항목 안의 이어지는 줄과 빈 줄 뒤 항목", () => {
    const ul = first("1. 첫째\n   이어지는 줄\n\n2. 둘째") as Extract<Block, { t: "list" }>;
    expect(ul.items).toHaveLength(2);
    expect(text((ul.items[0][0] as Extract<Block, { t: "p" }>).c)).toBe("첫째\n이어지는 줄");
  });

  it("코드 블록 — 언어 · 내용 보존 · 닫히지 않은 블록은 open", () => {
    const b = first("```python\ndef f():\n    return 1  # **굵게 아님**\n```") as Extract<Block, { t: "code" }>;
    expect(b).toMatchObject({ t: "code", lang: "python", open: false });
    expect(b.v).toBe("def f():\n    return 1  # **굵게 아님**");
    const open = first("```sql\nSELECT 1") as Extract<Block, { t: "code" }>;
    expect(open).toMatchObject({ open: true, lang: "sql", v: "SELECT 1" });
    // 코드 블록 안의 빈 줄 · 마크다운 기호는 그대로
    const keep = first("```\na\n\n# not heading\n```") as Extract<Block, { t: "code" }>;
    expect(keep.v).toBe("a\n\n# not heading");
  });

  it("인용", () => {
    const q = first("> 인용 한 줄\n> - 목록도") as Extract<Block, { t: "quote" }>;
    expect(q.t).toBe("quote");
    expect(q.c.map((b) => b.t)).toEqual(["p", "list"]);
  });

  it("표 — 머리 · 정렬 · 행, 셀 안 서식과 이스케이프된 파이프", () => {
    const t = first("| 항목 | 값 | 비고 |\n|:--|--:|:-:|\n| 비중 | **9.16** | a \\| b |\n| 증가율 | 4.04 |") as Extract<Block, { t: "table" }>;
    expect(t.t).toBe("table");
    expect(t.align).toEqual(["left", "right", "center"]);
    expect(t.head.map(text)).toEqual(["항목", "값", "비고"]);
    expect(t.rows).toHaveLength(2);
    expect(text(t.rows[0][1])).toBe("strong(9.16)");
    expect(text(t.rows[0][2])).toBe("a | b");
    expect(t.rows[1]).toHaveLength(3); // 모자란 칸은 빈 칸으로 채운다
    expect(text(t.rows[1][2])).toBe("");
  });

  it("표 머리줄만 온 스트리밍 상태는 문단 — 구분줄이 오면 표", () => {
    expect(first("| 항목 | 값 |").t).toBe("p");
    expect(first("| 항목 | 값 |\n|---|---|").t).toBe("table");
    const mixed = parseMarkdown("설명 문단\n| a | b |\n|---|---|\n| 1 | 2 |\n\n뒤 문단");
    expect(mixed.map((b) => b.t)).toEqual(["p", "table", "p"]);
  });

  it("표 끝 — 파이프 없는 줄에서 끝난다", () => {
    const b = parseMarkdown("| a | b |\n|---|---|\n| 1 | 2 |\n다음 문단");
    expect(b.map((x) => x.t)).toEqual(["table", "p"]);
  });

  it("빈 입력 · 공백 · 윈도 줄바꿈", () => {
    expect(parseMarkdown("")).toEqual([]);
    expect(parseMarkdown("   \n\n  ")).toEqual([]);
    expect(parseMarkdown("가\r\n나").map((b) => b.t)).toEqual(["p"]);
  });

  it("답변 형태 — 결론 문장 + 목록 + 표 + 인용", () => {
    const md = "충당금 비중은 **9.16%** 입니다 [지표:share_now].\n\n- 전월 대비 상승 [분석:포용금융 확대]\n- 한도 이내\n\n| 구분 | 값 |\n|---|---|\n| 비중 | 9.16 |\n\n근거: [문서:포용적 금융 확대방안] [1]";
    const b = parseMarkdown(md);
    expect(b.map((x) => x.t)).toEqual(["p", "list", "table", "p"]);
    expect(collectCites(b)).toEqual([
      { kind: "metric", ref: "share_now" },
      { kind: "analysis", ref: "포용금융 확대" },
      { kind: "doc", ref: "포용적 금융 확대방안" },
      { kind: "num", ref: "1" },
    ]);
  });
});

describe("collectCites", () => {
  it("중복은 한 번 — 처음 나온 순서", () => {
    const b = parseMarkdown("가 [분석:A] 나 [분석:A] 다 [지표:m]\n\n- [문서:D]\n- [분석:A]");
    expect(collectCites(b).map((c) => `${c.kind}:${c.ref}`)).toEqual(["analysis:A", "metric:m", "doc:D"]);
  });
});
