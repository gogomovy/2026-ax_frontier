/**
 * '봤음' 기록 (Phase K · DOT-01 · Q152) — 레드닷 · 정보성 건수는 확인하지 않은 새 내용이 있을 때만 보인다.
 *
 * 점마다 '내용 서명'(이슈 id · 판정 · 기준일 · 생성 시각을 이은 문자열)을 만들고, 사용자가 그 탭 · 화면을 열면
 * `localStorage["nhdip.seen.<사번>"]` 에 {키: 서명} 으로 남긴다. 서명이 같으면 숨기고, 내용이 바뀌면(새 이슈 · 새 기준일) 다시 보인다.
 * 탭 · 창 사이는 storage 이벤트로 맞춘다. 서버 렌더에서는 점을 그리지 않는다(기록을 모르므로).
 */
const PREFIX = "nhdip.seen.";
const EVENT = "nhdip:seen";
const MAX_KEYS = 500;

type SeenMap = Record<string, string>;

const storageKey = (emp: string | null | undefined) => `${PREFIX}${emp || "anon"}`;

let cacheRaw: string | null | undefined;
let cacheKey = "";
let cacheMap: SeenMap = {};

/** 기록 읽기 — 같은 원문이면 같은 객체(useSyncExternalStore 스냅샷 안정) */
export function readSeen(emp: string | null | undefined): SeenMap {
  const k = storageKey(emp);
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(k);
  } catch {
    raw = null;
  }
  if (raw === cacheRaw && k === cacheKey) return cacheMap;
  cacheRaw = raw;
  cacheKey = k;
  try {
    const v = raw ? JSON.parse(raw) : {};
    cacheMap = v && typeof v === "object" && !Array.isArray(v) ? (v as SeenMap) : {};
  } catch {
    cacheMap = {};
  }
  return cacheMap;
}

/** 열었음 — 서명을 남긴다(오래된 기록부터 정리) */
export function markSeen(emp: string | null | undefined, key: string, signature: string): void {
  if (!signature) return;
  const cur = readSeen(emp);
  if (cur[key] === signature) return;
  const next: SeenMap = { ...cur };
  delete next[key];
  next[key] = signature;
  const keys = Object.keys(next);
  for (const old of keys.slice(0, Math.max(0, keys.length - MAX_KEYS))) delete next[old];
  try {
    window.localStorage.setItem(storageKey(emp), JSON.stringify(next));
  } catch {
    return;
  }
  window.dispatchEvent(new Event(EVENT));
}

export function subscribeSeen(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT, onChange);
  };
}

/** 새것인가 — 서명이 없으면(내용 없음) 아니고, 기록이 없거나 다르면 새것. map 이 null(서버 렌더)이면 아니다 */
export function isFresh(map: SeenMap | null, key: string, signature: string | null | undefined): boolean {
  if (!signature || map === null) return false;
  return map[key] !== signature;
}

/** 서명 만들기 — 빈 값은 빼고 정렬해 순서가 달라도 같은 내용이면 같은 서명 */
export function signatureOf(parts: (string | number | null | undefined)[], base?: string | null): string {
  const items = parts.filter((p) => p !== null && p !== undefined && p !== "").map(String).sort();
  if (!items.length) return "";
  return `${base ?? ""}|${items.join(",")}`;
}

/** 분석 탭(동적 탭 · 맞춤 분석)의 '봤음' 키 · 서명 — 이슈 · 심각도 · 생성 시각이 바뀌면 새것 */
export function tabSeenKey(t: { tabKey: string; reportKey?: string }): string {
  return `tab.${t.reportKey ?? t.tabKey}`;
}
export function tabSignature(t: { insightId?: string; severity?: string; generatedAt?: string; asOf?: string }): string {
  if (!t.severity || t.severity === "ok" || t.severity === "normal") return "";
  return signatureOf([t.insightId, t.severity, t.generatedAt], t.asOf);
}
