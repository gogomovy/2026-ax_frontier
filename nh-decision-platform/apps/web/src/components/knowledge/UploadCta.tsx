"use client";

import Link from "next/link";
import { useSession } from "@/components/providers/SessionProvider";

/** [데이터베이스] 머리말의 '자료 올리기' — 화면 권한(자료 올리기)이 있는 사용자에게만 (Phase C · UPL-01) */
export function UploadCta() {
  const { menu } = useSession();
  const allowed = (menu?.sections ?? []).some((s) => [...s.flow, ...s.reference].some((i) => i.href === "/knowledge/upload"));
  if (!allowed) return null;
  return (
    <Link href="/knowledge/upload" className="inline-flex h-9 items-center rounded-pill bg-ink-button px-4 text-[13px] font-bold text-on-ink-button" data-upload-cta>
      자료 올리기
    </Link>
  );
}
