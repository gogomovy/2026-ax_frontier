"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSession } from "@/components/providers/SessionProvider";
import { api } from "@/lib/api-client";

/**
 * [데이터베이스] 머리말 — '자료 올리기'(화면 권한이 있는 사용자) · '승인할 자료 N' · '우리 부서 자료'(부서 데이터 책임자) (Phase C · UPL-01 · UPL-04 · DEL-09)
 */
export function UploadCta() {
  const { menu } = useSession();
  const allowed = (menu?.sections ?? []).some((s) => [...s.flow, ...s.reference].some((i) => i.href === "/knowledge/upload"));
  const steward = Boolean(menu?.user.dataSteward);
  const [pending, setPending] = useState<number | null>(null);
  // 에이전트 제안(분석 화면 · 추적 지표 · 개념 연결 · 부서 분석 요청) 중 처리할 것 — 서버 메뉴 건수(stewardTodo · §40 STW)
  const proposals = menu?.counts.stewardTodo ?? 0;
  useEffect(() => {
    if (!steward) return;
    let alive = true;
    api<{ counts: Record<string, number> }>("/db/uploads/review?status=pending")
      .then((r) => alive && setPending(r.counts.pending ?? 0))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [steward]);
  if (!allowed && !steward) return null;
  return (
    <>
      {steward ? (
        <>
          <Link href="/knowledge/upload?tab=review" className="inline-flex h-9 items-center gap-1.5 rounded-pill border border-hairline px-4 text-[13px] font-bold text-ink" data-steward-cta>
            승인할 자료
            {pending ? <span className="rounded-pill bg-attention-soft px-1.5 text-[11px] text-attention tnum">{pending}</span> : null}
          </Link>
          <Link href="/knowledge/upload?tab=proposals" className="inline-flex h-9 items-center gap-1.5 rounded-pill border border-hairline px-4 text-[13px] font-bold text-ink" data-steward-proposals-cta>
            에이전트 제안
            {proposals ? <span className="rounded-pill bg-attention-soft px-1.5 text-[11px] text-attention tnum">{proposals}</span> : null}
          </Link>
          {/* 우리 부서가 올려 반영된 자료를 보고 지우는 곳 (DEL-09) */}
          <Link href="/knowledge/upload?tab=data" className="inline-flex h-9 items-center rounded-pill border border-hairline px-4 text-[13px] font-bold text-ink" data-steward-data-cta>
            우리 부서 자료
          </Link>
        </>
      ) : null}
      {allowed ? (
        <Link href="/knowledge/upload" className="inline-flex h-9 items-center rounded-pill bg-ink-button px-4 text-[13px] font-bold text-on-ink-button" data-upload-cta>
          자료 올리기
        </Link>
      ) : null}
    </>
  );
}
