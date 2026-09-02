import { useTranslation } from "react-i18next";
import type { SearchHit } from "../types/knowledge";

type Props = {
  hits: SearchHit[];
  error: string | null;
  onAddCandidate: (hit: SearchHit) => Promise<void>;
};

export function SearchHitList({ hits, error, onAddCandidate }: Props) {
  const { t } = useTranslation();
  if (error) {
    return (
      <p className="error" data-testid="official-search-error">
        {error}
      </p>
    );
  }
  if (hits.length === 0) {
    return <p data-testid="official-search-empty">{t("search.empty")}</p>;
  }
  return (
    <ul className="hit-list" data-testid="official-search-hit-list">
      {hits.map((hit) => (
        <li key={hit.url}>
          <div>
            <strong>{hit.title}</strong>
            <div>
              <a href={hit.url}>{hit.url}</a>
            </div>
            <p>{hit.excerpt}</p>
          </div>
          <button
            type="button"
            className="ghost"
            data-testid={`official-search-add-candidate-${hit.url}`}
            onClick={() => void onAddCandidate(hit)}
          >
            {t("search.addCandidate")}
          </button>
        </li>
      ))}
    </ul>
  );
}
