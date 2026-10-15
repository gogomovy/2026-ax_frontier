"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AdminPage, C, Card, Loading, Table, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { reasonRule, useIsDataAdmin } from "@/components/admin/DataDelete";
import { useConfirm } from "@/components/providers/UiProvider";
import { Badge, Button } from "@/components/ui/primitives";
import { api, apiPost } from "@/lib/api-client";

/** 자료 연결 상태 — 업무 구성 '자료' 시트의 이름 → 지금 이어진 데이터셋 (Phase O · BIZ-03) */
export interface SourceStatus {
  name: string;
  config: string;
  configId: number | null;
  columns: string[];
  keywords: string[];
  description: string;
  status: "linked" | "waiting";
  dataset?: string;
  datasetName?: string;
  hasData?: boolean;
  closest?: { dataset: string; datasetName: string; missingColumns: string[] } | null;
}
interface ConfigRow {
  id: number;
  name: string;
  version: number;
  status: string;
  fileName: string | null;
  uploadedBy: string | null;
  createdAt: string | null;
  description: string;
  counts: Record<string, number>;
  report: Record<string, unknown>;
}
interface Preview {
  name: string;
  description: string;
  version: number;
  replaces: number | null;
  errors: string[];
  warnings: string[];
  counts: Record<string, { label: string; total: number; create: number; update: number; remove: number }>;
  sources: SourceStatus[];
  linked: number;
  waiting: number;
}

const COUNT_LABEL: Record<string, string> = { sources: "자료", metrics: "지표", workflows: "업무 흐름", bindings: "화면 연결", artifacts: "화면 틀", rules: "규칙", orgs: "조직", screens: "화면", settings: "설정", contracts: "정의서 컬럼" };

