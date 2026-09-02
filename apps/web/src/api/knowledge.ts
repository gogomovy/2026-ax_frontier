import type {
  Article,
  DecisionDocument,
  Evidence,
  EvidenceKind,
  OfficialDomain,
  PolicyDocument,
  SearchResponse,
} from "../types/knowledge";
import type { SectorId } from "../sectors";

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { error?: string };
    if (typeof body.error === "string" && body.error.length > 0) {
      return body.error;
    }
  } catch {
    /* 본문이 JSON이 아니면 상태 문구만 쓴다 */
  }
  return res.statusText || `HTTP ${res.status}`;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return (await res.json()) as T;
}

export const knowledgeApi = {
  listPolicies: () => getJson<PolicyDocument[]>("/api/knowledge/policies"),

  getPolicy: (id: string) => getJson<PolicyDocument>(`/api/knowledge/policies/${id}`),

  uploadPolicy: (form: FormData) =>
    fetch("/api/knowledge/policies", { method: "POST", body: form }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
      return (await res.json()) as PolicyDocument;
    }),

  addPolicyVersion: (id: string, form: FormData) =>
    fetch(`/api/knowledge/policies/${id}/versions`, { method: "POST", body: form }).then(
      async (res) => {
        if (!res.ok) {
          throw new Error(await readError(res));
        }
        return (await res.json()) as PolicyDocument;
      },
    ),

  patchPolicySummary: (id: string, summary: string) =>
    fetch(`/api/knowledge/policies/${id}/summary`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ summary }),
    }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
      return (await res.json()) as PolicyDocument;
    }),

  policyFileUrl: (id: string) => `/api/knowledge/policies/${id}/file`,

  listDecisions: () => getJson<DecisionDocument[]>("/api/knowledge/decisions"),

  getDecision: (id: string) => getJson<DecisionDocument>(`/api/knowledge/decisions/${id}`),

  uploadDecision: (form: FormData) =>
    fetch("/api/knowledge/decisions", { method: "POST", body: form }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
      return (await res.json()) as DecisionDocument;
    }),

  addDecisionVersion: (id: string, form: FormData) =>
    fetch(`/api/knowledge/decisions/${id}/versions`, { method: "POST", body: form }).then(
      async (res) => {
        if (!res.ok) {
          throw new Error(await readError(res));
        }
        return (await res.json()) as DecisionDocument;
      },
    ),

  patchDecisionSummary: (id: string, summary: string) =>
    fetch(`/api/knowledge/decisions/${id}/summary`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ summary }),
    }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
      return (await res.json()) as DecisionDocument;
    }),

  decisionFileUrl: (id: string) => `/api/knowledge/decisions/${id}/file`,

  getEvidence: (kind: EvidenceKind, targetId: string) =>
    getJson<Evidence>(`/api/knowledge/evidence/${kind}/${targetId}`),

  searchOfficial: (q: string) =>
    getJson<SearchResponse>(`/api/knowledge/search?q=${encodeURIComponent(q)}`),

  addSearchCandidate: (hit: { title: string; url: string; sectors: SectorId[]; tags: string[] }) =>
    fetch("/api/knowledge/search/candidates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(hit),
    }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
      return (await res.json()) as Article;
    }),

  listArticles: (confirmed?: boolean) => {
    const query = confirmed === undefined ? "" : `?confirmed=${String(confirmed)}`;
    return getJson<Article[]>(`/api/knowledge/articles${query}`);
  },

  registerArticle: (form: FormData) =>
    fetch("/api/knowledge/articles", { method: "POST", body: form }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
      return (await res.json()) as Article;
    }),

  confirmArticle: (id: string) =>
    fetch(`/api/knowledge/articles/${id}/confirm`, { method: "POST" }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
      return (await res.json()) as Article;
    }),

  unconfirmArticle: (id: string) =>
    fetch(`/api/knowledge/articles/${id}/unconfirm`, { method: "POST" }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
      return (await res.json()) as Article;
    }),

  listDomains: () => getJson<OfficialDomain[]>("/api/knowledge/domains"),

  addDomain: (host: string) =>
    fetch("/api/knowledge/domains", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host }),
    }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
      return (await res.json()) as OfficialDomain;
    }),

  deleteDomain: (id: string) =>
    fetch(`/api/knowledge/domains/${id}`, { method: "DELETE" }).then(async (res) => {
      if (!res.ok) {
        throw new Error(await readError(res));
      }
    }),
};
