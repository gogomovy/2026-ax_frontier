import path from "node:path";
import {
  ALLOWED_EXTENSIONS,
  type AllowedExtension,
  type EvidenceKind,
  EVIDENCE_KINDS,
  MAX_UPLOAD_BYTES,
  SECTOR_IDS,
  type SectorId,
  SUMMARY_INITIAL_CHARS,
  SUMMARY_MAX_CHARS,
} from "./constants.ts";

export type EvidenceRef = {
  evidenceId: string;
  kind: EvidenceKind;
  targetId: string;
};

export type RelatedItem = {
  kind: EvidenceKind;
  sectors: SectorId[];
  tags: string[];
  confirmed?: boolean;
};

export function isSectorId(value: string): value is SectorId {
  return (SECTOR_IDS as readonly string[]).includes(value);
}

export function parseSectors(raw: string): SectorId[] {
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter(isSectorId);
}

export function parseTags(raw: string): string[] {
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

export function isEvidenceKind(value: string): value is EvidenceKind {
  return (EVIDENCE_KINDS as readonly string[]).includes(value);
}

export function parseEvidenceRef(value: unknown): EvidenceRef | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const record = value as Record<string, unknown>;
  if (typeof record.evidenceId !== "string" || record.evidenceId.length === 0) {
    return null;
  }
  if (typeof record.kind !== "string" || !isEvidenceKind(record.kind)) {
    return null;
  }
  if (typeof record.targetId !== "string" || record.targetId.length === 0) {
    return null;
  }
  return {
    evidenceId: record.evidenceId,
    kind: record.kind,
    targetId: record.targetId,
  };
}

export function serializeEvidenceRef(ref: EvidenceRef): string {
  return JSON.stringify({
    evidenceId: ref.evidenceId,
    kind: ref.kind,
    targetId: ref.targetId,
  });
}

export function deserializeEvidenceRef(json: string): EvidenceRef | null {
  try {
    return parseEvidenceRef(JSON.parse(json) as unknown);
  } catch {
    return null;
  }
}

export function hostnameFromUrl(url: string): string | null {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
}

export function isHostAllowed(hostname: string, allowedHosts: readonly string[]): boolean {
  const host = hostname.toLowerCase();
  return allowedHosts.some((allowed) => {
    const a = allowed.toLowerCase();
    return host === a || host.endsWith(`.${a}`);
  });
}

export function isUrlHostAllowed(url: string, allowedHosts: readonly string[]): boolean {
  const host = hostnameFromUrl(url);
  if (host === null) {
    return false;
  }
  return isHostAllowed(host, allowedHosts);
}

export function matchesRelated(item: RelatedItem, sector: SectorId, tags: string[]): boolean {
  if (item.kind === "article" && item.confirmed !== true) {
    return false;
  }
  if (!item.sectors.includes(sector)) {
    return false;
  }
  if (tags.length === 0) {
    return true;
  }
  return tags.some((tag) => item.tags.includes(tag));
}

export function sliceSummary(extractedText: string): string {
  return clampSummary(extractedText.slice(0, SUMMARY_INITIAL_CHARS));
}

export function clampSummary(summary: string): string {
  return summary.slice(0, SUMMARY_MAX_CHARS);
}

export function extensionOf(filename: string): string {
  return path.extname(filename).replace(".", "").toLowerCase();
}

export function isAllowedExtension(ext: string): ext is AllowedExtension {
  return (ALLOWED_EXTENSIONS as readonly string[]).includes(ext);
}

export function isAllowedUploadSize(byteLength: number): boolean {
  return byteLength > 0 && byteLength <= MAX_UPLOAD_BYTES;
}

export function isPathInside(rootDir: string, targetPath: string): boolean {
  const root = path.resolve(rootDir);
  const target = path.resolve(targetPath);
  const relative = path.relative(root, target);
  if (relative === "") {
    return false;
  }
  return !relative.startsWith("..") && !path.isAbsolute(relative);
}

export function diskFileName(versionNo: number, ext: AllowedExtension): string {
  return `${versionNo}.${ext}`;
}

export function isDuplicateHost(existing: readonly string[], host: string): boolean {
  const normalized = normalizeHost(host);
  return existing.some((item) => normalizeHost(item) === normalized);
}

export function normalizeHost(host: string): string {
  return host.trim().toLowerCase().replace(/^https?:\/\//, "").split("/")[0] ?? "";
}
