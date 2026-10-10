/** 화면 데이터 대기 (B.32) — 서버 컴포넌트가 백엔드 응답을 기다리는 동안 */
export default function Loading() {
  return (
    <div className="shell flex min-h-[40vh] items-center justify-center" role="status" aria-live="polite">
      <span className="inline-flex items-center gap-2 text-[13px] text-steel">
        <span aria-hidden className="h-3 w-3 animate-spin rounded-full border-2 border-hairline-soft border-t-primary" />
        불러오는 중…
      </span>
    </div>
  );
}
