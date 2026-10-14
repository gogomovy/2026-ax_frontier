/**
 * 삭제로 내용이 복사돼 남은 곳까지 정리한 결과 — 호출 기록 · 노드 입출력 · 보고서 근거 · 옛 산출물 세대 (DEL-13~15)
 * 서버 DeleteResult.scrubbed 와 같은 키.
 */
export interface Scrubbed {
  llmCalls?: number;
  nodeRuns?: number;
  evidenceRemoved?: number;
  generationsRemoved?: number;
}

/** 삭제 완료 알림에 덧붙일 문장 — 정리한 것이 없으면 빈 문자열 */
export function scrubText(s?: Scrubbed | null): string {
  if (!s) return "";
  const parts = [
    s.llmCalls ? `AI 호출 기록 ${s.llmCalls}건` : "",
    s.nodeRuns ? `실행 기록 ${s.nodeRuns}건` : "",
    s.evidenceRemoved ? `보고서 근거 ${s.evidenceRemoved}건` : "",
    s.generationsRemoved ? `옛 산출물 세대 ${s.generationsRemoved}건` : "",
  ].filter(Boolean);
  return parts.length ? ` · 복사돼 남은 내용 정리: ${parts.join(", ")}` : "";
}