import { useTranslation } from "react-i18next";
import type { Evidence } from "../types/knowledge";

type Props = {
  evidence: Evidence;
};

export function EvidencePanel({ evidence }: Props) {
  const { t } = useTranslation();
  return (
    <article data-testid="evidence-panel">
      <h1>{t("evidence.title")}</h1>
      {evidence.unconfirmed ? (
        <p className="error" data-testid="evidence-unconfirmed">
          {t("evidence.unconfirmed")}
        </p>
      ) : null}
      <h2>{evidence.title}</h2>
      <p>
        {evidence.source} · {evidence.date}
      </p>
      <p data-testid="evidence-summary">{evidence.summary}</p>
      {evidence.downloadPath ? (
        <p>
          <a href={evidence.downloadPath} data-testid="evidence-download-link">
            {t("detail.download")}
          </a>
        </p>
      ) : null}
      {evidence.url ? (
        <p>
          <a href={evidence.url} data-testid="evidence-url-link">
            {t("evidence.openUrl")}
          </a>
        </p>
      ) : null}
    </article>
  );
}
