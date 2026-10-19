"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AdminPage, C, Card, Check, Collapse, JsonEditor, JsonView, Loading, OriginBadge, Select, StatusBadge, Table, Tabs, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { PurgeStatus, useDataDelete, useIsDataAdmin } from "@/components/admin/DataDelete";
import { ValueView } from "@/components/admin/ValueView";
import { OwnerBadge, OwnerOrgSelect, type OwnerOrg } from "@/components/admin/OwnerOrg";
import { useConfirm } from "@/components/providers/UiProvider";
import { FileDrop } from "@/components/ui/FileDrop";
import { IntakeWizard } from "@/components/knowledge/IntakeWizard";
import { NewDatasetPanel, definitionPayload, type InferredColumn, type PanelSubmit } from "@/components/knowledge/NewDatasetPanel";
import { Advanced, EmptyState, KeyValueList } from "@/components/ui/Layout";
import { Badge, Button, PillTabs } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { api, apiDelete, apiGetC, apiPatch, apiPost } from "@/lib/api-client";
import { confidentSuggestion, suggestDatasets, titleFromFile } from "@/lib/upload-match";

/** 관리자 업로드 형식 — 안내 문구와 파일 입력의 accept 를 같은 값으로 (Phase E · F7) */
// .md — 마크다운 표(DRM 엑셀을 변환한 파일 · Phase Q MD-01)
const DATASET_ACCEPT = ".csv,.tsv,.xlsx,.json,.md";
const DOCUMENT_ACCEPT = ".pdf,.hwpx,.hwp,.txt,.md,.html";
const fmtAccept = (a: string) => a.replaceAll(",", " · ");

interface UploadResult {
  status?: string;
  version?: number;
  rows?: number;
  quality?: { status?: string; checks?: { rule: string; passed: boolean; detail: string; severity: string }[]; source?: { adapter?: string | null } };
  message?: string;
}

/** 미리보기 · 업로드 결과 — 상태 · 행 수 · 품질 검증을 먼저, 원본은 고급에 */
function UploadResultView({ r }: { r: UploadResult }) {
  const checks = r.quality?.checks ?? [];
  const failed = checks.filter((c) => !c.passed);
  // 통과에 영향 없는 안내 — 정의에 더한 열 · 비운 값 · 저장하지 않은 열 (M.24)
  const notes = checks.filter((c) => c.passed && ["columns_added", "auto_column_values", "unmapped_headers"].includes(c.rule));
  return (
    <div className="mt-md flex flex-col gap-md" data-upload-result>
      <KeyValueList
        items={[
          { label: "처리 상태", value: r.status ? <StatusBadge status={r.status} /> : "미리보기" },
          { label: "품질", value: <StatusBadge status={r.quality?.status} />, hint: checks.length ? `검증 ${checks.length}개 중 실패 ${failed.length}` : undefined },
          { label: "행", value: r.rows !== undefined ? `${r.rows.toLocaleString("ko-KR")}행` : "-" },
          ...(r.version !== undefined ? [{ label: "버전", value: `v${r.version}` }] : []),
          ...(r.quality?.source?.adapter ? [{ label: "읽은 방식", value: r.quality.source.adapter }] : []),
        ]}
      />
      {failed.length ? (
        <ul className="flex flex-col gap-0.5 text-[12px]">
          {failed.map((c, i) => (
            <li key={i} className={c.severity === "error" ? "text-critical" : "text-attention"}>
              ✕ {c.rule} — {c.detail}
            </li>
          ))}
        </ul>
      ) : null}
      {notes.length ? (
        <ul className="flex flex-col gap-0.5 text-[12px]" data-upload-notes>
          {notes.map((c, i) => (
            <li key={i} className={c.severity === "warning" ? "text-attention" : "text-steel"}>
              {c.rule === "columns_added" ? "＋" : "ⓘ"} {c.detail}
            </li>
          ))}
        </ul>
      ) : null}
      <Advanced label="결과 원본(JSON)">
        <JsonView value={r} maxHeight={300} />
      </Advanced>
    </div>
  );
}

type ColumnDef = { name?: string; type?: string; aliases?: string[]; required?: boolean; description?: string; label?: string };

/** 데이터셋 정의 요약 — 컬럼 · 키 · 품질 규칙 · 파서 */
function DefinitionView({ ds }: { ds: Ds }) {
  const cols = (ds.columns as ColumnDef[]).filter((c) => c && typeof c === "object");
  return (
    <div className="flex flex-col gap-md">
      <KeyValueList
        items={[
          { label: "파일명 규칙", value: ds.file_pattern ?? "-" },
          { label: "갱신 주기", value: ds.refresh_cycle ?? "-" },
          { label: "키 컬럼", value: ds.key_columns.length ? ds.key_columns.join(", ") : "-" },
          { label: "기준일 컬럼", value: ds.as_of_column ?? "-" },
          { label: "품질 규칙", value: `${ds.quality_rules.length}개` },
          { label: "사용 지표", value: ds.usedByMetrics.length ? ds.usedByMetrics.slice(0, 8).join(", ") + (ds.usedByMetrics.length > 8 ? ` 외 ${ds.usedByMetrics.length - 8}` : "") : "없음" },
        ]}
      />
      {cols.length ? (
        <Table head={["컬럼", "형식", "원본 헤더 별칭", "필수", "설명"]}>
          {cols.slice(0, 80).map((c, i) => (
            <tr key={`${c.name}-${i}`}>
              <C mono>{c.name}</C>
              <C>{c.type ?? "-"}</C>
              <C className="text-[11px]">{(c.aliases ?? []).join(", ") || "-"}</C>
              <C>{c.required ? "예" : ""}</C>
              <C className="text-[11px]">{c.label ?? c.description ?? ""}</C>
            </tr>
          ))}
        </Table>
      ) : null}
      {Object.keys(ds.parser ?? {}).length ? (
        <div>
          <p className="mb-xs text-[11.5px] font-bold text-steel">파서</p>
          <ValueView value={ds.parser} />
        </div>
      ) : null}
    </div>
  );
}

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
  owner?: OwnerOrg | null;
  createdAt: string;
  note: string | null;
  /** 삭제 표시 (Phase J · DEL-06) — 행 · 원본 파일은 지워지고 기록만 남음 */
  deletedAt?: string | null;
  deletedBy?: string | null;
  deleteReason?: string | null;
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
  /** 사용/중지 (Phase M · DOB-09) — 중지하면 업로드 대상 · 매칭에서 빠진다 */
  active?: boolean;
  /** 공통 통합 DB (§38 CMN) — 모든 부서가 함께 보는 자료, 관리자만 올림 · 소유 팀 없음 */
  common?: boolean;
  /** 이 정의로 이어진 업무 구성의 자료 이름 (Phase O · BIZ-03) — 비면 업무 화면과 이어지지 않은 자료 */
  sources?: string[];
  /** 지우면 끊기는 것 — 비어 있어야 삭제할 수 있다 */
  references?: string[];
}
interface Doc {
  origin: "bank" | "ext";
  id: number;
  owner?: OwnerOrg | null;
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
  deletedAt?: string | null;
  deletedBy?: string | null;
  deleteReason?: string | null;
}

