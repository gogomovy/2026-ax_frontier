import { useTranslation } from "react-i18next";
import type { PolicyDocument } from "../types/knowledge";

type Props = {
  items: PolicyDocument[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export function PolicyDocumentList({ items, selectedId, onSelect }: Props) {
  const { t } = useTranslation();
  if (items.length === 0) {
    return <p data-testid="policy-list-empty">{t("list.empty")}</p>;
  }
  return (
    <ul className="doc-list" data-testid="policy-document-list">
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            data-testid={`policy-list-item-${item.id}`}
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
