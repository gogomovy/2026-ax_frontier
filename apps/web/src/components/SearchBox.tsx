import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

type Props = {
  query: string;
  onChange: (query: string) => void;
  onSearch: (query: string) => Promise<void>;
  searching: boolean;
};

export function SearchBox({ query, onChange, onSearch, searching }: Props) {
  const { t } = useTranslation();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await onSearch(query);
  }

  return (
    <form className="row-actions" data-testid="official-search-box" onSubmit={(event) => void handleSubmit(event)}>
      <label>
        {t("search.query")}
        <input
          type="text"
          value={query}
          data-testid="official-search-input"
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
      <button className="primary" type="submit" data-testid="official-search-submit-button" disabled={searching}>
        {t("search.run")}
      </button>
    </form>
  );
}
