export const SECTOR_IDS = [
  "loan",
  "deposit",
  "pension",
  "wealth",
  "trust",
  "fx",
  "card",
] as const;

export type SectorId = (typeof SECTOR_IDS)[number];

export const EVIDENCE_KINDS = ["policy", "decision", "article"] as const;
export type EvidenceKind = (typeof EVIDENCE_KINDS)[number];

export const ALLOWED_EXTENSIONS = ["pdf", "txt", "hwp"] as const;
export type AllowedExtension = (typeof ALLOWED_EXTENSIONS)[number];

export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
export const SUMMARY_INITIAL_CHARS = 500;
export const SUMMARY_MAX_CHARS = 4000;
export const EXTRACT_TIMEOUT_MS = 30_000;
export const SEARCH_HOST_TIMEOUT_MS = 10_000;
export const SEARCH_TOTAL_TIMEOUT_MS = 30_000;
export const DEFAULT_OFFICIAL_HOSTS = ["fsc.go.kr", "fss.or.kr", "moef.go.kr"] as const;
