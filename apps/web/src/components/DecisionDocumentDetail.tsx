import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { knowledgeApi } from "../api/knowledge";
import type { DecisionDocument } from "../types/knowledge";

type Props = {
  document: DecisionDocument;
  onUpdated: (next: DecisionDocument) => void;
};

export function DecisionDocumentDetail({ document, onUpdated }: Props) {
  const { t } = useTranslation();
  const [summary, setSummary] = useState(document.currentVersion.summary);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSummary(document.currentVersion.summary);
  }, [document.id, document.currentVersion.versionNo, document.currentVersion.summary]);

  async function saveSummary(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const next = await knowledgeApi.patchDecisionSummary(document.id, summary);
      onUpdated(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("common.error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <article data-testid="decision-document-detail">
      <h2>{document.title}</h2>
      <p>
        {document.meetingOrSource} · {document.decisionDate} · v{document.currentVersion.versionNo}
      </p>
      <p>{t("detail.noHwpViewer")}</p>
      <p>
        <a href={knowledgeApi.decisionFileUrl(document.id)} data-testid="decision-download-link">
          {t("detail.download")}
        </a>
      </p>
      <h3>{t("detail.extracted")}</h3>
      <pre className="extracted" data-testid="decision-extracted-text">
        {document.currentVersion.extractedText}
      </pre>
      <form onSubmit={(event) => void saveSummary(event)}>
        <label>
          {t("detail.summary")}
          <textarea
            rows={5}
            value={summary}
            data-testid="decision-summary-input"
            onChange={(e) => setSummary(e.target.value)}
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button className="primary" type="submit" data-testid="decision-summary-save-button" disabled={saving}>
          {t("detail.saveSummary")}
        </button>
      </form>
    </article>
  );
}
