import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import type { OfficialDomain } from "../types/knowledge";

type Props = {
  domains: OfficialDomain[];
  onAdd: (host: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

export function OfficialDomainList({ domains, onAdd, onDelete }: Props) {
  const { t } = useTranslation();
  const [host, setHost] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    const next = host.trim();
    if (next === "") {
      setError(t("validation.host"));
      return;
    }
    const duplicate = domains.some((item) => item.host.toLowerCase() === next.toLowerCase());
    if (duplicate) {
      setError(t("domains.duplicate"));
      return;
    }
    setError(null);
    try {
      await onAdd(next);
      setHost("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("common.error"));
    }
  }

  return (
    <div data-testid="official-domain-list">
      <h3>{t("domains.title")}</h3>
      <ul>
        {domains.map((domain) => (
          <li key={domain.id} className="row-actions">
            <span>{domain.host}</span>
            <button
              type="button"
              className="ghost"
              data-testid={`official-domain-delete-${domain.id}`}
              onClick={() => void onDelete(domain.id)}
            >
              {t("domains.delete")}
            </button>
          </li>
        ))}
      </ul>
      <form className="row-actions" onSubmit={(event) => void handleAdd(event)}>
        <input
          type="text"
          value={host}
          data-testid="official-domain-host-input"
          onChange={(e) => setHost(e.target.value)}
        />
        <button className="primary" type="submit" data-testid="official-domain-add-button">
          {t("domains.add")}
        </button>
      </form>
      {error ? (
        <p className="error" data-testid="official-domain-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
