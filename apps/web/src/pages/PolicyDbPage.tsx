import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { knowledgeApi } from "../api/knowledge";
import { ArticleCandidateList } from "../components/ArticleCandidateList";
import { ArticleDetail } from "../components/ArticleDetail";
import { ArticleDirectForm } from "../components/ArticleDirectForm";
import { OfficialSearchPanel } from "../components/OfficialSearchPanel";
import { PolicyDocumentDetail } from "../components/PolicyDocumentDetail";
import { PolicyDocumentList } from "../components/PolicyDocumentList";
import { PolicyUploadForm } from "../components/PolicyUploadForm";
import type { Article, OfficialDomain, PolicyDocument } from "../types/knowledge";

export function PolicyDbPage() {
  const { t } = useTranslation();
  const [policies, setPolicies] = useState<PolicyDocument[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [domains, setDomains] = useState<OfficialDomain[]>([]);
  const [candidates, setCandidates] = useState<Article[]>([]);
  const [confirmed, setConfirmed] = useState<Article[]>([]);
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null);
  const [articleSubmitting, setArticleSubmitting] = useState(false);

  const selected = policies.find((item) => item.id === selectedId) ?? null;
  const selectedArticle =
    candidates.find((item) => item.id === selectedArticleId) ??
    confirmed.find((item) => item.id === selectedArticleId) ??
    null;

  const loadLists = useCallback(async () => {
    try {
      const [nextPolicies, nextDomains, nextCandidates, nextConfirmed] = await Promise.all([
        knowledgeApi.listPolicies(),
        knowledgeApi.listDomains(),
        knowledgeApi.listArticles(false),
        knowledgeApi.listArticles(true),
      ]);
      setPolicies(nextPolicies);
      setDomains(nextDomains);
      setCandidates(nextCandidates);
      setConfirmed(nextConfirmed);
      setListError(null);
    } catch (caught) {
      setListError(caught instanceof Error ? caught.message : t("list.error"));
    }
  }, [t]);

  useEffect(() => {
    void loadLists();
  }, [loadLists]);

  return (
    <section>
      <p className="page-kicker">
        <Link to="/" data-testid="policy-page-home-link">
          {t("nav.home")}
        </Link>
      </p>
      <h1>{t("policy.title")}</h1>
      {listError ? (
        <p className="error" data-testid="policy-list-error">
          {listError}
        </p>
      ) : null}
      <div className="layout-split">
        <div className="panel">
          <PolicyDocumentList items={policies} selectedId={selectedId} onSelect={setSelectedId} />
        </div>
        <div className="panel">
          {selected ? (
            <PolicyDocumentDetail
              document={selected}
              onUpdated={(next) => {
                setPolicies((current) => current.map((item) => (item.id === next.id ? next : item)));
              }}
            />
          ) : (
            <p>{t("list.empty")}</p>
          )}
        </div>
      </div>
      <section className="panel">
        <PolicyUploadForm
          submitting={uploading}
          onSubmit={async (form) => {
            setUploading(true);
            try {
              const created = await knowledgeApi.uploadPolicy(form);
              setPolicies((current) => [created, ...current]);
              setSelectedId(created.id);
            } finally {
              setUploading(false);
            }
          }}
        />
      </section>
      <OfficialSearchPanel
        domains={domains}
        onDomainsChange={loadLists}
        onCandidateAdded={loadLists}
      />
      <section className="panel">
        <ArticleCandidateList
          items={candidates}
          selectedId={selectedArticleId}
          onSelect={setSelectedArticleId}
        />
        <h3>{t("articles.confirmed")}</h3>
        <ul className="doc-list" data-testid="article-confirmed-list">
          {confirmed.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                data-testid={`article-confirmed-${item.id}`}
                aria-current={item.id === selectedArticleId}
                onClick={() => setSelectedArticleId(item.id)}
              >
                {item.title}
              </button>
            </li>
          ))}
        </ul>
        {selectedArticle ? (
          <ArticleDetail
            article={selectedArticle}
            onConfirm={async (id) => {
              await knowledgeApi.confirmArticle(id);
              await loadLists();
            }}
            onUnconfirm={async (id) => {
              await knowledgeApi.unconfirmArticle(id);
              await loadLists();
            }}
          />
        ) : null}
        <ArticleDirectForm
          submitting={articleSubmitting}
          onSubmit={async (form) => {
            setArticleSubmitting(true);
            try {
              await knowledgeApi.registerArticle(form);
              await loadLists();
            } finally {
              setArticleSubmitting(false);
            }
          }}
        />
      </section>
    </section>
  );
}
