import { useTranslation } from "react-i18next";
import type { DecisionDocument } from "../types/knowledge";

type Props = {
  items: DecisionDocument[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export function DecisionDocumentList({ items, selectedId, onSelect }: Props) {
  const { t } = useTranslation();
  if (items.length === 0) {
    return <p data-testid="decision-list-empty">{t("list.empty")}</p>;
  }
  return (
    <ul className="doc-list" data-testid="decision-document-list">
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            data-testid={`decision-list-item-${item.id}`}
            aria-current={item.id === selectedId}
            onClick={() => onSelect(item.id)}
          >
            {item.title}
          </button>
        </li>
      ))}
    </ul>
  );
}
