"use client";

import Image from "next/image";
import Link from "next/link";

/**
 * NH NAVI 브랜드 마크 (목업 전용 미리보기).
 * 가로형 로고 이미지(public/nh-navi-logo.png, 원본 686×160)를 그대로 쓴다.
 */
export function NaviBrand({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex shrink-0 items-center pr-[14px]" aria-label="NH NAVI 홈">
      <Image
        src="/nh-navi-logo.png"
        alt="NH NAVI"
        width={686}
        height={160}
        priority
        unoptimized
        className="h-7 w-auto"
      />
    </Link>
  );
}
