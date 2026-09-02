import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { knowledgeApi } from "../api/knowledge";
import { EvidencePanel } from "../components/EvidencePanel";
import type { Evidence, EvidenceKind } from "../types/knowledge";

function isKind(value: string | undefined): value is EvidenceKind {
  return value === "policy" || value === "decision" || value === "article";
}

export function EvidencePage() {
  const { t } = useTranslation();
  const { kind, targetId } = useParams();
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isKind(kind) || !targetId) {
      setError(t("common.error"));
      return;
    }
    let cancelled = false;
    void knowledgeApi
      .getEvidence(kind, targetId)
      .then((next) => {
        if (!cancelled) {
          setEvidence(next);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : t("common.error"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [kind, targetId, t]);

  return (
    <section>
      <p className="page-kicker">
        <Link to="/" data-testid="evidence-page-home-link">
          {t("nav.home")}
        </Link>
      </p>
      {error ? (
        <p className="error" data-testid="evidence-error">
          {error}
        </p>
      ) : null}
      {evidence ? <EvidencePanel evidence={evidence} /> : null}
    </section>
  );
}
