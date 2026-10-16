import { cloneElement, isValidElement, type ReactNode } from "react";
/**
 * Agent 해설 문장 다듬기 — 해요체(구어체) + 마침표로 끝맺는다.
 * 서버 서술은 '…있습니다' 같은 합쇼체가 섞여 오므로, 화면에 보일 결론 한 문장만 끝말을 바꾼다.
 * 문장 가운데는 손대지 않고 맨 끝 어미만 바꾼다(의미 · 수치 표식은 그대로).
 */

/** 한글 음절에 받침이 있는가 */
function hasBatchim(ch: string): boolean {
  const code = ch.charCodeAt(0) - 0xac00;
  return code >= 0 && code <= 11171 && code % 28 !== 0;
}

/** 끝 어미 하나를 해요체로 — 바꿀 규칙이 없으면 그대로 */
function politeEnding(s: string): string {
  if (/(요|죠)$/.test(s)) return s;
  // '…됩니다' → '…돼요'
  if (s.endsWith("됩니다")) return `${s.slice(0, -3)}돼요`;
  // '…합니다' → '…해요'
  if (s.endsWith("합니다")) return `${s.slice(0, -3)}해요`;
  // '…입니다' → 앞 글자 받침에 따라 '…이에요' / '…예요'
  if (s.endsWith("입니다")) {
    const stem = s.slice(0, -3);
    const prev = stem.slice(-1);
    return prev && !hasBatchim(prev) ? `${stem}예요` : `${stem}이에요`;
  }
  // '…있습니다' · '…없습니다' · '…졌습니다' 등 받침 + 습니다 → '…어요'
  if (s.endsWith("습니다")) return `${s.slice(0, -3)}어요`;
  return s;
}

/**
 * 여러 문장 해설 → 문장마다 끝말을 해요체로 (Agent 의견 · 해설 본문).
 * 문장 끝 = 한글 음절 바로 뒤의 마침표(·!·?) 또는 줄 끝. 소수점 · 수치 표식([[fig:…]]) · 문장 가운데는 그대로 둔다.
 */
export function toPoliteText(text: string): string {
  if (!text) return text;
  return text
    .split("\n")
    .map((line) => line.replace(/([가-힣]+)(?=[.!?](?:\s|$))/g, (w) => politeEnding(w)).replace(/([가-힣]+)\s*$/, (w) => politeEnding(w)))
    .join("\n");
}
/** 결론 한 문장 → 해요체 + 마침표 */
export function toPoliteSentence(text: string): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (!t) return t;
  const body = t.replace(/[.!?。]+$/, "");
  return `${politeEnding(body)}.`;
}

/**
 * 화면 조각(글자 · 배열 · 요소)의 글자만 해요체로 — 그래프 설명처럼 ReactNode 로 받는 Agent 해설용.
 * 요소는 children 만 따라 내려가고 다른 속성은 그대로 둔다. 수치 표식이 든 RichText 는 text 속성을 바꾼다.
 */
export function politeNode(node: ReactNode): ReactNode {
  const walk = (n: ReactNode): ReactNode => {
    if (typeof n === "string") return toPoliteText(n);
    if (Array.isArray(n)) return n.map(walk);
    if (isValidElement(n)) {
      const props = n.props as { children?: ReactNode; text?: unknown };
      const next: Record<string, unknown> = {};
      if (typeof props.text === "string") next.text = toPoliteText(props.text);
      if (props.children !== undefined) next.children = walk(props.children);
      return Object.keys(next).length ? cloneElement(n, next) : n;
    }
    return n;
  };
  return walk(node);
}
