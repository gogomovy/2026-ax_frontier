"use client";

import { useState } from "react";
import { AdminPage, C, Card, Check, Collapse, JsonEditor, JsonView, Loading, OriginBadge, Select, StatusBadge, Table, Tabs, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { api, apiGetC, apiPatch, apiPost } from "@/lib/api-client";

interface Version {
  id: number;
  version: number;
  asOf: string | null;
  status: string;
  isCurrent: boolean;
  dataOrigin: string;
  fileName: string | null;
  sha256: string | null;
  rows: number;
  quality: { status?: string; checks?: { rule: string; passed: boolean; detail: string; severity: string }[] };
  uploadedBy: string | null;
  createdAt: string;
  note: string | null;
}
interface Ds {
  code: string;
  name: string;
  origin: "bank" | "ext";
  kind: string;
  description: string;
  file_pattern: string | null;
  refresh_cycle: string | null;
  columns: unknown[];
  key_columns: string[];
  as_of_column: string | null;
  mapping: Record<string, unknown>;
  quality_rules: unknown[];
  parser: Record<string, unknown>;
  storage: string;
  usedByMetrics: string[];
  versions: Version[];
}
interface Doc {
  origin: "bank" | "ext";
  id: number;
  docCode: string;
  version: number;
  isCurrent: boolean;
  title: string;
  docClass: string;
  issuer: string | null;
  fileName: string | null;
  status: string;
  chunks: number;
  embedded: number;
  extraction: { by: string | null; entities: number; relations: number; issues: number | null; fallbackReason?: string };
  openIssues: number;
  createdAt: string;
}

/** 데이터셋 정의 · 당행/외부 업로드 · 버전 · 롤백 · 품질 / 문서 업로드 · 구조화 (ADM-08, ING-01~07) */
export default function DatasetsAdmin() {
  const [tab, setTab] = useState<"datasets" | "documents">("datasets");
  return (
    <AdminPage
      title="데이터셋 · 문서"
      description="당행(bank) 데이터와 외부(ext) 데이터는 저장 스키마가 분리됩니다. 업로드 시 출처를 다시 확인하고, 품질 검증을 통과한 버전만 현재 버전이 됩니다. 확정되면 관련 워크플로우만 자동으로 다시 계산합니다."
    >
      <Tabs active={tab} onChange={setTab} tabs={[{ key: "datasets", label: "정형 데이터셋" }, { key: "documents", label: "문서 (비정형)" }]} />
      {tab === "datasets" ? <Datasets /> : <Documents />}
    </AdminPage>
  );
}

function Datasets() {
  const data = useApiData<Ds[]>("/admin/datasets");
  const [sel, setSel] = useState<string | null>(null);
  const cur = data.data?.find((d) => d.code === sel) ?? null;
  return (
    <>
      <Loading error={data.error} loading={!data.data && data.loading} />
      <Card>
        <Table head={["출처", "데이터셋", "종류", "저장", "현재 버전", "사용 지표", ""]}>
          {(data.data ?? []).map((d) => {
            const curV = d.versions.filter((v) => v.isCurrent);
            return (
              <tr key={d.code} className={sel === d.code ? "bg-surface-soft" : ""}>
                <C>
                  <OriginBadge origin={d.origin} />
                </C>
                <C>
                  <span className="font-bold text-ink-deep">{d.name}</span>
                  <p className="font-mono text-[10.5px] text-stone">{d.code}</p>
                </C>
                <C>{d.kind === "master" ? "마스터" : "사실"}</C>
                <C mono>{d.storage}</C>
                <C className="text-[11.5px]">
                  {curV.map((v) => (
                    <span key={v.id} className="mr-1 inline-flex items-center gap-1">
                      v{v.version}
                      {v.asOf ? `(${v.asOf.slice(0, 7)})` : ""} <StatusBadge status={v.quality.status} />
                    </span>
                  ))}
                </C>
                <C right>{d.usedByMetrics.length}</C>
                <C>
                  <Button size="sm" variant={sel === d.code ? "primary" : "quiet"} onClick={() => setSel(sel === d.code ? null : d.code)}>
                    {sel === d.code ? "닫기" : "열기"}
                  </Button>
                </C>
              </tr>
            );
          })}
        </Table>
      </Card>
      {cur ? <DatasetDetail ds={cur} reload={data.reload} /> : null}
    </>
  );
}

function DatasetDetail({ ds, reload }: { ds: Ds; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [origin, setOrigin] = useState<string>(ds.origin);
  const [dataOrigin, setDataOrigin] = useState("actual");
  const [asOf, setAsOf] = useState("");
  const [force, setForce] = useState(false);
  const [preview, setPreview] = useState<unknown>(null);
  const [rows, setRows] = useState<{ columns: string[]; rows: Record<string, unknown>[] } | null>(null);

  const form = () => {
    const fd = new FormData();
    if (file) fd.append("file", file);
    fd.append("origin", origin);
    fd.append("data_origin", dataOrigin);
    if (asOf) fd.append("as_of", asOf);
    fd.append("force", String(force));
    return fd;
  };

  return (
    <>
      <Card title={<span className="flex items-center gap-xs">{ds.name} <OriginBadge origin={ds.origin} /></span>}>
        <p className="mb-md text-[12.5px] text-steel">{ds.description}</p>
        <div className="grid grid-cols-1 gap-md md:grid-cols-[1fr_auto_auto_auto_auto_auto]">
          <label className="block">
            <span className="mb-1 block text-[11.5px] font-bold text-steel">파일 (.csv · .xlsx · .json){ds.file_pattern ? ` — 파일명 규칙 ${ds.file_pattern}` : ""}</span>
            <input type="file" accept=".csv,.tsv,.xlsx,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[12.5px]" />
          </label>
          <Select label="출처 확인" value={origin} onChange={setOrigin} options={[{ value: "bank", label: "당행 데이터" }, { value: "ext", label: "외부 데이터" }]} />
          <Select label="데이터 성격" value={dataOrigin} onChange={setDataOrigin} options={[{ value: "actual", label: "실데이터" }, { value: "simulated", label: "시뮬레이션" }]} />
          <TextInput label="기준일(선택)" value={asOf} onChange={setAsOf} placeholder="YYYY-MM-DD" />
          <div className="flex items-end">
            <Check label="품질 실패 시에도 확정" checked={force} onChange={setForce} />
          </div>
          <div className="flex items-end gap-xs">
            <Button size="sm" variant="quiet" disabled={busy || !file} onClick={() => run(() => api(`/admin/datasets/${ds.code}/preview`, { method: "POST", body: form() }), undefined).then((r) => r && setPreview(r))}>
              미리보기
            </Button>
            <Button size="sm" variant="confirm" disabled={busy || !file} onClick={() => run(() => api(`/admin/datasets/${ds.code}/upload`, { method: "POST", body: form() }), "업로드했습니다 — 관련 워크플로우가 대기열에 올라갑니다", reload).then((r) => r && setPreview(r))}>
              업로드
            </Button>
          </div>
        </div>
        {preview ? (
          <div className="mt-md">
            <JsonView value={preview} maxHeight={300} />
          </div>
        ) : null}
      </Card>

      <Card title="버전">
        <Table head={["버전", "기준일", "상태", "성격", "파일", "행", "품질", "업로드", ""]}>
          {ds.versions.map((v) => (
            <tr key={v.id} className={v.isCurrent ? "bg-[rgba(49,162,76,0.05)]" : ""}>
              <C>
                v{v.version} {v.isCurrent ? <Badge tone="success">현재</Badge> : null}
              </C>
              <C>{v.asOf ?? "-"}</C>
              <C>
                <StatusBadge status={v.status} />
              </C>
              <C>{v.dataOrigin === "actual" ? "실데이터" : "시뮬레이션"}</C>
              <C className="max-w-[260px] text-[11.5px]">
                {v.fileName}
                <p className="font-mono text-[10px] text-stone">{v.sha256?.slice(0, 16)}</p>
              </C>
              <C right>{v.rows}</C>
              <C className="min-w-[200px]">
                <StatusBadge status={v.quality.status} />
                <Collapse label="검증 항목">
                  <ul className="text-[11px]">
                    {(v.quality.checks ?? []).map((c, i) => (
                      <li key={i} className={c.passed ? "text-steel" : c.severity === "error" ? "text-critical" : "text-[#8a5d00]"}>
                        {c.passed ? "✓" : "✕"} {c.rule} — {c.detail}
                      </li>
                    ))}
                  </ul>
                </Collapse>
              </C>
              <C className="text-[11px]">
                {v.uploadedBy}
                <br />
                {fmtTime(v.createdAt)}
              </C>
              <C>
                <div className="flex gap-1">
                  <Button size="sm" variant="quiet" onClick={() => apiGetC<{ columns: string[]; rows: Record<string, unknown>[] }>(`/admin/datasets/${ds.code}/versions/${v.id}/rows?limit=200`).then(setRows)}>
                    행
                  </Button>
                  {!v.isCurrent && (v.status === "committed" || v.status === "rolled_back") ? (
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => window.confirm(`v${v.version} 으로 되돌릴까요? 관련 워크플로우가 다시 계산합니다.`) && run(() => apiPost(`/admin/datasets/${ds.code}/versions/${v.id}/rollback`), "되돌렸습니다", reload)}>
                      되돌리기
                    </Button>
                  ) : null}
                </div>
              </C>
            </tr>
          ))}
        </Table>
        {rows ? (
          <div className="mt-md max-h-[360px] overflow-auto">
            <Table head={rows.columns}>
              {rows.rows.map((r, i) => (
                <tr key={i}>
                  {rows.columns.map((c) => (
                    <C key={c} mono>
                      {r[c] === null || r[c] === undefined ? "" : String(r[c])}
                    </C>
                  ))}
                </tr>
              ))}
            </Table>
          </div>
        ) : null}
      </Card>

      <Card title="정의 (컬럼 · 별칭 · 키 · 품질 규칙 · 온톨로지 매핑 · 파서)">
        <p className="mb-md text-[12px] text-steel">실데이터 형식이 다르면 코드를 바꾸지 않고 여기서 컬럼 별칭(원본 헤더명)과 파서 설정을 고칩니다. 매핑은 그래프 투영(결정론)에 쓰입니다.</p>
        <JsonEditor
          rows={22}
          disabled={busy}
          value={{ name: ds.name, description: ds.description, file_pattern: ds.file_pattern, refresh_cycle: ds.refresh_cycle, columns: ds.columns, key_columns: ds.key_columns, as_of_column: ds.as_of_column, quality_rules: ds.quality_rules, mapping: ds.mapping, parser: ds.parser }}
          onSave={(v) => run(() => apiPatch(`/admin/datasets/${ds.code}`, v), "정의를 저장했습니다", reload)}
        />
      </Card>
    </>
  );
}

function Documents() {
  const docs = useApiData<Doc[]>("/admin/documents", { refreshMs: 8000 });
  const { run, busy } = useAction();
  const [f, setF] = useState({ origin: "ext", doc_class: "gov_policy", title: "", issuer: "", published_at: "", text: "" });
  const [file, setFile] = useState<File | null>(null);
  const [detail, setDetail] = useState<unknown>(null);

  const upload = () => {
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => v && fd.append(k, v));
    if (file) fd.append("file", file);
    return run(() => api("/admin/documents/upload", { method: "POST", body: fd }), "문서를 등록했습니다 — 임베딩·구조화·관련 워크플로우가 이어서 실행됩니다", docs.reload);
  };

  return (
    <>
      <Card title="문서 등록">
        <div className="grid grid-cols-1 gap-md md:grid-cols-6">
          <Select label="출처" value={f.origin} onChange={(v) => setF({ ...f, origin: v })} options={[{ value: "ext", label: "외부 문서" }, { value: "bank", label: "당행 문서" }]} />
          <Select label="문서 분류 DB" value={f.doc_class} onChange={(v) => setF({ ...f, doc_class: v })} options={[{ value: "gov_policy", label: "정부정책" }, { value: "mgmt_decision", label: "경영 의사결정" }, { value: "model_method", label: "모형·방법론" }, { value: "branch_ref", label: "영업점 기준·공문" }, { value: "reference", label: "참고" }]} />
          <TextInput label="제목" value={f.title} onChange={(v) => setF({ ...f, title: v })} className="md:col-span-2" />
          <TextInput label="발행 기관" value={f.issuer} onChange={(v) => setF({ ...f, issuer: v })} />
          <TextInput label="시행일" value={f.published_at} onChange={(v) => setF({ ...f, published_at: v })} placeholder="YYYY-MM-DD" />
        </div>
        <div className="mt-md grid grid-cols-1 gap-md md:grid-cols-[auto_1fr]">
          <label className="block">
            <span className="mb-1 block text-[11.5px] font-bold text-steel">파일 (.pdf · .txt · .md · .html)</span>
            <input type="file" accept=".pdf,.hwpx,.hwp,.txt,.md,.html" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-[12.5px]" />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11.5px] font-bold text-steel">또는 본문 텍스트</span>
            <textarea className="input text-[12.5px]" rows={3} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} />
          </label>
        </div>
        <Button size="sm" variant="confirm" className="mt-md" disabled={busy || !f.title || (!file && !f.text)} onClick={upload}>
          등록
        </Button>
      </Card>
      <Card title="문서">
        <Loading error={docs.error} loading={!docs.data && docs.loading} />
        <Table head={["출처", "문서", "분류", "상태", "청크 · 임베딩", "구조화", "검토 대기", ""]}>
          {(docs.data ?? []).map((d) => (
            <tr key={`${d.origin}-${d.id}`} className={d.isCurrent ? "" : "opacity-50"}>
              <C>
                <OriginBadge origin={d.origin} />
              </C>
              <C className="max-w-[320px]">
                <span className="font-bold text-ink-deep">{d.title}</span>
                <p className="text-[10.5px] text-stone">
                  {d.docCode} v{d.version} · {d.issuer ?? "-"} · {fmtTime(d.createdAt)}
                </p>
              </C>
              <C>
                <Badge>{d.docClass}</Badge>
              </C>
              <C>
                <StatusBadge status={d.status} />
              </C>
              <C right>
                {d.chunks} · {d.embedded}
              </C>
              <C className="text-[11px]">
                {d.extraction.by ?? "-"} · 엔티티 {d.extraction.entities} · 관계 {d.extraction.relations}
                {d.extraction.fallbackReason ? <p className="text-stone">규칙 폴백: {d.extraction.fallbackReason}</p> : null}
              </C>
              <C right>{d.openIssues}</C>
              <C>
                <div className="flex gap-1">
                  <Button size="sm" variant="quiet" onClick={() => apiGetC(`/admin/documents/${d.origin}/${d.id}`).then(setDetail)}>
                    상세
                  </Button>
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => apiPost(`/admin/documents/${d.origin}/${d.id}/reextract`), "재구조화를 요청했습니다", docs.reload)}>
                    재구조화
                  </Button>
                </div>
              </C>
            </tr>
          ))}
        </Table>
        {detail ? (
          <div className="mt-md">
            <JsonView value={detail} maxHeight={420} />
          </div>
        ) : null}
      </Card>
    </>
  );
}
