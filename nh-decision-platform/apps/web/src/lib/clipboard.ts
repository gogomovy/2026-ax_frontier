/** 클립보드 복사 — HTTPS 가 아닌 사내 주소(http://서버)에서는 navigator.clipboard 가 없어 임시 입력칸으로 대신한다. 성공 여부를 돌려준다. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* 권한 거부 등 — 아래 대체 방법 */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    document.body.appendChild(ta);
    const prev = document.activeElement as HTMLElement | null;
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    prev?.focus?.();
    return ok;
  } catch {
    return false;
  }
}
