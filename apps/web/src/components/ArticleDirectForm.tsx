import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { type SectorId } from "../sectors";
import { SectorCheckboxes } from "./SectorCheckboxes";

type Props = {
  submitting: boolean;
  onSubmit: (form: FormData) => Promise<void>;
};

export function ArticleDirectForm({ submitting, onSubmit }: Props) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [sectors, setSectors] = useState<SectorId[]>([]);
  const [tags, setTags] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (title.trim() === "" || (url.trim() === "" && file === null)) {
      setError(t("validation.article"));
      return;
    }
    if (sectors.length === 0) {
      setError(t("validation.sectors"));
      return;
    }
    setError(null);
    const form = new FormData();
    form.append("title", title.trim());
    if (url.trim() !== "") {
      form.append("url", url.trim());
    }
    if (file) {
      form.append("file", file);
    }
    form.append("sectors", sectors.join(","));
    form.append("tags", tags);
    try {
      await onSubmit(form);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("common.error"));
    }
  }

  return (
    <form className="form-grid" data-testid="article-direct-form" onSubmit={(event) => void handleSubmit(event)}>
      <h3>{t("articles.direct")}</h3>
      <label>
        {t("upload.title")}
        <input type="text" value={title} data-testid="article-direct-title-input" onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        {t("articles.url")}
        <input type="url" value={url} data-testid="article-direct-url-input" onChange={(e) => setUrl(e.target.value)} />
      </label>
      <label>
        {t("upload.file")}
        <input type="file" data-testid="article-direct-file-input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <div className="field">
        {t("upload.sectors")}
        <SectorCheckboxes value={sectors} onChange={setSectors} testId="article-direct-sectors" />
      </div>
      <label>
        {t("upload.tags")}
        <input type="text" value={tags} data-testid="article-direct-tags-input" onChange={(e) => setTags(e.target.value)} />
      </label>
      {error ? (
        <p className="error" data-testid="article-direct-error">
          {error}
        </p>
      ) : null}
      <button className="primary" type="submit" data-testid="article-direct-submit-button" disabled={submitting}>
        {submitting ? t("upload.submitting") : t("upload.submit")}
      </button>
    </form>
  );
}
