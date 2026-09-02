import type { SectorId } from "../sectors";

export type EvidenceKind = "policy" | "decision" | "article";

export type DocumentVersion = {
  versionNo: number;
  extractedText: string;
  summary: string;
  createdAt: string;
};

export type PolicyDocument = {
  id: string;
  title: string;
  agency: string;
  policyOrAsOfDate: string;
  registeredAt: string;
  sectors: SectorId[];
  tags: string[];
  currentVersion: DocumentVersion;
};

export type DecisionDocument = {
  id: string;
  title: string;
  meetingOrSource: string;
  decisionDate: string;
  registeredAt: string;
  sectors: SectorId[];
  tags: string[];
  currentVersion: DocumentVersion;
};

export type Article = {
  id: string;
  title: string;
  url: string | null;
  hasFile: boolean;
  source: "seed" | "direct" | "official_search";
  confirmed: boolean;
  confirmedAt: string | null;
  sectors: SectorId[];
  tags: string[];
  summary: string | null;
};

export type OfficialDomain = {
  id: string;
  host: string;
  enabled: boolean;
};

export type SearchHit = {
  title: string;
  url: string;
  excerpt: string;
  sourceHost: string;
};

export type SearchResponse = {
  hits: SearchHit[];
  error: string | null;
};

export type Evidence = {
  kind: EvidenceKind;
  targetId: string;
  title: string;
  source: string;
  date: string;
  summary: string;
  unconfirmed: boolean;
  downloadPath: string | null;
  url: string | null;
};
