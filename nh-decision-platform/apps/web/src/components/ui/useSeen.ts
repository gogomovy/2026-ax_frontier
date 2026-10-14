"use client";

import { useCallback, useSyncExternalStore } from "react";
import { useSession } from "@/components/providers/SessionProvider";
import { isFresh, markSeen, readSeen, subscribeSeen } from "@/lib/seen";

const serverSnapshot = () => null;

/**
 * 레드닷 '봤음' 상태 (Phase K · DOT-01) — `fresh(key, sig)` 가 참일 때만 점을 그리고, 열면 `mark(key, sig)`.
 * 사용자(사번)별로 기억한다.
 */
export function useSeen() {
  const { menu } = useSession();
  const emp = menu?.user.empNo ?? null;
  const read = useCallback(() => readSeen(emp), [emp]);
  const map = useSyncExternalStore(subscribeSeen, read, serverSnapshot);
  const fresh = useCallback((key: string, signature: string | null | undefined) => isFresh(map, key, signature), [map]);
  const mark = useCallback((key: string, signature: string | null | undefined) => {
    if (signature) markSeen(emp, key, signature);
  }, [emp]);
  return { fresh, mark };
}