/** 업무 구성 (Phase O · BIZ-02 · BIZ-05) — 지표 산식 · 규칙 · 기준값 · 조직 · 업무 흐름 · 화면 연결을 파일로 올려 반영 · 삭제. 원천은 자료 이름으로 이어진다 */
export default function BusinessConfigAdmin() {
  const data = useApiData<{ items: ConfigRow[]; sources: SourceStatus[]; linked: number; waiting: number }>("/admin/business-config");
  const isDataAdmin = useIsDataAdmin();
  const confirm = useConfirm();
  const router = useRouter();
  const { run, busy } = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [pv, setPv] = useState<Preview | null>(null);
  const d = data.data;

  const form = () => {
    const fd = new FormData();
    if (file) fd.append("file", file);
    return fd;
  };
  const preview = () => file && run(() => api<Preview>("/admin/business-config/preview", { method: "POST", body: form() }), undefined).then((r) => r && setPv(r));
  const apply = () =>
    file &&
    run(() => api("/admin/business-config", { method: "POST", body: form() }), "업무 구성을 반영했습니다 — 이어진 자료로 관련 업무 흐름이 다시 계산합니다", async () => {
      setPv(null);
      setFile(null);
      await data.reload();
      router.refresh(); // 메뉴(업무 화면 · 영역)를 다시 받는다 — 구성이 화면 · 권한을 바꾼다
    });
  const remove = async (c: ConfigRow) => {
    const reason = await confirm({
      title: `${c.name} v${c.version} 을(를) 지울까요?`,
      tone: "danger",
      confirmLabel: "구성 삭제",
      body: (
        <div className="flex flex-col gap-xs text-[12.5px]" data-delete-preview="business-config">
          <p>이 구성이 만든 지표 · 규칙 · 업무 흐름 · 화면 연결 · 화면 틀 · 조직 · 화면 · 설정 · 정의서를 지웁니다. 사용자가 있는 조직과 문서가 있는 지식 컬렉션은 남깁니다.</p>
          <p className="text-steel">올린 자료(데이터셋 · 문서)는 지우지 않습니다. 같은 파일을 다시 올리면 그대로 돌아옵니다.</p>
        </div>
      ),
      input: { label: "삭제 사유", placeholder: "예: 새 업무 구성으로 교체", validate: reasonRule },
    });
    if (typeof reason !== "string" || !reason) return;
    await run(() => apiPost(`/admin/business-config/${c.id}/delete`, { reason }), "업무 구성을 지웠습니다", async () => {
      await data.reload();
      router.refresh();
    });
  };

  return (
    <AdminPage
      title="업무 구성"
      description="지표 산식 · 규칙 · 기준값 · 목표 · 조직 · 업무 흐름 · 화면 연결은 플랫폼에 미리 들어 있지 않고, 업무 구성 파일(엑셀 · JSON)로 올립니다. 구성은 원천을 데이터셋 코드가 아니라 자료 이름 · 필요한 열로 가리키므로, 그 자료가 아직 없으면 '자료 대기'로 두었다가 올라오면 자동으로 이어져 계산합니다."
      actions={
        <Button size="sm" variant="quiet" onClick={data.reload}>
          새로고침
        </Button>
      }
    >
      <Card title="구성 파일 올리기">
        <div className="flex flex-wrap items-end gap-md">
          <label className="block">
            <span className="mb-1 block text-[11.5px] font-bold text-steel">업무 구성 파일(.xlsx · .json) — 시트: 자료 · 지표 · 업무흐름 · 흐름단계 · 흐름조건 · 화면연결 · 화면틀 · 규칙 · 조직 · 화면 · 설정 · 정의서 …</span>
            <input
              type="file"
              accept=".xlsx,.json"
              aria-label="업무 구성 파일"
              data-bizconfig-file
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setPv(null);
              }}
              className="text-[12.5px]"
            />
          </label>
          <Button size="sm" variant="quiet" disabled={busy || !file} onClick={preview} data-bizconfig-preview>
            미리보기
          </Button>
          <Button size="sm" variant="confirm" disabled={busy || !file || !isDataAdmin || !pv || pv.errors.length > 0} onClick={apply} data-bizconfig-apply>
            반영
          </Button>
          {!isDataAdmin ? <span className="text-[11.5px] text-attention">반영 · 삭제는 데이터 관리자만 할 수 있습니다.</span> : null}
        </div>
        <p className="mt-xs text-[11.5px] text-stone">같은 이름의 구성을 다시 올리면 새 판이 되고, 새 판에서 빠진 항목은 지웁니다. 먼저 [미리보기]로 오류 · 자료 연결 · 바뀌는 수를 확인하세요.</p>
        {pv ? <PreviewBody p={pv} /> : null}
      </Card>

      <Loading error={data.error} loading={!d && data.loading} />
      {d ? (
        <>
          <Card
            title={
              <span className="flex flex-wrap items-center gap-xs">
                자료 연결 <Badge tone="success">연결됨 {d.linked}</Badge> {d.waiting ? <Badge tone="attention">자료 대기 {d.waiting}</Badge> : null}
              </span>
            }
          >
            <SourceTable rows={d.sources} />
          </Card>
          <Card title="반영된 업무 구성">
            {d.items.length ? (
              <Table head={["이름", "판", "내용", "파일 · 올린 사람", ""]}>
                {d.items.map((c) => (
                  <tr key={c.id} data-bizconfig-row={c.id}>
                    <C className="min-w-[220px]">
                      <span className="font-bold text-ink-deep">{c.name}</span>
                      {c.description ? <p className="line-clamp-2 text-[11px] text-stone">{c.description}</p> : null}
                    </C>
                    <C className="whitespace-nowrap">v{c.version}</C>
                    <C className="max-w-[380px] text-[11.5px]">
                      {Object.entries(c.counts)
                        .filter(([, n]) => n > 0)
                        .map(([k, n]) => `${COUNT_LABEL[k] ?? k} ${n}`)
                        .join(" · ")}
                    </C>
                    <C className="text-[11px]">
                      {c.fileName ?? "-"}
                      <br />
                      {c.uploadedBy ?? "-"} · {fmtTime(c.createdAt)}
                    </C>
                    <C className="whitespace-nowrap">
                      <a className="mr-xs text-[12px] font-bold text-primary-text" href={`/backend/admin/business-config/${c.id}/download`}>
                        내려받기
                      </a>
                      {isDataAdmin ? (
                        <Button size="sm" variant="danger" disabled={busy} onClick={() => remove(c)} data-bizconfig-delete={c.id}>
                          삭제
                        </Button>
                      ) : null}
                    </C>
                  </tr>
                ))}
              </Table>
            ) : (
              <p className="text-[12.5px] text-steel">
                반영된 업무 구성이 없습니다. 업무 화면 지표 · 업무 흐름이 비어 있고, 올린 자료는 분석 에이전트 · AI 어시스턴트 · 온톨로지가 씁니다.
              </p>
            )}
          </Card>
          <p className="text-[11.5px] text-stone">
            자료 자체는{" "}
            <Link href="/admin/datasets" className="font-bold text-primary-text">
              데이터셋·문서
            </Link>
            에서 올리고, 흐름 전체는{" "}
            <Link href="/admin/pipeline" className="font-bold text-primary-text">
              파이프라인
            </Link>
            에서 봅니다.
          </p>
        </>
      ) : null}
    </AdminPage>
  );
}

