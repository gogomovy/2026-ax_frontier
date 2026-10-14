"use client";

import { useUiConfig } from "@/components/providers/SessionProvider";
import { TONE_PROGRESS, bandOf, type BandKey } from "@/lib/uiConfig";
import { ProgressBar } from "./primitives";

/**
 * 판정 구간 색의 진행 막대 (Phase K · HC-01) — 경계 · 색은 관리자 [화면 설정 › 판정 구간].
 * 서버 컴포넌트 화면에서도 쓸 수 있도록 설정은 여기서 읽는다. 구간 설정이 없으면 기본(보라).
 */
export function BandProgress({ value, band, label }: { value: number; band: BandKey; label?: string }) {
  const cfg = useUiConfig();
  const b = bandOf(value, cfg.bands[band]);
  return <ProgressBar value={value} tone={b ? TONE_PROGRESS[b.tone] : "primary"} label={label} />;
}
