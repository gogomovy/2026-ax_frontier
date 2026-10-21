"use client";

import Link from "next/link";
import { useState } from "react";
import { C, Card, Collapse, Loading, Select, Table, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { useConfirm } from "@/components/providers/UiProvider";
import { EmptyState, KeyValueList, Notice } from "@/components/ui/Layout";
import { Badge, Button, PillTabs } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";
import { opText } from "@/components/admin/ontology/opText";
import { KIND_LABEL, STATUS_LABEL, groupByKind, impactText, previewValue, reasonError, scoreText, type ProposalItem, type ProposalsData } from "@/lib/stewardProposals";

type Status = "pending" | "approved" | "rejected" | "";

/**
 * 데이터 책임자 승인함 (요구사항 §40 STW) — 새 자료가 올라오면 에이전트가 만든 제안(분석 화면 · 추적 지표 · 개념 연결)과
 * 부서 사용자의 분석 요청을 보고 승인 · 반려한다. 승인 전에는 계산 · 화면 · 그래프 어디에도 나가지 않는다.
 * 책임자는 자기 부서가 소유한 자료 · 자기 부서 사용자의 요청만, 관리자는 전체를 본다. 본인이 요청한 분석은 다른 사람이 처리한다.
 */
export function StewardProposals({ initial }: { initial: ProposalsData }) {
  const [status, setStatus] = useState<Status>("pending");
  const data = useApiData<ProposalsData>(`/db/steward/proposals?status=${status}`, { refreshMs: 20000 });
  const d = data.data ?? (status === "pending" ? initial : null);
  const counts = d?.counts ?? initial.counts;
  const groups = groupByKind(d?.items ?? []);
  return (
    <section aria-label="데이터 책임자 승인함" className="flex flex-col gap-md" data-steward-proposals>
      <Notice tone="info" title={`${d?.scope?.name ?? initial.scope?.name ?? "소속 부서"} 승인함`}>
        새 자료가 올라오면 에이전트가 자료 구조를 보고 분석 화면 · 추적 지표 · 업무 개념 연결 · 온톨로지 변경(객체 유형 · 링크)을 제안합니다. 승인하면 계산 커널이 계산하고 분석 · 변화 감지 에이전트가 의견과 변화를 붙여 화면 · 검색 · 그래프에
        반영되고, 반려하면 같은 제안을 다시 만들지 않습니다. 승인 전에는 어디에도 나가지 않습니다.
      </Notice>
      <PillTabs
        size="sm"
        label="제안 상태"
        value={status}
        onChange={setStatus}
        items={[
          { key: "pending", label: "승인 대기", count: counts.total ?? 0 },
          { key: "approved", label: "승인" },
          { key: "rejected", label: "반려" },
          { key: "", label: "전체" },
        ]}
      />
      <Loading error={data.error} loading={!d && data.loading} />
      {d && !groups.length ? (
        <EmptyState compact title={status === "pending" ? "처리할 제안이 없습니다" : "기록이 없습니다"} description="부서 자료가 새로 올라오면 에이전트 제안이 여기에 나타납니다." />
      ) : null}
      {groups.map((g) => (
        <div key={g.kind} className="flex flex-col gap-md" data-proposal-kind={g.kind}>
          <h2 className="text-[14px] font-bold text-ink-deep">
            {KIND_LABEL[g.kind]} <span className="text-[12px] font-normal text-steel">{g.items.length}건</span>
          </h2>
          {g.kind === "analysis" ? g.items.map((it) => <AnalysisCard key={it.id} it={it} spaces={d?.spaces ?? []} reload={data.reload} />) : null}
          {g.kind === "metric" ? <MetricTable items={g.items} reload={data.reload} /> : null}
          {g.kind === "concept" ? <ConceptTable items={g.items} reload={data.reload} /> : null}
          {g.kind === "ontology" ? g.items.map((it) => <OntologyCard key={it.id} it={it} reload={data.reload} />) : null}
        </div>
      ))}
    </section>
  );
}

function StatusTag({ it }: { it: ProposalItem }) {
  const tone = it.status === "pending" ? "attention" : it.status === "approved" ? "success" : "neutral";
  return <Badge tone={tone}>{STATUS_LABEL[it.status] ?? it.status}</Badge>;
}

function useReject() {
  const confirm = useConfirm();
  return (title: string, body: string) =>
    confirm({ title, tone: "danger", confirmLabel: "반려", body: <p className="text-[12.5px]">{body}</p>, input: { label: "반려 사유", placeholder: "예: 이미 다른 화면에서 보는 자료", validate: reasonError } });
}

function AnalysisCard({ it, spaces, reload }: { it: ProposalItem; spaces: { key: string; label: string }[]; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const confirm = useConfirm();
  const reject = useReject();
  const [space, setSpace] = useState(it.space ?? "");
  const [note, setNote] = useState("");
  const spaceLabel = spaces.find((s) => s.key === space)?.label ?? it.spaceLabel ?? space;
  const figures = it.preview?.figures ?? [];
  const base = `/db/steward/proposals/analysis/${it.agent}/${it.version}`;
  const approve = async () => {
    const ok = await confirm({
      title: `'${it.title}' 분석을 승인할까요?`,
      confirmLabel: "승인하고 만들기",
      body: (
        <p className="text-[12.5px]">
          분석 에이전트(지표 {it.metrics?.length ?? 0}개 · 흐름 · 보고서 탭)가 만들어지고 바로 첫 계산을 합니다. 결과는 <strong>{spaceLabel}</strong> 분석 탭에 나타나고, 자료가 새로 올라올 때마다 다시 계산 · 서술됩니다.
        </p>
      ),
    });
    if (!ok) return;
    await run(() => apiPost(`${base}/approve`, { note: note || null, ...(space && space !== it.space ? { space } : {}) }), "승인했습니다 — 첫 계산이 대기열에 올라갑니다", reload);
  };
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-xs" data-proposal={it.id}>
          {it.title}
          <Badge tone={it.auto ? "info" : "neutral"}>{it.auto ? "에이전트 제안" : "사용자 요청"}</Badge>
          {it.by ? <Badge>{it.by === "llm" ? "LLM 판단" : "규칙"}</Badge> : null}
          <StatusTag it={it} />
        </span>
      }
      actions={it.href ? <Link href={it.href} className="text-[12.5px] font-bold text-primary underline">결과 보기</Link> : null}
    >
      <div className="grid grid-cols-1 gap-lg lg:grid-cols-[minmax(0,340px)_1fr]">
        <KeyValueList
          columns={1}
          dense
          items={[
            ...(it.datasetName ? [{ label: "자료", value: it.datasetName }] : []),
            ...(it.periods ? [{ label: "보관 기준일", value: `${it.periods}개${it.periods >= 2 ? " · 직전 기준일 대비 비교" : ""}` }] : []),
            { label: "분석 공간", value: it.spaceLabel ?? it.space ?? "-" },
            { label: "요청", value: `${it.requestedByName ?? it.requestedBy ?? "-"} · ${fmtTime(it.createdAt)}` },
            ...(it.purpose ? [{ label: "목적", value: it.purpose }] : []),
            ...(it.reviewedAt ? [{ label: "처리", value: `${it.reviewedByName ?? "-"} · ${fmtTime(it.reviewedAt)}` }] : []),
            ...(it.reviewNote ? [{ label: "처리 메모", value: it.reviewNote }] : []),
          ]}
        />
        <div className="min-w-0">
          <p className="mb-xs text-[12px] font-bold text-steel">미리 계산(현재 자료 · 저장 안 함)</p>
          {figures.length ? (
            <ul className="grid grid-cols-1 gap-x-md gap-y-1 text-[12.5px] sm:grid-cols-2">
              {figures.map((f) => (
                <li key={f.id} className="flex justify-between gap-xs border-b border-hairline-soft py-0.5">
                  <span className="text-steel">{f.label ?? f.id}</span>
                  <span className="font-bold text-ink-deep tnum">{previewValue(f)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12px] text-stone">미리 계산한 값이 없습니다 — 승인 뒤 첫 실행에서 계산합니다.</p>
          )}
          <Collapse label={`지표 ${it.metrics?.length ?? 0}개 · 표 ${it.tables?.length ?? 0}개`}>
            <ul className="text-[12px] text-charcoal">
              {(it.metrics ?? []).map((m) => (
                <li key={m.key}>
                  {m.label} <span className="font-mono text-[10.5px] text-stone">{m.formula}</span>
                </li>
              ))}
              {(it.tables ?? []).map((t) => (
                <li key={t.key}>표 · {t.caption}</li>
              ))}
            </ul>
          </Collapse>
          {it.sourceText ? (
            <Collapse label="요청 내용">
              <p className="whitespace-pre-wrap text-[12px] text-charcoal">{it.sourceText}</p>
            </Collapse>
          ) : null}
          {it.issues?.length ? (
            <Collapse label={`검증 메모 ${it.issues.length}건`}>
              <ul className="text-[11.5px] text-attention">
                {it.issues.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            </Collapse>
          ) : null}
        </div>
      </div>
      {it.status === "pending" && !it.canReview ? <p className="mt-md text-[12px] text-stone">본인이 요청한 분석입니다 — 다른 책임자나 관리자가 처리합니다.</p> : null}
      {it.status === "pending" && it.canReview ? (
        <div className="mt-lg flex flex-col gap-xs border-t border-hairline-soft pt-md" data-proposal-review={it.id}>
          <div className="grid grid-cols-1 gap-md sm:grid-cols-[minmax(0,240px)_1fr]">
            {!it.spaceLocked && spaces.length > 1 ? (
              <Select label="분석 공간" ariaLabel="결과를 둘 분석 공간" value={space} onChange={setSpace} options={spaces.map((s) => ({ value: s.key, label: s.label }))} />
            ) : null}
            <label htmlFor={`pnote-${it.id}`} className="flex flex-col gap-1 text-[12px] font-bold text-charcoal">
              처리 메모(선택)
              <textarea id={`pnote-${it.id}`} className="input text-[12.5px] font-normal" rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
            </label>
          </div>
          <div className="flex flex-wrap gap-xs">
            <Button size="sm" variant="confirm" disabled={busy} onClick={approve}>
              승인하고 만들기
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={async () => {
                const reason = await reject(`'${it.title}' 제안을 반려할까요?`, "반려하면 이 자료로 같은 분석을 다시 제안하지 않습니다. 필요하면 [분석 에이전트 만들기]로 직접 만들 수 있습니다.");
                if (typeof reason === "string" && reason) await run(() => apiPost(`${base}/reject`, { note: reason }), "반려했습니다", reload);
              }}
            >
              반려…
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

function MetricTable({ items, reload }: { items: ProposalItem[]; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const reject = useReject();
  return (
    <Card>
      <p className="mb-md text-[12.5px] text-steel">아직 어떤 지표도 읽지 않는 자료의 측정 열로 지표 제안 에이전트가 만든 후보입니다. 승인하면 계산 커널이 계산해 지표 이력에 남고, 다른 분석이 상위 지표(KPI)로 쓸 수 있습니다.</p>
      <Table head={["지표", "자료", "이유", "상태", ""]}>
        {items.map((m) => (
          <tr key={m.id} data-proposal={m.id}>
            <C className="min-w-[180px]">
              <span className="font-bold text-ink-deep">{m.label}</span>
              <p className="font-mono text-[10.5px] text-stone">
                {m.formula} · {m.code}
              </p>
            </C>
            <C>{m.datasetName ?? "-"}</C>
            <C className="max-w-[380px] text-[12px]">{m.reason}</C>
            <C>
              <StatusTag it={m} />
            </C>
            <C>
              {m.canReview ? (
                <div className="flex gap-1">
                  <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost(`/db/steward/proposals/metric/${m.code}/approve`, {}), "승인했습니다 — 계산이 대기열에 올라갑니다", reload)}>
                    승인
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={async () => {
                      const reason = await reject(`'${m.label}' 지표 제안을 반려할까요?`, "반려하면 같은 열로 지표를 다시 제안하지 않습니다.");
                      if (typeof reason === "string" && reason) await run(() => apiPost(`/db/steward/proposals/metric/${m.code}/reject`, { note: reason }), "반려했습니다", reload);
                    }}
                  >
                    반려…
                  </Button>
                </div>
              ) : null}
            </C>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function ConceptTable({ items, reload }: { items: ProposalItem[]; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const reject = useReject();
  return (
    <Card>
      <p className="mb-md text-[12.5px] text-steel">자료 이름 · 열 · 값이 온톨로지의 업무 개념과 맞아 개념 연결 에이전트가 고른 후보입니다. 승인하면 그래프에서 자료가 그 개념에 이어지고(근거 검색 · 팀 데이터가 함께 찾음), 질문하기 색인에 개념이 붙습니다.</p>
      <Table head={["자료", "개념", "근거", "확신", "상태", ""]}>
        {items.map((c) => (
          <tr key={c.id} data-proposal={c.id}>
            <C>{c.datasetName ?? c.dataset}</C>
            <C className="min-w-[140px]">
              <span className="font-bold text-ink-deep">{c.name ?? c.key}</span>
              <p className="text-[10.5px] text-stone">{c.labelKo ?? c.label}</p>
            </C>
            <C className="max-w-[360px] text-[11.5px]">
              {(c.evidence ?? []).slice(0, 3).join(" · ")}
              {c.reason ? <p className="text-steel">{c.reason}</p> : null}
              {c.note ? <p className="text-stone">메모: {c.note}</p> : null}
            </C>
            <C right>{scoreText(c.score)}</C>
            <C>
              <StatusTag it={c} />
            </C>
            <C>
              {c.canReview && c.dataset ? (
                <div className="flex gap-1">
                  <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost(`/db/steward/proposals/concept/${encodeURIComponent(c.dataset ?? "")}/approve`, { label: c.label, key: c.key }), "연결했습니다 — 그래프 · 색인을 다시 맞춥니다", reload)}>
                    연결
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={async () => {
                      const reason = await reject(`'${c.name ?? c.key}' 연결을 반려할까요?`, "반려하면 이 자료에 같은 개념 연결을 다시 제안하지 않습니다.");
                      if (typeof reason === "string" && reason) await run(() => apiPost(`/db/steward/proposals/concept/${encodeURIComponent(c.dataset ?? "")}/reject`, { label: c.label, key: c.key, note: reason }), "반려했습니다", reload);
                    }}
                  >
                    반려…
                  </Button>
                </div>
              ) : null}
            </C>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function OntologyCard({ it, reload }: { it: ProposalItem; reload: () => Promise<void> }) {
  const { run, busy } = useAction();
  const confirm = useConfirm();
  const reject = useReject();
  const ops = it.ops ?? [];
  const base = `/db/steward/proposals/ontology/${it.pid}`;
  const datasets = (it.datasets ?? []).map((x) => x.name || x.code).join(", ");
  const approve = async () => {
    const ok = await confirm({
      title: "온톨로지 변경을 적용할까요?",
      confirmLabel: "승인하고 적용",
      body: (
        <p className="text-[12.5px]">
          연산 {it.opCount ?? ops.length}개를 활성 스키마에 적용해 새 판을 만듭니다. 그래프가 다시 투영되고(예상 {impactText(it.impact)}) 문서 추출이 새 판으로 다시 돕니다. 일부 연산만 적용하려면 관리자에게 요청하세요.
        </p>
      ),
    });
    if (ok) await run(() => apiPost(`${base}/approve`, {}), "적용했습니다 — 그래프를 다시 투영합니다", reload);
  };
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-xs" data-proposal={it.id}>
          {it.title}
          <StatusTag it={it} />
        </span>
      }
    >
      <div className="grid grid-cols-1 gap-lg lg:grid-cols-[minmax(0,340px)_1fr]">
        <KeyValueList
          columns={1}
          dense
          items={[
            { label: "원천 자료", value: datasets || "-" },
            ...(it.linkedDatasets?.length ? [{ label: "잇는 객체 유형의 자료", value: it.linkedDatasets.map((x) => x.name || x.code).join(", ") }] : []),
            { label: "변경", value: it.summary || `연산 ${it.opCount ?? ops.length}개` },
            { label: "그래프 영향(예상)", value: impactText(it.impact) },
            { label: "제안", value: `${it.createdByName ?? it.createdBy ?? "-"} · ${fmtTime(it.createdAt)}` },
            ...(it.baseVersion ? [{ label: "기준 판", value: `v${it.baseVersion}${it.appliedVersion ? ` → 적용 v${it.appliedVersion}` : ""}` }] : []),
            ...(it.decidedAt ? [{ label: "처리", value: `${it.decidedByName ?? "-"} · ${fmtTime(it.decidedAt)}` }] : []),
            ...(it.note ? [{ label: "처리 메모", value: it.note }] : []),
          ]}
        />
        <div className="min-w-0">
          <p className="mb-xs text-[12px] font-bold text-steel">변경 연산</p>
          <ul className="flex flex-col gap-1 text-[12.5px]" data-ontology-ops>
            {ops.map((o) => (
              <li key={o.key} className="border-b border-hairline-soft py-0.5">
                <span className="text-ink-deep">{opText(o.op)}</span>
                {o.why ? <p className="text-[11.5px] text-steel">{o.why}</p> : null}
              </li>
            ))}
          </ul>
          {(it.opCount ?? 0) > ops.length ? <p className="mt-xs text-[11.5px] text-stone">외 {(it.opCount ?? 0) - ops.length}개 — 관리자 [온톨로지 › 변경 제안]에서 모두 볼 수 있습니다.</p> : null}
          {it.warnings?.length ? (
            <Collapse label={`검증 경고 ${it.warnings.length}건`}>
              <ul className="text-[11.5px] text-attention">
                {it.warnings.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
            </Collapse>
          ) : null}
        </div>
      </div>
      {it.status === "pending" && !it.canReview ? <p className="mt-md text-[12px] text-stone">본인이 만든 제안입니다 — 다른 책임자나 관리자가 처리합니다.</p> : null}
      {it.status === "pending" && it.canReview ? (
        <div className="mt-lg flex flex-wrap gap-xs border-t border-hairline-soft pt-md" data-proposal-review={it.id}>
          <Button size="sm" variant="confirm" disabled={busy} onClick={approve}>
            승인하고 적용
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={async () => {
              const reason = await reject("온톨로지 변경 제안을 반려할까요?", "반려하면 구축 에이전트가 같은 연산을 다시 제안하지 않습니다. 관리자가 [온톨로지 › 변경 제안]에서 다시 검토로 되돌릴 수 있습니다.");
              if (typeof reason === "string" && reason) await run(() => apiPost(`${base}/reject`, { note: reason }), "반려했습니다", reload);
            }}
          >
            반려…
          </Button>
        </div>
      ) : null}
    </Card>
  );
}
