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

/** 결론 한 문장 → 해요체 + 마침표 */
export function toPoliteSentence(text: string): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (!t) return t;
  const body = t.replace(/[.!?。]+$/, "");
  return `${politeEnding(body)}.`;
}
