import { useState } from "react";
import { useTranslation } from "react-i18next";
import { knowledgeApi } from "../api/knowledge";
import type { OfficialDomain, SearchHit } from "../types/knowledge";
import { OfficialDomainList } from "./OfficialDomainList";
import { SearchBox } from "./SearchBox";
import { SearchHitList } from "./SearchHitList";
import { SectorCheckboxes } from "./SectorCheckboxes";
import { type SectorId } from "../sectors";

type Props = {
  domains: OfficialDomain[];
  onDomainsChange: () => Promise<void>;
  onCandidateAdded: () => Promise<void>;
};

export function OfficialSearchPanel({ domains, onDomainsChange, onCandidateAdded }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [candidateSectors, setCandidateSectors] = useState<SectorId[]>([]);
  const [candidateError, setCandidateError] = useState<string | null>(null);

  async function runSearch(nextQuery: string) {
    setSearching(true);
    setError(null);
    setHits([]);
    try {
      const result = await knowledgeApi.searchOfficial(nextQuery);
      setHits(result.hits);
      setError(result.error);
      setSearched(true);
    } catch (caught) {
      setHits([]);
      setError(caught instanceof Error ? caught.message : t("search.failed"));
      setSearched(true);
    } finally {
      setSearching(false);
    }
  }

  async function addCandidate(hit: SearchHit) {
    if (candidateSectors.length === 0) {
      setCandidateError(t("validation.sectors"));
      return;
    }
    setCandidateError(null);
    await knowledgeApi.addSearchCandidate({
      title: hit.title,
      url: hit.url,
      sectors: candidateSectors,
      tags: [],
    });
    await onCandidateAdded();
  }

  return (
    <section className="panel" data-testid="official-search-panel">
      <h2>{t("search.title")}</h2>
      <OfficialDomainList
        domains={domains}
        onAdd={async (host) => {
          await knowledgeApi.addDomain(host);
          await onDomainsChange();
        }}
        onDelete={async (id) => {
          await knowledgeApi.deleteDomain(id);
          await onDomainsChange();
        }}
      />
      <SearchBox query={query} onChange={setQuery} onSearch={runSearch} searching={searching} />
      <div className="field">
        {t("upload.sectors")}
        <SectorCheckboxes value={candidateSectors} onChange={setCandidateSectors} testId="search-candidate-sectors" />
      </div>
      {candidateError ? <p className="error">{candidateError}</p> : null}
      {searched ? <SearchHitList hits={hits} error={error} onAddCandidate={addCandidate} /> : null}
    </section>
  );
}
