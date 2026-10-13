import { IconAlertCircle } from "@/components/ui/icons";
import { LinkButton } from "@/components/ui/primitives";

/** 존재하지 않는 경로 — 모든 사용자가 갈 수 있는 '내 첫 화면'(/ → 역할별 첫 화면)으로 안내 (Phase E · NAV-03) */
export default function NotFound() {
  return (
    <div className="shell flex min-h-[60vh] flex-col items-center justify-center py-10 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-circle bg-track text-steel">
        <IconAlertCircle />
      </span>
      <p className="mt-5 text-[12px] font-bold text-steel">404</p>
      <h1 className="mt-1 text-[24px] font-bold leading-[1.25] text-ink-deep">찾는 화면이 없습니다</h1>
      <p className="mt-2 max-w-[440px] text-[14px] leading-normal text-steel">
        주소가 바뀌었거나 일 단위로 다시 만드는 분석 탭이 교체되었을 수 있어요. 이전 분석은 각 분석 화면의 ‘이전 분석’에서 볼 수 있어요.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-xs">
        <LinkButton href="/">내 첫 화면으로</LinkButton>
        <LinkButton href="/knowledge" variant="ghost">
          데이터베이스
        </LinkButton>
      </div>
    </div>
  );
}
