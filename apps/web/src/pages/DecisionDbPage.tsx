import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { knowledgeApi } from "../api/knowledge";
import { DecisionDocumentDetail } from "../components/DecisionDocumentDetail";
import { DecisionDocumentList } from "../components/DecisionDocumentList";
import { DecisionUploadForm } from "../components/DecisionUploadForm";
import type { DecisionDocument } from "../types/knowledge";

export function DecisionDbPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<DecisionDocument[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const selected = items.find((item) => item.id === selectedId) ?? null;

  const load = useCallback(async () => {
    try {
      const next = await knowledgeApi.listDecisions();
      setItems(next);
      setListError(null);
    } catch (caught) {
      setListError(caught instanceof Error ? caught.message : t("list.error"));
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section>
      <p className="page-kicker">
        <Link to="/" data-testid="decision-page-home-link">
          {t("nav.home")}
        </Link>
      </p>
      <h1>{t("decision.title")}</h1>
      {listError ? (
        <p className="error" data-testid="decision-list-error">
          {listError}
        </p>
      ) : null}
      <div className="layout-split">
        <div className="panel">
          <DecisionDocumentList items={items} selectedId={selectedId} onSelect={setSelectedId} />
        </div>
        <div className="panel">
          {selected ? (
            <DecisionDocumentDetail
              document={selected}
              onUpdated={(next) => {
                setItems((current) => current.map((item) => (item.id === next.id ? next : item)));
              }}
            />
          ) : (
            <p>{t("list.empty")}</p>
          )}
        </div>
      </div>
      <section className="panel">
        <DecisionUploadForm
          submitting={uploading}
          onSubmit={async (form) => {
            setUploading(true);
            try {
              const created = await knowledgeApi.uploadDecision(form);
              setItems((current) => [created, ...current]);
              setSelectedId(created.id);
            } finally {
              setUploading(false);
            }
          }}
        />
      </section>
    </section>
  );
}
