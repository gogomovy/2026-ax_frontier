import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { ALLOWED_EXTENSIONS, type SectorId } from "../sectors";
import { SectorCheckboxes } from "./SectorCheckboxes";

type Props = {
  submitting: boolean;
  onSubmit: (form: FormData) => Promise<void>;
};

function isAllowedFile(file: File): boolean {
  const i = file.name.lastIndexOf(".");
  const ext = i === -1 ? "" : file.name.slice(i + 1).toLowerCase();
  return (ALLOWED_EXTENSIONS as readonly string[]).includes(ext);
}

export function DecisionUploadForm({ submitting, onSubmit }: Props) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [meetingOrSource, setMeetingOrSource] = useState("");
  const [decisionDate, setDecisionDate] = useState("");
  const [sectors, setSectors] = useState<SectorId[]>([]);
  const [tags, setTags] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || !isAllowedFile(file)) {
      setError(t("validation.file"));
      return;
    }
    if (title.trim() === "") {
      setError(t("validation.title"));
      return;
    }
    if (sectors.length === 0) {
      setError(t("validation.sectors"));
      return;
    }
    setError(null);
    const form = new FormData();
    form.append("file", file);
    form.append("title", title.trim());
    form.append("meetingOrSource", meetingOrSource.trim());
    form.append("decisionDate", decisionDate);
    form.append("sectors", sectors.join(","));
    form.append("tags", tags);
    try {
      await onSubmit(form);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("common.error"));
    }
  }

  return (
    <form className="form-grid" data-testid="decision-upload-form" onSubmit={(event) => void handleSubmit(event)}>
      <label>
        {t("upload.file")}
        <input
          type="file"
          accept=".pdf,.txt,.hwp,application/pdf,text/plain"
          data-testid="decision-upload-file-input"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <label>
        {t("upload.title")}
        <input
          type="text"
          value={title}
          data-testid="decision-upload-title-input"
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label>
        {t("upload.meeting")}
        <input
          type="text"
          value={meetingOrSource}
          data-testid="decision-upload-meeting-input"
          onChange={(e) => setMeetingOrSource(e.target.value)}
        />
      </label>
      <label>
        {t("upload.decisionDate")}
        <input
          type="date"
          value={decisionDate}
          data-testid="decision-upload-date-input"
          onChange={(e) => setDecisionDate(e.target.value)}
        />
      </label>
      <div className="field">
        {t("upload.sectors")}
        <SectorCheckboxes value={sectors} onChange={setSectors} testId="decision-upload-sectors" />
      </div>
      <label>
        {t("upload.tags")}
        <input type="text" value={tags} data-testid="decision-upload-tags-input" onChange={(e) => setTags(e.target.value)} />
      </label>
      {error ? (
        <p className="error" data-testid="decision-upload-validation-error">
          {error}
        </p>
      ) : null}
      <button className="primary" type="submit" data-testid="decision-upload-submit-button" disabled={submitting}>
        {submitting ? (
          <>
            <span className="spinner" aria-hidden />
            {t("upload.submitting")}
          </>
        ) : (
          t("upload.submit")
        )}
      </button>
    </form>
  );
}
