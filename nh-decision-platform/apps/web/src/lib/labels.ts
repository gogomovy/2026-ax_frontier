/**
 * 화면 표기 (Phase E · TXT-01 · Q125) — 실행 · 품질 상태 코드를 업무 한국어로. 코드는 보조 글씨(title)로만.
 */
const RUN: Record<string, string> = {
  succeeded: "성공",
  success: "성공",
  ok: "정상",
  degraded: "축소 동작",
  failed: "실패",
  error: "실패",
  running: "실행 중",
  in_progress: "실행 중",
  queued: "대기",
  pending: "대기",
  approval: "승인 대기",
  done: "완료",
  skipped: "건너뜀",
  cancelled: "취소",
};
const QUALITY: Record<string, string> = { passed: "통과", warning: "주의", failed: "실패", rejected: "실패", committed: "확정" };

/** 실행 상태(워크플로 · 노드 · 작업) */
export function runStatusLabel(code: string | null | undefined): string {
  if (!code) return "-";
  return RUN[code] ?? code;
}

/** 품질 검사 · 버전 상태 */
export function qualityLabel(code: string | null | undefined): string {
  if (!code) return "-";
  return QUALITY[code] ?? RUN[code] ?? code;
}

/** 관리 화면 상태 배지의 기본 표기 — 실행 · 버전 · 사용 상태를 한 표로. 모르는 코드는 그대로 */
const STATUS: Record<string, string> = {
  ...RUN,
  passed: "통과",
  warning: "주의",
  committed: "확정",
  staged: "확정 전",
  rolled_back: "되돌림",
  deleted: "삭제됨",
  rejected: "반려",
  approved: "승인",
  superseded: "대체됨",
  active: "사용",
  disabled: "중지",
  locked: "잠김",
  paused: "일시 중지",
  retired: "폐기",
  partial: "일부",
  extracted: "추출됨",
  ingested: "적재됨",
  open: "열림",
  accepted: "수락",
};

export function statusLabel(code: string | null | undefined): string {
  if (!code) return "-";
  return STATUS[code] ?? code;
}
