"use client";

import { useEffect, useRef, useState } from "react";

/** 중간에 보이는 숫자 칸 수 — 최종 값까지 6번 바뀐다 */
const STEPS = 6;
/** 칸마다 머무는 시간(ms) — 뒤로 갈수록 조금씩 느려지며 멈춘다(합 약 0.39초) */
const DELAYS = [45, 50, 55, 65, 80, 95];
/** 감속 곡선 — 앞 칸은 크게, 뒤 칸은 작게 다가간다 */
const easeOut = (t: number) => 1 - Math.pow(1 - t, 2);

/** 화면에 쓰인 숫자 글자에서 소수 자릿수 — '66.3' → 1, '21,865' → 0 (호환용) */
export function decimalsOf(text: string): number {
  const m = /\.(\d+)/.exec(text);
  return m ? m[1].length : 0;
}

/**
 * 큰 숫자 롤링 — 0(값이 바뀐 경우엔 이전 값)에서 최종 값까지, 중간 숫자 6개를 짧게 거쳐 멈춘다.
 * 중간 값이 최종 값의 약 27% · 49% · 67% · 82% · 92% · 98% 라서 모든 자리가 함께 바뀐다.
 * 예: 66.3% → 17.9 · 32.5 · 44.4 · 54.1 · 60.9 · 64.9 → 66.3
 * - 서버 렌더 · 첫 그림에는 최종 값이 그대로 있다(인쇄 · 화면 낭독 · 스크립트 없음에서도 맞는 숫자).
 * - '동작 줄이기' 설정이면 돌지 않는다.
 * 상태는 타이머 콜백 안에서만 바꾼다(효과 본문에서 바로 바꾸지 않음).
 */
export function useRollingNumber(target: number | null | undefined, _decimals?: number): number | null {
  const final = target ?? null;
  const [rolling, setRolling] = useState<number | null>(null);
  const last = useRef<number | null>(null);

  useEffect(() => {
    if (final === null || last.current === final) return;
    const start = last.current ?? 0;
    last.current = final;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const frames = Array.from({ length: STEPS }, (_, i) => start + (final - start) * easeOut((i + 1) / (STEPS + 1)));
    const timers: number[] = [];
    let at = 0;
    frames.forEach((v, i) => {
      timers.push(window.setTimeout(() => setRolling(v), at));
      at += DELAYS[i] ?? DELAYS[DELAYS.length - 1];
    });
    timers.push(window.setTimeout(() => setRolling(null), at));
    let done = false;
    timers.push(window.setTimeout(() => (done = true), at));
    return () => {
      timers.forEach((t) => window.clearTimeout(t));
      // 끝나기 전에 정리되면(개발 모드의 두 번 실행 · 화면 전환) 다음 실행이 다시 돌 수 있게 시작 값을 되돌린다.
      // 이게 없으면 값이 그대로인 화면(데이터 분석의 Agent 해설 숫자 등)에서는 롤링이 건너뛰어졌다.
      if (!done) last.current = start === 0 && final !== 0 ? null : start;
    };
  }, [final]);

  return final === null ? null : (rolling ?? final);
}