interface CommonDb {
  datasets: { code: string; name: string; kind: string; versions: number; rows: number; asOf: string | null }[];
  docClasses: string[];
  documents: number;
  references: { type: string; ko?: string; to: string; datasets: string[] }[];
}

/** 공통 통합 DB (§38 CMN) — 모든 부서가 함께 보는 자료. 관리자만 올리고, 온톨로지 참조 관계로 부서 자료와 이어진다 */
function CommonDbCard({ onPick }: { onPick: (code: string) => void }) {
  const data = useApiData<CommonDb>("/admin/common-db");
  const d = data.data;
  return (
    <Card title="공통 통합 DB" actions={<Badge tone="primary">관리자만 올림 · 전 부서 공통</Badge>}>
      <p className="mb-md text-[12.5px] text-steel">
        종기부 · 사업부서 · 영업본부 · 영업점이 함께 보는 기준 자료입니다. 데이터셋은 [정의 관리]의 &apos;공통 통합 DB&apos;를 켜고, 문서는 [문서] 탭에서 분류 &apos;공통 통합 자료&apos;로 올립니다. 올린 판의 소유 팀은 비고(전행
        공통), 모든 부서 흐름의 근거 검색 · 질의에 함께 쓰입니다. 다른 부서 자료의 열이 공통 자료의 키(상품코드 · 사무소코드 등)를 가리키면 온톨로지 구축 에이전트가 참조 관계를 제안합니다([온톨로지 › 변경 제안]에서 승인).
      </p>
      {!d ? null : (
        <div className="grid grid-cols-1 gap-md md:grid-cols-3" data-common-db>
          <div>
            <p className="mb-1 text-[12px] font-bold text-steel">공통 데이터셋 {d.datasets.length}개</p>
            {d.datasets.length ? (
              <ul className="flex flex-col gap-0.5 text-[12.5px]">
                {d.datasets.map((x) => (
                  <li key={x.code}>
                    <button type="button" className="font-bold text-primary-text hover:underline" onClick={() => onPick(x.code)}>
                      {x.name}
                    </button>{" "}
                    <span className="text-stone">
                      · 현재 판 {x.versions} · {x.rows.toLocaleString("ko-KR")}행{x.asOf ? ` · ${x.asOf}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-stone">아직 없습니다 — 아래 목록에서 데이터셋을 열고 [정의 관리]에서 켭니다.</p>
            )}
          </div>
          <div>
            <p className="mb-1 text-[12px] font-bold text-steel">공통 문서 {d.documents}건</p>
            <p className="text-[12px] text-stone">분류: {d.docClasses.join(", ") || "–"}</p>
          </div>
          <div>
            <p className="mb-1 text-[12px] font-bold text-steel">온톨로지 참조 관계 {d.references.length}개</p>
            {d.references.length ? (
              <ul className="flex flex-col gap-0.5 text-[12px]">
                {d.references.map((r) => (
                  <li key={r.type}>
                    <span className="font-mono text-[11px]">{r.type}</span> → {r.to} <span className="text-stone">· 부서 자료 {r.datasets.length}개</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-stone">승인된 참조 관계가 없습니다.</p>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

/** 데이터셋 정의 · 당행/외부 업로드 · 버전 · 롤백 · 품질 / 문서 업로드 · 구조화 (ADM-08, ING-01~07) */
export default function DatasetsAdmin() {
  const [tab, setTab] = useState<"intake" | "datasets" | "documents">("datasets");
  return (
    <AdminPage
      title="데이터셋 · 문서"
      description="당행(bank) 데이터와 외부(ext) 데이터는 저장 스키마가 분리됩니다. 업로드 시 출처를 다시 확인하고, 품질 검증을 통과한 버전만 현재 버전이 됩니다. 확정되면 관련 워크플로우만 자동으로 다시 계산합니다. [자료 등록]은 파일을 에이전트가 분석해 정의 · 문서 정보를 제안하고, 확인하면 같은 확정 경로로 반영합니다."
    >
      <Tabs active={tab} onChange={setTab} tabs={[{ key: "intake", label: "자료 등록(에이전트 분석)" }, { key: "datasets", label: "정형 데이터셋" }, { key: "documents", label: "문서 (비정형)" }]} />
      {tab === "intake" ? <IntakeWizard context="admin" /> : tab === "datasets" ? <Datasets /> : <Documents />}
      <PurgeStatus />
    </AdminPage>
  );
}

function Datasets() {
  const data = useApiData<Ds[]>("/admin/datasets");
  const [sel, setSel] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [org, setOrg] = useState<"all" | "bank" | "ext" | "common">("all");
  // 머리 '파일로 업로드' 에서 고른 파일 — 데이터셋을 열면 상세 양식에 채운다 (Phase E · UXF-03)
  const [drop, setDrop] = useState<File | null>(null);
  const [openFile, setOpenFile] = useState<File | null>(null);
  const [stamp, setStamp] = useState(0);
  // 맞는 데이터셋이 없는 새 종류 파일 — 파일에서 추론한 정의를 확인해 데이터셋을 만들고 첫 버전으로 올린다 (DEF-02)
  const [creating, setCreating] = useState(false);
  const [createOwner, setCreateOwner] = useState("");
  const { run: runCreate } = useAction();
  // 목록에서 바로 정의 삭제(M.22 후속) — 데이터 관리자만. 연결(지표 · 바인딩 · 트리거)이 있으면 미리보기에서 함께 정리
  const isDataAdmin = useIsDataAdmin();
  const del = useDataDelete();
  const detailRef = useRef<HTMLDivElement>(null);
  const all = data.data ?? [];
  const cur = all.find((d) => d.code === sel) ?? null;
  // 낱말 하나만 겹치는 것(10점)은 잡음이라 빼고 상위 3개 (업무 [자료 올리기]와 같은 기준)
  const sugg = drop ? suggestDatasets(drop.name, all.map((d) => ({ code: d.code, name: d.name, filePattern: d.file_pattern }))).filter((s) => s.score >= 20).slice(0, 3) : [];

  const open = (code: string, f: File | null) => {
    setSel(code);
    setOpenFile(f);
    setStamp((n) => n + 1);
  };
  // 상세는 긴 표 아래에 열린다 — 열 때마다 그 자리로 옮기고 초점을 준다
  useEffect(() => {
    if (!stamp || !sel) return;
    const el = detailRef.current;
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.focus({ preventScroll: true });
  }, [stamp, sel]);
  const createFromFile = async ({ definition, dataOrigin, note }: PanelSubmit) => {
    if (!drop) return;
    // 정의 + 첫 버전을 한 번에(M.24) — 품질 검사로 확정되지 않으면 정의도 만들지 않는다(빈 정의가 남지 않게)
    const r = await runCreate(
      async () => {
        const fd = new FormData();
        fd.append("file", drop);
        fd.append("definition", JSON.stringify(definitionPayload(definition)));
        fd.append("data_origin", dataOrigin);
        if (note) fd.append("note", note);
        if (createOwner) fd.append("owner_org", createOwner);
        return api<UploadResult>("/admin/datasets/create-upload", { method: "POST", body: fd });
      },
      "데이터셋을 만들고 이 파일을 첫 버전으로 올렸습니다 — 관련 구조 파악 · 그래프 반영이 이어서 실행됩니다",
      data.reload,
    );
    if (r) {
      setCreating(false);
      setDrop(null);
      open(definition.code, null);
    }
  };
  const takeDrop = (f: File | null) => {
    setDrop(f);
    setCreating(false);
    if (!f) return;
    const top = confidentSuggestion(suggestDatasets(f.name, all.map((d) => ({ code: d.code, name: d.name, filePattern: d.file_pattern }))));
    if (top) open(top.code, f);
    // 맞는 정의가 없으면 바로 파일에서 정의를 만들어 보여 준다(M.24) — 정의를 미리 만들어 둘 필요가 없다
    else setCreating(true);
  };
  const list = all.filter((d) => (org === "all" || (org === "common" ? d.common : d.origin === org)) && (!q || `${d.code} ${d.name} ${d.description}`.toLowerCase().includes(q.toLowerCase())));
  const warn = all.filter((d) => d.versions.some((v) => v.isCurrent && v.quality.status && !["passed", "ok"].includes(v.quality.status))).length;
  const empty = all.filter((d) => !d.versions.some((v) => v.isCurrent)).length;
  const sim = all.filter((d) => d.versions.some((v) => v.isCurrent && v.dataOrigin !== "actual")).length;
  return (
    <>
      <CommonDbCard onPick={(code) => open(code, null)} />
      <div className="mb-lg">
        <StatGrid columns={4} label="데이터셋 요약">
          <StatCard label="데이터셋" value={all.length || "-"} unit="개" hint={`당행 ${all.filter((d) => d.origin === "bank").length} · 외부 ${all.filter((d) => d.origin === "ext").length}`} />
          <StatCard label="자료 없음" value={empty} unit="개" tone={empty ? "attention" : "success"} hint={empty ? "현재 버전이 없어 계산에서 빠짐" : "모두 현재 버전 있음"} />
          <StatCard label="품질 경고" value={warn} unit="개" tone={warn ? "attention" : "default"} hint="현재 버전의 품질 검증이 통과가 아님" />
          <StatCard label="시뮬레이션 자료" value={sim} unit="개" tone={sim ? "info" : "default"} hint="실데이터로 바꿔야 할 자료" />
        </StatGrid>
      </div>
      <Card title="파일로 업로드">
        <div className="grid grid-cols-1 gap-md lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <FileDrop
            id="ds-drop"
            accept={DATASET_ACCEPT}
            file={drop}
            onFile={takeDrop}
            compact
            label="정형 자료 파일을 끌어다 놓거나 눌러서 고르세요"
            hint={`${fmtAccept(DATASET_ACCEPT)} — 파일 이름으로 데이터셋을 찾아 업로드 양식을 엽니다(확정 전에 한 번 더 묻습니다)`}
            data-testid="admin-dataset"
          />
          <div className="text-[12.5px]" aria-live="polite">
            {!drop ? (
              <p className="text-steel">또는 아래 표에서 데이터셋을 [열기] 하고 업로드합니다.</p>
            ) : sugg.length ? (
              <div className="flex flex-col gap-xs" data-drop-suggestions>
                <p className="font-bold text-ink-deep">파일 이름으로 찾은 데이터셋</p>
                {sugg.map((s) => {
                  const d = all.find((x) => x.code === s.code);
                  return (
                    <div key={s.code} className="flex flex-wrap items-center gap-xs rounded-xl border border-hairline-soft px-md py-2">
                      <span className="min-w-0 flex-1">
                        <span className="font-bold text-ink-deep">{d?.name ?? s.code}</span> <span className="font-mono text-[10.5px] text-stone">{s.code}</span>
                        <span className="block text-[11.5px] text-steel">근거: {s.reasons.join(" · ")}</span>
                      </span>
                      <Button size="sm" variant={sel === s.code ? "primary" : "quiet"} onClick={() => open(s.code, drop)}>
                        {sel === s.code ? "열림" : "이 데이터셋으로 열기"}
                      </Button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="font-bold text-attention" data-drop-no-match>
                맞는 데이터셋이 없어 파일에서 정의를 만들었습니다 — 아래에서 확인하고 [데이터셋 만들고 첫 버전 올리기]를 누르세요. 기존 자료라면 표에서 고르세요.
              </p>
            )}
            {drop && !creating ? (
              <Button size="sm" variant="quiet" className="mt-xs" onClick={() => setCreating(true)} data-dataset-create-from-file>
                이 파일로 새 데이터셋 만들기
              </Button>
            ) : null}
          </div>
        </div>
        {drop && creating ? (
          <div className="mt-md">
            <div className="mb-md max-w-[420px]">
              <OwnerOrgSelect value={createOwner} onChange={setCreateOwner} />
            </div>
            <NewDatasetPanel
              file={drop}
              inferPath="/admin/datasets/infer"
              submitLabel="데이터셋 만들고 첫 버전 올리기"
              introText="파일의 머리글 · 값으로 정의를 만들었습니다. 저장하면 데이터셋이 만들어지고 이 파일이 바로 현재 버전이 됩니다. 지표 · 워크플로우 연결은 만든 뒤 따로 합니다."
              onSubmit={createFromFile}
              onClose={() => setCreating(false)}
            />
          </div>
        ) : null}
      </Card>
      <Loading error={data.error} loading={!data.data && data.loading} />
      <Card
        title={`데이터셋 ${list.length}개`}
        actions={
          <>
            <TextInput ariaLabel="데이터셋 찾기" placeholder="코드 · 이름 · 설명" value={q} onChange={setQ} className="w-[240px]" />
            <PillTabs size="sm" label="출처" value={org} onChange={setOrg} items={[{ key: "all", label: "전체" }, { key: "bank", label: "당행" }, { key: "ext", label: "외부" }, { key: "common", label: "공통 통합 DB" }]} />
          </>
        }
      >
        <p className="mb-md text-[12.5px] text-steel" data-dataset-list-note>
          이 목록은 업무 자료가 아니라 <strong className="text-ink-deep">데이터셋 정의</strong>(파일 형식 · 열 · 키 · 기준일과 업무 화면 연결)입니다. 올라온 자료는 [현재 버전]에 보이고, 비어 있으면 자료가 없는 정의입니다.
          &apos;업무 화면 연결 정의&apos;는 같은 형식의 파일을 올리면 업무 화면 수치로 이어지는 그릇이라, 그 파일을 올릴 계획이면 지우지 마세요.
        </p>
        {data.data && !list.length ? <EmptyState compact title="맞는 데이터셋이 없습니다" description="찾는 말이나 출처를 바꿔 보세요." /> : null}
        <Table head={["출처", "데이터셋", "종류", "저장", "현재 버전", "사용 지표", ""]}>
          {list.map((d) => {
            const curV = d.versions.filter((v) => v.isCurrent);
            return (
              <tr key={d.code} className={sel === d.code ? "bg-surface-soft" : ""}>
                <C>
                  <OriginBadge origin={d.origin} />
                </C>
                <C>
                  <span className="font-bold text-ink-deep">{d.name}</span>
                  {d.active === false ? <Badge tone="neutral" className="ml-1">중지</Badge> : null}
                  {d.common ? (
                    <Badge tone="primary" className="ml-1">
                      공통 통합 DB
                    </Badge>
                  ) : null}
                  {d.sources?.length ? (
                    <Badge tone="info" className="ml-1">
                      업무 구성 자료 · {d.sources[0]}
                      {d.sources.length > 1 ? ` 외 ${d.sources.length - 1}` : ""}
                    </Badge>
                  ) : null}
                  <p className="font-mono text-[10.5px] text-stone">{d.code}</p>
                </C>
                <C>{d.kind === "master" ? "마스터" : "사실"}</C>
                <C mono>{d.storage}</C>
                <C className="text-[11.5px]">
                  {!curV.length ? <span className="text-stone">자료 없음</span> : null}
                  {curV.map((v) => (
                    <span key={v.id} className="mr-1 inline-flex items-center gap-1">
                      v{v.version}
                      {v.asOf ? `(${v.asOf.slice(0, 7)})` : ""} <StatusBadge status={v.quality.status} />
                    </span>
                  ))}
                </C>
                <C right>{d.usedByMetrics.length}</C>
                <C>
                  <span className="inline-flex items-center gap-1">
                    <Button size="sm" variant={sel === d.code ? "primary" : "quiet"} onClick={() => (sel === d.code ? setSel(null) : open(d.code, drop))} aria-label={`${d.name} ${sel === d.code ? "닫기" : "열기"}`}>
                      {sel === d.code ? "닫기" : "열기"}
                    </Button>
                    {isDataAdmin ? (
                      <Button
                        size="sm"
                        variant="quiet"
                        disabled={del.busy}
                        onClick={() =>
                          del.deleteDefinition(d, async () => {
                            if (sel === d.code) setSel(null);
                            await data.reload();
                          })
                        }
                        aria-label={`${d.name} 정의 삭제`}
                        data-dataset-row-delete={d.code}
                      >
                        삭제
                      </Button>
                    ) : null}
                  </span>
                </C>
              </tr>
            );
          })}
        </Table>
      </Card>
      {cur ? (
        <div ref={detailRef} tabIndex={-1} aria-label={`${cur.name} 상세`} className="scroll-mt-24 outline-none focus-visible:ring-2 focus-visible:ring-primary" data-dataset-detail={cur.code}>
          <DatasetDetail key={`${cur.code}-${stamp}`} ds={cur} reload={data.reload} initialFile={openFile} />
        </div>
      ) : null}
    </>
  );
}

interface NewColumns {
  newColumns: InferredColumn[];
  columns: InferredColumn[];
  samples: Record<string, string[]>;
}

/** 파일에는 있지만 정의에 없어 저장되지 않는 열을 찾아 정의에 더한다 — 업로드 형식이 처음 정의에 묶여 있지 않게 (DEF-04). 새 열은 선택(필수 아님)으로만 더해 기존 업로드가 막히지 않는다 */
function NewColumnsFinder({ ds, file, reload }: { ds: Ds; file: File; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const [found, setFound] = useState<NewColumns | null>(null);
  const find = async () => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await run(() => api<NewColumns>(`/admin/datasets/${ds.code}/infer-diff`, { method: "POST", body: fd }), undefined);
    if (r) setFound(r);
  };
  return (
    <div className="mt-md" data-new-columns>
      <Button size="sm" variant="quiet" disabled={busy} onClick={find}>
        파일에서 새 열 찾기
      </Button>
      <span className="ml-xs text-[12px] text-steel">정의에 없어 저장되지 않는 열이 있는지 확인합니다.</span>
      {found ? (
        found.newColumns.length ? (
          <div className="mt-xs rounded-xl border border-hairline-soft p-md">
            <p className="text-[12.5px] font-bold text-ink-deep">정의에 없는 열 {found.newColumns.length}개</p>
            <ul className="mt-xs flex flex-col gap-0.5 text-[12px]">
              {found.newColumns.map((c) => (
                <li key={c.name}>
                  <code className="font-mono text-charcoal">{c.name}</code> <span className="text-stone">{c.label}</span> · {c.type}
                  {found.samples[c.name]?.length ? <span className="ml-1 font-mono text-[11px] text-stone">예: {found.samples[c.name].join(" · ")}</span> : null}
                </li>
              ))}
            </ul>
            <Button
              size="sm"
              variant="confirm"
              className="mt-xs"
              disabled={busy}
              onClick={async () => {
                const ok = await run(() => apiPatch(`/admin/datasets/${ds.code}`, { columns: found.columns }), `열 ${found.newColumns.length}개를 정의에 더했습니다 — 다음 업로드부터 저장됩니다`, reload);
                if (ok) setFound(null);
              }}
            >
              정의에 더하기(선택 열)
            </Button>
          </div>
        ) : (
          <p className="mt-xs text-[12px] text-success">모든 열이 이미 정의에 있습니다.</p>
        )
      ) : null}
    </div>
  );
}

interface Connect {
  dataset: string;
  triggerKind: "dataset" | "master";
  connected: { workflow: string; name: string }[];
  metrics: string[];
  suggestions: { workflow: string; name: string; score: number; why: string[]; via: string }[];
  ontology: { label: string; ko: string }[];
  builderHref: string;
}

/** 연결 도우미(DOB-11 · Q201) — 이 자료를 읽는 워크플로 · 지표, 이을 만한 워크플로(열 겹침 · 온톨로지 객체 · 키), 이 자료로 분석 에이전트 만들기 */
function ConnectHelper({ ds, reload }: { ds: Ds; reload: () => Promise<void> }) {
  const data = useApiData<Connect>(`/admin/datasets/${ds.code}/connect`);
  const { run, busy } = useAction();
  const c = data.data;
  const after = async () => {
    await Promise.all([data.reload(), reload()]);
  };
  return (
    <Card title="연결 도우미" actions={<Link href={c?.builderHref ?? `/analysis/builder?dataset=${ds.code}`} className="text-[12.5px] font-bold text-primary">이 자료로 분석 에이전트 만들기</Link>}>
      <p className="mb-md text-[12.5px] text-steel">
        새 자료는 온톨로지 구축 · AI 어시스턴트 검색 · 분석 카탈로그에는 바로 들어갑니다. 업무 화면 수치로 이으려면 이 자료가 바뀔 때 다시 계산할 워크플로에 연결하거나(트리거 추가), 분석 에이전트를 만들어 승인합니다. 추천은 열 겹침 · 같은 온톨로지 객체 · 같은 키로 정합니다.
      </p>
      <Loading error={data.error} loading={!c && data.loading} />
      {c ? (
        <div className="flex flex-col gap-md text-[12.5px]">
          <p className="text-charcoal">
            <b>연결된 워크플로</b> {c.connected.length ? c.connected.map((w) => w.name).join(" · ") : "없음"}
            <span className="mx-1.5 text-stone" aria-hidden="true">|</span>
            <b>이 자료로 계산하는 지표</b> {c.metrics.length ? `${c.metrics.length}개 (${c.metrics.slice(0, 4).join(", ")}${c.metrics.length > 4 ? " 등" : ""})` : "없음"}
            {c.ontology.length ? (
              <>
                <span className="mx-1.5 text-stone" aria-hidden="true">|</span>
                <b>온톨로지 객체</b> {c.ontology.map((o) => o.ko).join(" · ")}
              </>
            ) : null}
          </p>
          {c.suggestions.length ? (
            <ul className="flex flex-col gap-xs" aria-label="연결 추천 워크플로">
              {c.suggestions.map((s) => (
                <li key={s.workflow} className="flex flex-wrap items-center gap-xs rounded-xl border border-hairline-soft px-md py-2">
                  <span className="min-w-0 flex-1">
                    <span className="font-bold text-ink-deep">{s.name}</span> <code className="font-mono text-[10.5px] text-stone">{s.workflow}</code>
                    <span className="ml-1.5 text-[11.5px] text-steel tnum">추천 {Math.round(s.score * 100)}점</span>
                    <span className="block text-[11.5px] text-steel">{s.why.join(" · ")}</span>
                  </span>
                  <Button
                    size="sm"
                    variant="quiet"
                    disabled={busy}
                    onClick={() => run(() => apiPost(`/admin/workflows/${s.workflow}/triggers`, { kind: c.triggerKind, target: ds.code }), `${s.name} 에 연결했습니다 — 이 자료가 바뀌면 다시 계산합니다`, after)}
                  >
                    워크플로에 연결
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-steel">이을 만한 기존 워크플로를 찾지 못했습니다 — 이 자료로 분석 에이전트를 만들면 부서 분석 화면에 탭으로 나타납니다.</p>
          )}
        </div>
      ) : null}
    </Card>
  );
}

/** 정의 관리(Phase M · DOB-09 · Q194) — 사용/중지 · 삭제(참조가 남아 있으면 이유를 보이고 막는다). 지운 시드 정의는 다시 시드되지 않는다 */
function DefinitionManage({ ds, reload }: { ds: Ds; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const confirm = useConfirm();
  const isDataAdmin = useIsDataAdmin();
  const del = useDataDelete();
  const refs = ds.references ?? [];
  const active = ds.active !== false;
  return (
    <Card title="정의 관리" actions={ds.sources?.length ? <Badge tone="info">업무 구성 자료</Badge> : <Badge tone="neutral">등록한 정의</Badge>}>
      <p className="mb-md text-[12.5px] text-steel">
        {ds.sources?.length
          ? `올린 파일에서 만든 정의이고, 업무 구성의 자료(${ds.sources.join(", ")})로 이어져 업무 화면 지표가 이 자료로 계산됩니다. 중지 · 삭제하면 그 자료는 '자료 대기'가 되고, 같은 열 구성의 파일이 올라오면 다시 자동으로 이어집니다.`
          : "자료 등록 · 파일로 만든 정의입니다. 중지하면 업로드 대상 · 파일 매칭에서 빠집니다."}
      </p>
      <div className="flex flex-wrap items-center gap-xs">
        <Check label={active ? "사용 중" : "중지됨"} checked={active} disabled={busy} onChange={(v) => run(() => apiPatch(`/admin/datasets/${ds.code}`, { active: v }), v ? "정의를 다시 사용합니다" : "정의를 중지했습니다", reload)} />
        <Check
          label="공통 통합 DB"
          checked={!!ds.common}
          disabled={busy}
          onChange={async (v) => {
            if (v) {
              const ok = await confirm({
                title: `${ds.name} 을(를) 공통 통합 DB 로 둘까요?`,
                body: (
                  <p>
                    모든 부서(종기부 · 사업부서 · 영업본부 · 영업점)가 함께 보는 자료가 됩니다. 올린 판의 소유 팀은 비워지고(전행 공통), 앞으로는 관리자만 올릴 수 있습니다. 온톨로지 구축 에이전트가 이 자료를 가리키는 다른 부서 자료와의 참조 관계를 제안합니다.
                  </p>
                ),
                confirmLabel: "공통으로",
              });
              if (!ok) return;
            }
            await run(() => apiPatch(`/admin/datasets/${ds.code}`, { common: v }), v ? "공통 통합 DB 로 두었습니다 — 온톨로지 구축이 참조 관계를 다시 찾습니다" : "부서 자료로 되돌렸습니다", reload);
          }}
        />
        {refs.length && isDataAdmin ? (
          <Button size="sm" variant="danger" disabled={busy || del.busy} onClick={() => del.deleteDefinition(ds, reload)} data-dataset-delete-cascade>
            연결까지 정의 삭제
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="danger"
          disabled={busy || refs.length > 0}
          onClick={async () => {
            const ok = await confirm({
              title: `${ds.name} 정의를 지울까요?`,
              body: <p>정의 · 삭제 표시만 남은 버전 기록 · 구조 파악 결과가 지워집니다. 되돌리려면 정의를 다시 만들어야 합니다.</p>,
              confirmLabel: "정의 삭제",
              tone: "danger",
            });
            if (!ok) return;
            await run(() => apiDelete(`/admin/datasets/${ds.code}`), "정의를 지웠습니다", reload);
          }}
          data-dataset-delete
        >
          정의 삭제
        </Button>
        {refs.length ? (
          <span className="text-[12px] text-attention">
            {isDataAdmin ? "[정의 삭제]는 막힘 — 아래 연결을 함께 정리하려면 [연결까지 정의 삭제](미리보기 · 사유 확인)" : "지울 수 없음 — 아래가 이 정의를 쓰고 있습니다(연결까지 지우기는 데이터 관리자만)"}
          </span>
        ) : (
          <span className="text-[12px] text-steel">이 정의를 쓰는 곳이 없습니다</span>
        )}
      </div>
      {refs.length ? (
        <ul className="mt-xs list-disc pl-5 text-[12px] text-charcoal" aria-label="정의를 쓰는 곳">
          {refs.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

function DatasetDetail({ ds, reload, initialFile }: { ds: Ds; reload: () => Promise<void>; initialFile?: File | null }) {
  const { run, busy } = useAction();
  const confirm = useConfirm();
  const isDataAdmin = useIsDataAdmin();
  const del = useDataDelete();
  const [file, setFile] = useState<File | null>(initialFile ?? null);
  const [origin, setOrigin] = useState<string>(ds.origin);
  const [dataOrigin, setDataOrigin] = useState("actual");
  const [asOf, setAsOf] = useState("");
  const [force, setForce] = useState(false);
  // 자료를 둘 팀 · 영업점 — 기본은 현재 버전의 소유 조직(같은 팀이 새 판을 올리는 경우가 대부분)
  const [owner, setOwner] = useState<string>(ds.versions.find((v) => v.isCurrent)?.owner?.code ?? "");
  const [preview, setPreview] = useState<UploadResult | null>(null);
  const [rows, setRows] = useState<{ columns: string[]; rows: Record<string, unknown>[] } | null>(null);

  const form = () => {
    const fd = new FormData();
    if (file) fd.append("file", file);
    fd.append("origin", origin);
    fd.append("data_origin", dataOrigin);
    if (asOf) fd.append("as_of", asOf);
    fd.append("force", String(force));
    if (owner) fd.append("owner_org", owner);
    return fd;
  };

  return (
    <>
      <Card title={<span className="flex items-center gap-xs">{ds.name} <OriginBadge origin={ds.origin} /></span>}>
        <p className="mb-md text-[12.5px] text-steel">{ds.description}</p>
        <div className="flex flex-col gap-md">
          <FileDrop
            id={`ds-file-${ds.code}`}
            accept={DATASET_ACCEPT}
            file={file}
            onFile={(f) => {
              setFile(f);
              setPreview(null);
            }}
            compact
            label="이 데이터셋의 새 파일을 끌어다 놓거나 눌러서 고르세요"
            hint={`${fmtAccept(DATASET_ACCEPT)}${ds.file_pattern ? ` · 파일명 규칙 ${ds.file_pattern}` : ""}`}
          />
          <div className="grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-[auto_auto_auto_1fr]">
            <Select label="출처 확인" value={origin} onChange={setOrigin} options={[{ value: "bank", label: "당행 데이터" }, { value: "ext", label: "외부 데이터" }]} />
            <Select label="데이터 성격" value={dataOrigin} onChange={setDataOrigin} options={[{ value: "actual", label: "실데이터" }, { value: "simulated", label: "시뮬레이션" }]} />
            <TextInput label="기준일(선택)" type="date" value={asOf} onChange={setAsOf} />
            <div className="flex items-end">
              <Check label="품질 실패 시에도 확정" checked={force} onChange={setForce} />
            </div>
          </div>
          <div className="max-w-[420px]">
            <OwnerOrgSelect value={owner} onChange={setOwner} />
            <p className="mt-1 text-[11px] text-stone">영업점을 고르면 그 영업점 화면에서 계산되고, 다른 영업점 자료를 밀어내지 않습니다.</p>
          </div>
          <div className="flex flex-wrap items-center gap-xs">
            <Button size="sm" variant="quiet" disabled={busy || !file} onClick={() => run(() => api<UploadResult>(`/admin/datasets/${ds.code}/preview`, { method: "POST", body: form() }), undefined).then((r) => r && setPreview(r))}>
              미리보기
            </Button>
            <Button
              size="sm"
              variant={force ? "danger" : "confirm"}
              disabled={busy || !file}
              onClick={async () => {
                const curV = ds.versions.find((v) => v.isCurrent);
                const ok = await confirm({
                  title: force ? "품질 검사에 실패해도 확정할까요?" : "업로드하고 바로 확정할까요?",
                  body: (
                    <>
                      <p>
                        <strong>{ds.name}</strong>의 현재 버전{curV ? `(v${curV.version})` : ""}이 이 파일({file?.name})로 바뀌고, 관련 워크플로가 다시 계산됩니다. 되돌리려면 버전 표에서 [되돌리기]를 씁니다.
                      </p>
                      {force ? <p className="mt-xs font-bold text-critical">품질 검사에 실패한 자료도 현재 버전이 됩니다. 화면 수치가 틀릴 수 있습니다.</p> : null}
                    </>
                  ),
                  confirmLabel: force ? "실패해도 확정" : "업로드(확정)",
                  tone: force ? "danger" : "default",
                });
                if (!ok) return;
                const r = await run(() => api<UploadResult>(`/admin/datasets/${ds.code}/upload`, { method: "POST", body: form() }), "업로드했습니다 — 관련 워크플로가 대기열에 올라갑니다", reload);
                if (r) setPreview(r);
              }}
              data-admin-upload
            >
              업로드(즉시 확정)
            </Button>
            {!file ? <span className="text-[12px] text-steel">파일을 고르면 미리보기 · 업로드할 수 있습니다.</span> : null}
          </div>
        </div>
        {preview ? <UploadResultView r={preview} /> : null}
        {file ? <NewColumnsFinder ds={ds} file={file} reload={reload} /> : null}
      </Card>

      <ConnectHelper ds={ds} reload={reload} />
      <DefinitionManage ds={ds} reload={reload} />

      <Card title="버전">
        <Table head={["버전", "기준일", "상태", "성격", "소유", "파일", "행", "품질", "업로드", ""]}>
          {ds.versions.map((v) => (
            <tr key={v.id} className={v.isCurrent ? "bg-success-faint" : v.status === "deleted" ? "bg-surface-soft" : ""} data-version-status={v.status}>
              <C>
                v{v.version} {v.isCurrent ? <Badge tone="success">현재</Badge> : null}
              </C>
              <C>{v.asOf ?? "-"}</C>
              <C>
                <StatusBadge status={v.status} />
                {v.status === "deleted" ? (
                  <p className="mt-0.5 max-w-[200px] text-[10.5px] text-stone">
                    {v.deletedBy ?? "-"} · {fmtTime(v.deletedAt ?? null)}
                    {v.deleteReason ? <span className="block">사유: {v.deleteReason}</span> : null}
                  </p>
                ) : null}
              </C>
              <C>{v.dataOrigin === "actual" ? "실데이터" : "시뮬레이션"}</C>
              <C>
                <OwnerBadge owner={v.owner} />
              </C>
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
                      <li key={i} className={c.passed ? "text-steel" : c.severity === "error" ? "text-critical" : "text-attention"}>
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
                  {v.status !== "deleted" ? (
                    <Button size="sm" variant="quiet" onClick={() => apiGetC<{ columns: string[]; rows: Record<string, unknown>[] }>(`/admin/datasets/${ds.code}/versions/${v.id}/rows?limit=200`).then(setRows)}>
                      행
                    </Button>
                  ) : null}
                  {!v.isCurrent && (v.status === "committed" || v.status === "rolled_back") ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={async () => {
                        const ok = await confirm({ title: `v${v.version}(으)로 되돌릴까요?`, body: `${ds.name}의 현재 버전이 v${v.version}(으)로 바뀌고 관련 워크플로가 다시 계산됩니다.`, confirmLabel: "되돌리기" });
                        if (ok) await run(() => apiPost(`/admin/datasets/${ds.code}/versions/${v.id}/rollback`), "되돌렸습니다", reload);
                      }}
                    >
                      되돌리기
                    </Button>
                  ) : null}
                  {isDataAdmin && v.status !== "deleted" ? (
                    <Button size="sm" variant="danger" disabled={busy || del.busy} onClick={() => void del.deleteVersion(ds, v.id, reload)} aria-label={`v${v.version} 삭제`} data-delete-version={v.id}>
                      삭제
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
        <DefinitionView ds={ds} />
        <div className="mt-md">
          <Advanced label="고급 — 정의 JSON 편집">
            <JsonEditor
              rows={22}
              disabled={busy}
              value={{ name: ds.name, description: ds.description, file_pattern: ds.file_pattern, refresh_cycle: ds.refresh_cycle, columns: ds.columns, key_columns: ds.key_columns, as_of_column: ds.as_of_column, quality_rules: ds.quality_rules, mapping: ds.mapping, parser: ds.parser }}
              onSave={(v) => run(() => apiPatch(`/admin/datasets/${ds.code}`, v), "정의를 저장했습니다", reload)}
            />
          </Advanced>
        </div>
      </Card>
    </>
  );
}

function Documents() {
  const [showDeleted, setShowDeleted] = useState(false);
  const docs = useApiData<Doc[]>(`/admin/documents${showDeleted ? "?include_deleted=true" : ""}`, { refreshMs: 8000 });
  const { run, busy } = useAction();
  const isDataAdmin = useIsDataAdmin();
  const del = useDataDelete();
  const [f, setF] = useState({ origin: "ext", doc_class: "gov_policy", title: "", issuer: "", published_at: "", text: "" });
  const [owner, setOwner] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [detail, setDetail] = useState<unknown>(null);

  const upload = async () => {
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => v && fd.append(k, v));
    if (file) fd.append("file", file);
    if (owner) fd.append("owner_org", owner);
    const r = await run(() => api("/admin/documents/upload", { method: "POST", body: fd }), "문서를 등록했습니다 — 임베딩·구조화·관련 워크플로우가 이어서 실행됩니다", docs.reload);
    if (r !== null) {
      setFile(null);
      setF((cur) => ({ ...cur, title: "", issuer: "", published_at: "", text: "" }));
    }
  };

  return (
    <>
      <Card title="문서 등록">
        <div className="grid grid-cols-1 gap-md md:grid-cols-6">
          <Select label="출처" value={f.origin} onChange={(v) => setF({ ...f, origin: v })} options={[{ value: "ext", label: "외부 문서" }, { value: "bank", label: "당행 문서" }]} />
          <Select label="문서 분류 DB" value={f.doc_class} onChange={(v) => setF({ ...f, doc_class: v })} options={[{ value: "gov_policy", label: "정부정책" }, { value: "mgmt_decision", label: "경영 의사결정" }, { value: "model_method", label: "모형·방법론" }, { value: "branch_ref", label: "영업점 기준·공문" }, { value: "reference", label: "참고" }, { value: "common_ref", label: "공통 통합 자료(전 부서)" }]} />
          <TextInput label="제목" value={f.title} onChange={(v) => setF({ ...f, title: v })} className="md:col-span-2" />
          <TextInput label="발행 기관" value={f.issuer} onChange={(v) => setF({ ...f, issuer: v })} />
          <TextInput label="시행일" type="date" value={f.published_at} onChange={(v) => setF({ ...f, published_at: v })} />
        </div>
        <div className="mt-md max-w-[420px]">
          <OwnerOrgSelect value={owner} onChange={setOwner} label="문서를 둘 팀 · 영업점" />
        </div>
        <div className="mt-md grid grid-cols-1 gap-md md:grid-cols-2">
          <FileDrop
            id="doc-file"
            accept={DOCUMENT_ACCEPT}
            file={file}
            onFile={(x) => {
              setFile(x);
              // 제목이 비었으면 파일 이름(확장자 제외)으로
              if (x && !f.title.trim()) setF((cur) => ({ ...cur, title: titleFromFile(x.name) }));
            }}
            compact
            label="문서 파일을 끌어다 놓거나 눌러서 고르세요"
            hint={`${fmtAccept(DOCUMENT_ACCEPT)} · 스캔 PDF 는 글자 인식(OCR) 후`}
          />
          <label className="block">
            <span className="mb-1 block text-[11.5px] font-bold text-steel">또는 본문 텍스트</span>
            <textarea className="input text-[12.5px]" rows={4} value={f.text} disabled={Boolean(file)} onChange={(e) => setF({ ...f, text: e.target.value })} />
          </label>
        </div>
        <div className="mt-md flex flex-wrap items-center gap-xs">
          <Button size="sm" variant="confirm" disabled={busy || !f.title || (!file && !f.text)} onClick={upload}>
            등록
          </Button>
          {!f.title ? <span className="text-[12px] text-steel">제목을 입력하세요.</span> : !file && !f.text ? <span className="text-[12px] text-steel">파일을 고르거나 본문을 넣으세요.</span> : null}
        </div>
      </Card>
      <Card title="문서" actions={<Check label="삭제된 문서 보기" checked={showDeleted} onChange={setShowDeleted} />}>
        <Loading error={docs.error} loading={!docs.data && docs.loading} />
        <Table head={["출처", "문서", "분류", "소유", "상태", "청크 · 임베딩", "구조화", "검토 대기", ""]}>
          {(docs.data ?? []).map((d) => (
            <tr key={`${d.origin}-${d.id}`} className={d.isCurrent ? "" : "opacity-50"} data-doc-status={d.status}>
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
                <OwnerBadge owner={d.owner} />
              </C>
              <C>
                <StatusBadge status={d.status} />
                {d.status === "deleted" ? (
                  <p className="mt-0.5 max-w-[200px] text-[10.5px] text-stone">
                    {d.deletedBy ?? "-"} · {fmtTime(d.deletedAt ?? null)}
                    {d.deleteReason ? <span className="block">사유: {d.deleteReason}</span> : null}
                  </p>
                ) : null}
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
                  {d.status !== "deleted" ? (
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => apiPost(`/admin/documents/${d.origin}/${d.id}/reextract`), "재구조화를 요청했습니다", docs.reload)}>
                      재구조화
                    </Button>
                  ) : null}
                  {isDataAdmin && d.status !== "deleted" ? (
                    <Button size="sm" variant="danger" disabled={busy || del.busy} onClick={() => void del.deleteDocument(d, docs.reload)} aria-label={`${d.title} v${d.version} 삭제`} data-delete-document={`${d.origin}-${d.id}`}>
                      삭제
                    </Button>
                  ) : null}
                </div>
              </C>
            </tr>
          ))}
        </Table>
        {detail ? (
          <div className="mt-md">
            <Advanced label="문서 상세 원본(JSON)" defaultOpen>
              <JsonView value={detail} maxHeight={420} />
            </Advanced>
          </div>
        ) : null}
      </Card>
    </>
  );
}
