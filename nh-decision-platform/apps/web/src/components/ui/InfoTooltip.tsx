"use client";

import { useRef, useState } from "react";
import { FloatingTip } from "@/components/ui/FloatingTip";
import { IconInfoCircle } from "@/components/ui/icons";

/**
 * ⓘ 아이콘 + 호버 툴팁.
 * 지표 제목 옆에 두고 산출 기준을 짧게 설명한다. 상자는 카드 밖(문서 맨 위)에 그려 잘리지 않는다.
 */
export function InfoTooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);

  return (
    <span className="relative inline-flex items-center">
      <button
        ref={anchor}
        type="button"
        aria-label="산출 기준 보기"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
        className="flex items-center text-icon hover:text-steel focus:outline-none"
      >
        <IconInfoCircle className="text-icon" />
      </button>
      <FloatingTip anchor={anchor} open={show} width={240} align="center" className="block rounded-lg border border-hairline-soft bg-canvas p-3 text-left font-normal shadow-tooltip">
        <span className="block text-[11.5px] leading-snug text-ink [word-break:keep-all]">{text}</span>
      </FloatingTip>
    </span>
  );
}