function PreviewBody({ p }: { p: Preview }) {
  return (
    <div className="mt-md flex flex-col gap-sm rounded-xl border border-hairline bg-white p-md" data-bizconfig-preview-result>
      <p className="text-[13px]">
        <strong>{p.name}</strong> v{p.version}
        {p.replaces ? ` — 지금 판(${p.replaces})을 바꿉니다` : " — 새 구성"} · 자료 연결됨 {p.linked} · 자료 대기 {p.waiting}
      </p>
      {p.errors.length ? (
        <div role="alert" className="rounded-lg bg-critical-faint px-md py-xs text-[12px] text-critical">
          <p className="font-bold">오류 {p.errors.length}건 — 고친 뒤 다시 올려 주세요</p>
          <ul className="list-disc pl-5">
            {p.errors.slice(0, 20).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {p.warnings.length ? (
        <ul className="list-disc pl-5 text-[11.5px] text-attention">
          {p.warnings.slice(0, 12).map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      ) : null}
      <Table head={["항목", "모두", "새로", "바뀜", "지움"]}>
        {Object.entries(p.counts)
          .filter(([, c]) => c.total || c.remove)
          .map(([k, c]) => (
            <tr key={k}>
              <C>{c.label}</C>
              <C right>{c.total}</C>
              <C right>{c.create}</C>
              <C right>{c.update}</C>
              <C right>{c.remove ? <span className="font-bold text-critical">{c.remove}</span> : 0}</C>
            </tr>
          ))}
      </Table>
      <SourceTable rows={p.sources} />
    </div>
  );
}

/** 자료 이름 → 지금 이어진 데이터셋 · 자료 대기(가장 가까운 정의와 없는 열) */
export function SourceTable({ rows }: { rows: SourceStatus[] }) {
  if (!rows.length) return <p className="text-[12.5px] text-steel">업무 구성에 적힌 자료가 없습니다.</p>;
  return (
    <Table head={["자료 이름", "상태", "이어진 데이터셋", "필요한 열"]}>
      {rows.map((s) => (
        <tr key={s.name} data-source-status={s.status}>
          <C className="min-w-[200px]">
            <span className="font-bold text-ink-deep">{s.name}</span>
            {s.config ? <p className="text-[10.5px] text-stone">{s.config}</p> : null}
          </C>
          <C>{s.status === "linked" ? <Badge tone={s.hasData ? "success" : "info"}>{s.hasData ? "연결됨" : "정의만 있음"}</Badge> : <Badge tone="attention">자료 대기</Badge>}</C>
          <C className="text-[11.5px]">
            {s.status === "linked" ? (
              <>
                {s.datasetName} <code className="font-mono text-[10.5px] text-stone">{s.dataset}</code>
              </>
            ) : s.closest ? (
              <span className="text-steel">
                가장 가까운 자료 {s.closest.datasetName} — 없는 열: {s.closest.missingColumns.join(", ")}
              </span>
            ) : (
              <span className="text-steel">맞는 자료가 아직 없습니다 — 필요한 열이 모두 있는 파일을 올리면 자동으로 이어집니다</span>
            )}
          </C>
          <C className="max-w-[320px] text-[11px] text-stone">{s.columns.join(", ")}</C>
        </tr>
      ))}
    </Table>
  );
}
