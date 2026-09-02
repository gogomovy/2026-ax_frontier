import type { Article, DecisionDocument, PolicyDocument } from "@prisma/client";
import type { SectorId } from "./domain/constants.ts";

export type VersionDto = {
  versionNo: number;
  extractedText: string;
  summary: string;
  createdAt: string;
};

export type PolicyDto = {
  id: string;
  title: string;
  agency: string;
  policyOrAsOfDate: string;
  registeredAt: string;
  sectors: SectorId[];
  tags: string[];
  currentVersion: VersionDto;
};

export type DecisionDto = {
  id: string;
  title: string;
  meetingOrSource: string;
  decisionDate: string;
  registeredAt: string;
  sectors: SectorId[];
  tags: string[];
  currentVersion: VersionDto;
};

export type ArticleDto = {
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

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function toVersion(version: {
  versionNo: number;
  extractedText: string;
  summary: string;
  createdAt: Date;
}): VersionDto {
  return {
    versionNo: version.versionNo,
    extractedText: version.extractedText,
    summary: version.summary,
    createdAt: version.createdAt.toISOString(),
  };
}

export function toPolicyDto(
  doc: PolicyDocument & { versions: { versionNo: number; extractedText: string; summary: string; createdAt: Date }[] },
): PolicyDto {
  const current = [...doc.versions].sort((a, b) => b.versionNo - a.versionNo)[0];
  if (!current) {
    throw new Error("policy_has_no_version");
  }
  return {
    id: doc.id,
    title: doc.title,
    agency: doc.agency,
    policyOrAsOfDate: isoDate(doc.policyOrAsOfDate),
    registeredAt: doc.registeredAt.toISOString(),
    sectors: doc.sectors as SectorId[],
    tags: doc.tags,
    currentVersion: toVersion(current),
  };
}

export function toDecisionDto(
  doc: DecisionDocument & { versions: { versionNo: number; extractedText: string; summary: string; createdAt: Date }[] },
): DecisionDto {
  const current = [...doc.versions].sort((a, b) => b.versionNo - a.versionNo)[0];
  if (!current) {
    throw new Error("decision_has_no_version");
  }
  return {
    id: doc.id,
    title: doc.title,
    meetingOrSource: doc.meetingOrSource,
    decisionDate: isoDate(doc.decisionDate),
    registeredAt: doc.registeredAt.toISOString(),
    sectors: doc.sectors as SectorId[],
    tags: doc.tags,
    currentVersion: toVersion(current),
  };
}

export function toArticleDto(article: Article): ArticleDto {
  return {
    id: article.id,
    title: article.title,
    url: article.url,
    hasFile: Boolean(article.fileRelPath),
    source: article.source as ArticleDto["source"],
    confirmed: article.confirmed,
    confirmedAt: article.confirmedAt ? article.confirmedAt.toISOString() : null,
    sectors: article.sectors as SectorId[],
    tags: article.tags,
    summary: article.summary,
  };
}
