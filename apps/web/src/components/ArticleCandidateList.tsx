import { useTranslation } from "react-i18next";
import type { Article } from "../types/knowledge";

type Props = {
  items: Article[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export function ArticleCandidateList({ items, selectedId, onSelect }: Props) {
  const { t } = useTranslation();
  return (
    <div data-testid="article-candidate-list">
      <h3>{t("articles.candidates")}</h3>
      {items.length === 0 ? (
        <p>{t("list.empty")}</p>
      ) : (
        <ul className="doc-list">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                data-testid={`article-candidate-${item.id}`}
                aria-current={item.id === selectedId}
                onClick={() => onSelect(item.id)}
              >
                {item.title}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
