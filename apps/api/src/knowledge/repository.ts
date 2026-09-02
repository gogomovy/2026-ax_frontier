import { prisma } from "../prisma.ts";
import { isSectorId, matchesRelated, type SectorId } from "./domain/rules.ts";
import { toArticleDto, toDecisionDto, toPolicyDto } from "./dto.ts";

const versionInclude = { versions: true } as const;

export const knowledgeRepository = {
  listPolicies: async () => {
    const rows = await prisma.policyDocument.findMany({ include: versionInclude, orderBy: { registeredAt: "desc" } });
    return rows.map(toPolicyDto);
  },

  getPolicy: async (id: string) => {
    const row = await prisma.policyDocument.findUnique({ where: { id }, include: versionInclude });
    return row ? toPolicyDto(row) : null;
  },

  createPolicy: async (data: {
    title: string;
    agency: string;
    policyOrAsOfDate: Date;
    sectors: string[];
    tags: string[];
    fileRelPath: string;
    extractedText: string;
    summary: string;
  }) => {
    const row = await prisma.policyDocument.create({
      data: {
        title: data.title,
        agency: data.agency,
        policyOrAsOfDate: data.policyOrAsOfDate,
        sectors: data.sectors,
        tags: data.tags,
        versions: {
          create: {
            versionNo: 1,
            fileRelPath: data.fileRelPath,
            extractedText: data.extractedText,
            summary: data.summary,
          },
        },
      },
      include: versionInclude,
    });
    return toPolicyDto(row);
  },

  addPolicyVersion: async (
    id: string,
    data: { fileRelPath: string; extractedText: string; summary: string },
  ) => {
    const existing = await prisma.policyDocument.findUnique({ where: { id }, include: versionInclude });
    if (!existing) {
      return null;
    }
    const versionNo = Math.max(...existing.versions.map((v) => v.versionNo)) + 1;
    await prisma.policyVersion.create({
      data: {
        documentId: id,
        versionNo,
        fileRelPath: data.fileRelPath,
        extractedText: data.extractedText,
        summary: data.summary,
      },
    });
    const row = await prisma.policyDocument.findUnique({ where: { id }, include: versionInclude });
    return row ? toPolicyDto(row) : null;
  },

  updatePolicySummary: async (id: string, summary: string) => {
    const existing = await prisma.policyDocument.findUnique({ where: { id }, include: versionInclude });
    if (!existing) {
      return null;
    }
    const current = [...existing.versions].sort((a, b) => b.versionNo - a.versionNo)[0];
    if (!current) {
      return null;
    }
    await prisma.policyVersion.update({ where: { id: current.id }, data: { summary } });
    const row = await prisma.policyDocument.findUnique({ where: { id }, include: versionInclude });
    return row ? toPolicyDto(row) : null;
  },

  getPolicyFilePath: async (id: string) => {
    const row = await prisma.policyDocument.findUnique({ where: { id }, include: versionInclude });
    if (!row) {
      return null;
    }
    const current = [...row.versions].sort((a, b) => b.versionNo - a.versionNo)[0];
    return current?.fileRelPath ?? null;
  },

  listDecisions: async () => {
    const rows = await prisma.decisionDocument.findMany({ include: versionInclude, orderBy: { registeredAt: "desc" } });
    return rows.map(toDecisionDto);
  },

  getDecision: async (id: string) => {
    const row = await prisma.decisionDocument.findUnique({ where: { id }, include: versionInclude });
    return row ? toDecisionDto(row) : null;
  },

  createDecision: async (data: {
    title: string;
    meetingOrSource: string;
    decisionDate: Date;
    sectors: string[];
    tags: string[];
    fileRelPath: string;
    extractedText: string;
    summary: string;
  }) => {
    const row = await prisma.decisionDocument.create({
      data: {
        title: data.title,
        meetingOrSource: data.meetingOrSource,
        decisionDate: data.decisionDate,
        sectors: data.sectors,
        tags: data.tags,
        versions: {
          create: {
            versionNo: 1,
            fileRelPath: data.fileRelPath,
            extractedText: data.extractedText,
            summary: data.summary,
          },
        },
      },
      include: versionInclude,
    });
    return toDecisionDto(row);
  },

  addDecisionVersion: async (
    id: string,
    data: { fileRelPath: string; extractedText: string; summary: string },
  ) => {
    const existing = await prisma.decisionDocument.findUnique({ where: { id }, include: versionInclude });
    if (!existing) {
      return null;
    }
    const versionNo = Math.max(...existing.versions.map((v) => v.versionNo)) + 1;
    await prisma.decisionVersion.create({
      data: {
        documentId: id,
        versionNo,
        fileRelPath: data.fileRelPath,
        extractedText: data.extractedText,
        summary: data.summary,
      },
    });
    const row = await prisma.decisionDocument.findUnique({ where: { id }, include: versionInclude });
    return row ? toDecisionDto(row) : null;
  },

  updateDecisionSummary: async (id: string, summary: string) => {
    const existing = await prisma.decisionDocument.findUnique({ where: { id }, include: versionInclude });
    if (!existing) {
      return null;
    }
    const current = [...existing.versions].sort((a, b) => b.versionNo - a.versionNo)[0];
    if (!current) {
      return null;
    }
    await prisma.decisionVersion.update({ where: { id: current.id }, data: { summary } });
    const row = await prisma.decisionDocument.findUnique({ where: { id }, include: versionInclude });
    return row ? toDecisionDto(row) : null;
  },

  getDecisionFilePath: async (id: string) => {
    const row = await prisma.decisionDocument.findUnique({ where: { id }, include: versionInclude });
    if (!row) {
      return null;
    }
    const current = [...row.versions].sort((a, b) => b.versionNo - a.versionNo)[0];
    return current?.fileRelPath ?? null;
  },

  listArticles: async (confirmed?: boolean) => {
    const rows = await prisma.article.findMany({
      where: confirmed === undefined ? undefined : { confirmed },
      orderBy: { title: "asc" },
    });
    return rows.map(toArticleDto);
  },

  getArticle: async (id: string) => {
    const row = await prisma.article.findUnique({ where: { id } });
    return row ? toArticleDto(row) : null;
  },

  createArticle: async (data: {
    title: string;
    url: string | null;
    fileRelPath: string | null;
    source: "seed" | "direct" | "official_search";
    confirmed: boolean;
    confirmedAt: Date | null;
    sectors: string[];
    tags: string[];
    summary: string | null;
  }) => {
    const row = await prisma.article.create({ data });
    return toArticleDto(row);
  },

  setArticleConfirmed: async (id: string, confirmed: boolean) => {
    const row = await prisma.article.update({
      where: { id },
      data: { confirmed, confirmedAt: confirmed ? new Date() : null },
    });
    return toArticleDto(row);
  },

  listDomains: async () => prisma.officialDomain.findMany({ orderBy: { host: "asc" } }),

  addDomain: async (host: string) => prisma.officialDomain.create({ data: { host, enabled: true } }),

  deleteDomain: async (id: string) => {
    await prisma.officialDomain.delete({ where: { id } });
  },

  enabledHosts: async () => {
    const rows = await prisma.officialDomain.findMany({ where: { enabled: true } });
    return rows.map((row) => row.host);
  },

  listRelated: async (sector: SectorId, tags: string[]) => {
    const [policies, decisions, articles] = await Promise.all([
      prisma.policyDocument.findMany({ include: versionInclude }),
      prisma.decisionDocument.findMany({ include: versionInclude }),
      prisma.article.findMany(),
    ]);
    const policyHits = policies
      .filter((row) =>
        matchesRelated(
          { kind: "policy", sectors: row.sectors.filter(isSectorId), tags: row.tags },
          sector,
          tags,
        ),
      )
      .map(toPolicyDto);
    const decisionHits = decisions
      .filter((row) =>
        matchesRelated(
          { kind: "decision", sectors: row.sectors.filter(isSectorId), tags: row.tags },
          sector,
          tags,
        ),
      )
      .map(toDecisionDto);
    const articleHits = articles
      .filter((row) =>
        matchesRelated(
          {
            kind: "article",
            sectors: row.sectors.filter(isSectorId),
            tags: row.tags,
            confirmed: row.confirmed,
          },
          sector,
          tags,
        ),
      )
      .map(toArticleDto);
    return { policies: policyHits, decisions: decisionHits, articles: articleHits };
  },
};
