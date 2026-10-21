"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { AdminPage, Card, Check, Loading, Select, Tabs, TextInput, useAction, useApiData } from "@/components/admin/kit";
import { OrgPicker } from "@/components/admin/OrgPicker";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPut } from "@/lib/api-client";
import { bandOf, type Band, type Tone } from "@/lib/uiConfig";

/** 관리자 [화면 설정] (Phase K · 요구사항 §27 HC-01~03 · SCP-01 · Q148~Q151) — GET /admin/ui-config 의 값 · 기본값 · 선택지 */
interface Meta {
  bandKeys: Record<string, string>;
  thresholdKeys: Record<string, { label: string; min: number; max: number }>;
  goalRoles: Record<string, string>;
  labelGroups: Record<string, string>;
  tones: Tone[];
  verdicts: string[];
  scopeKinds: string[];
  goals: { id: string; title: string }[];
  orgs: { code: string; name: string; unitType: string | null }[];
  sections: string[];
  countKeys: string[];
  values: Record<string, unknown>;
  defaults: Record<string, unknown>;
  descriptions: Record<string, string>;
}
type Bands = Record<string, Band[]>;
type ScopesCfg = Record<string, { label: string; units: { org: string | null; section: string }[] }>;
type Notice = { countKey: string; label: string; fallback?: boolean };
type Example = { q: string; hint: string };

type TabKey = "bands" | "thresholds" | "goals" | "scopes" | "examples" | "notices" | "issues" | "labels";
const TABS: { key: TabKey; label: string }[] = [
  { key: "bands", label: "판정 구간" },
  { key: "thresholds", label: "기준값" },
  { key: "goals", label: "목표 역할" },
  { key: "scopes", label: "업무 영역" },
  { key: "examples", label: "예시 질문" },
  { key: "notices", label: "알림" },
  { key: "issues", label: "주요 이슈 순서" },
  { key: "labels", label: "표시 이름" },
];
const TONE_LABEL: Record<Tone, string> = { neutral: "기본(회색)", info: "정보(보라)", positive: "좋음(초록)", attention: "주의(주황)", critical: "위험(빨강)" };
const VERDICT_LABEL: Record<string, string> = { breach: "한도 초과", below: "목표 미달", near_limit: "한도 근접", on_track: "정상" };
const KIND_LABEL: Record<string, string> = { hq: "종합기획(hq)", dept: "사업부서(dept)", branch: "영업점(branch)" };
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v ?? null)) as T;

/**
 * 화면 설정 — 화면 코드에 두던 판정 기준 · 목록 · 목표 지정을 여기서 바꾼다. 저장하면 모든 사용자의 다음 화면부터 같은 값이 쓰인다.
 * 항목마다 저장 전 서버가 형식을 검사한다(구간 오름차순 · 목표 · 조직 존재 등).
 */
export default function AdminUiSettings() {
  const meta = useApiData<Meta>("/admin/ui-config");
  const [tab, setTab] = useState<TabKey>("bands");
  const m = meta.data;
  return (
    <AdminPage
      title="화면 설정"
      description="화면의 판정 구간 · 기준값 · 화면이 집어 쓰는 목표 · 업무 영역(부서 · 영업점) · 예시 질문 · 알림 목록을 정합니다. 저장하면 다음 화면부터 모든 사용자에게 같은 값이 적용되고 감사 로그에 남습니다."
    >
      <Loading error={meta.error} loading={!m && meta.loading} />
      {m ? (
        <>
          <Tabs tabs={TABS} active={tab} onChange={setTab} />
          {tab === "bands" ? <BandsForm meta={m} reload={meta.reload} /> : null}
          {tab === "thresholds" ? <ThresholdsForm meta={m} reload={meta.reload} /> : null}
          {tab === "goals" ? <GoalRolesForm meta={m} reload={meta.reload} /> : null}
          {tab === "scopes" ? <ScopesForm meta={m} reload={meta.reload} /> : null}
          {tab === "examples" ? <ExamplesForm meta={m} reload={meta.reload} /> : null}
          {tab === "notices" ? <NoticesForm meta={m} reload={meta.reload} /> : null}
          {tab === "issues" ? <IssueOrderForm meta={m} reload={meta.reload} /> : null}
          {tab === "labels" ? <LabelsForm meta={m} reload={meta.reload} /> : null}
        </>
      ) : null}
    </AdminPage>
  );
}

/** 저장 · 기본값 되돌리기 — 저장 뒤 셸(메뉴 · 설정)을 다시 받는다 */
function useSave(key: string, reload: () => unknown) {
  const { run, busy } = useAction();
  const router = useRouter();
  const save = (value: unknown, msg = "저장했습니다 — 다음 화면부터 적용됩니다") =>
    run(() => apiPut(`/admin/settings/${encodeURIComponent(key)}`, { value }), msg, async () => {
      await reload();
      router.refresh();
    });
  return { save, busy };
}

function FormCard({ title, settingKey, meta, children, onSave, onReset, busy }: { title: string; settingKey: string; meta: Meta; children: ReactNode; onSave: () => void; onReset: () => void; busy: boolean }) {
  return (
    <Card
      title={title}
      actions={
        <div className="flex flex-wrap gap-xs">
          <Button size="sm" variant="quiet" disabled={busy} onClick={onReset}>
            기본값 불러오기
          </Button>
          <Button size="sm" variant="confirm" disabled={busy} onClick={onSave}>
            저장
          </Button>
        </div>
      }
    >
      <p className="mb-md text-[12px] leading-relaxed text-steel">
        <span className="font-mono text-[11.5px] text-stone">{settingKey}</span> · {meta.descriptions[settingKey]}
      </p>
      {children}
    </Card>
  );
}

const rowBtn = "rounded-md border border-hairline-soft px-2 py-1 text-[12px] font-bold text-charcoal hover:bg-surface-soft disabled:opacity-40";

/* ── 판정 구간 ─────────────────────────────────────── */
function BandsForm({ meta, reload }: { meta: Meta; reload: () => unknown }) {
  const [v, setV] = useState<Bands>(() => clone(meta.values["ui.bands"] as Bands));
  const [probe, setProbe] = useState<Record<string, string>>({});
  const { save, busy } = useSave("ui.bands", reload);
  const set = (k: string, rows: Band[]) => setV((p) => ({ ...p, [k]: rows }));
  return (
    <FormCard title="판정 구간" settingKey="ui.bands" meta={meta} busy={busy} onSave={() => void save(v)} onReset={() => setV(clone(meta.defaults["ui.bands"] as Bands))}>
      <div className="grid grid-cols-1 gap-lg xl:grid-cols-2">
        {Object.entries(meta.bandKeys).map(([k, desc]) => {
          const rows = v[k] ?? [];
          const test = Number(probe[k]);
          const hit = probe[k] !== undefined && probe[k] !== "" && Number.isFinite(test) ? bandOf(test, rows) : null;
          return (
            <section key={k} className="rounded-xl border border-hairline-soft p-md" data-band-key={k}>
              <h3 className="text-[13px] font-bold text-ink-deep">{desc}</h3>
              <table className="mt-sm w-full text-[12.5px]">
                <thead>
                  <tr className="text-left text-stone">
                    <th className="py-1 font-medium">미만(상한)</th>
                    <th className="py-1 font-medium">이름</th>
                    <th className="py-1 font-medium">색</th>
                    <th className="py-1" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((b, i) => {
                    const last = i === rows.length - 1;
                    return (
                      <tr key={i}>
                        <td className="py-1 pr-2">
                          {last ? (
                            <span className="text-stone">그 이상 전부</span>
                          ) : (
                            <TextInput ariaLabel={`${desc} ${i + 1}번째 상한`} type="number" value={b.max ?? ""} onChange={(x) => set(k, rows.map((r, j) => (j === i ? { ...r, max: x === "" ? null : Number(x) } : r)))} className="w-[110px]" />
                          )}
                        </td>
                        <td className="py-1 pr-2">
                          <TextInput ariaLabel={`${desc} ${i + 1}번째 이름`} value={b.label} onChange={(x) => set(k, rows.map((r, j) => (j === i ? { ...r, label: x } : r)))} />
                        </td>
                        <td className="py-1 pr-2">
                          <Select ariaLabel={`${desc} ${i + 1}번째 색`} value={b.tone} onChange={(x) => set(k, rows.map((r, j) => (j === i ? { ...r, tone: x as Tone } : r)))} options={meta.tones.map((t) => ({ value: t, label: TONE_LABEL[t] }))} />
                        </td>
                        <td className="py-1 text-right">
                          <button type="button" className={rowBtn} disabled={rows.length <= 1} onClick={() => set(k, normalizeLast(rows.filter((_, j) => j !== i)))}>
                            삭제
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="mt-sm flex flex-wrap items-end gap-sm">
                <button
                  type="button"
                  className={rowBtn}
                  disabled={rows.length >= 8}
                  onClick={() => {
                    const prev = rows.length >= 2 ? rows[rows.length - 2].max : null;
                    const add: Band = { max: (prev ?? 0) + 1, label: "새 구간", tone: "neutral" };
                    set(k, [...rows.slice(0, -1), add, ...rows.slice(-1)]);
                  }}
                >
                  구간 추가
                </button>
                <TextInput label="값 넣어 보기" type="number" value={probe[k] ?? ""} onChange={(x) => setProbe((p) => ({ ...p, [k]: x }))} className="w-[120px]" />
                <span className="pb-2 text-[12.5px]" aria-live="polite">
                  {hit ? <Badge tone={hit.tone === "positive" ? "success" : hit.tone}>{hit.label}</Badge> : null}
                </span>
              </div>
            </section>
          );
        })}
      </div>
    </FormCard>
  );
}
/** 마지막 구간은 상한 없음 */
function normalizeLast(rows: Band[]): Band[] {
  return rows.map((r, i) => (i === rows.length - 1 ? { ...r, max: null } : r));
}

/* ── 기준값 ─────────────────────────────────────── */
function ThresholdsForm({ meta, reload }: { meta: Meta; reload: () => unknown }) {
  const [v, setV] = useState<Record<string, number | string>>(() => clone(meta.values["ui.thresholds"] as Record<string, number>));
  const { save, busy } = useSave("ui.thresholds", reload);
  const out = () => Object.fromEntries(Object.entries(v).map(([k, x]) => [k, Number(x)]));
  return (
    <FormCard title="기준값" settingKey="ui.thresholds" meta={meta} busy={busy} onSave={() => void save(out())} onReset={() => setV(clone(meta.defaults["ui.thresholds"] as Record<string, number>))}>
      <div className="grid grid-cols-1 gap-md md:grid-cols-2">
        {Object.entries(meta.thresholdKeys).map(([k, d]) => (
          <div key={k}>
            <TextInput label={d.label} type="number" value={v[k] ?? ""} onChange={(x) => setV((p) => ({ ...p, [k]: x }))} className="max-w-[200px]" />
            <p className="mt-0.5 text-[11.5px] text-stone">
              {d.min} ~ {d.max}
            </p>
          </div>
        ))}
      </div>
    </FormCard>
  );
}

/* ── 목표 역할 ─────────────────────────────────────── */
function GoalRolesForm({ meta, reload }: { meta: Meta; reload: () => unknown }) {
  const [v, setV] = useState<Record<string, string | null>>(() => clone(meta.values["ui.goal_roles"] as Record<string, string | null>));
  const { save, busy } = useSave("ui.goal_roles", reload);
  const options = [{ value: "", label: "지정 안 함(그 자리를 표시하지 않음)" }, ...meta.goals.map((g) => ({ value: g.id, label: `${g.title} (${g.id})` }))];
  return (
    <FormCard title="목표 역할" settingKey="ui.goal_roles" meta={meta} busy={busy} onSave={() => void save(v)} onReset={() => setV(clone(meta.defaults["ui.goal_roles"] as Record<string, string | null>))}>
      <div className="flex flex-col gap-md">
        {Object.entries(meta.goalRoles).map(([role, desc]) => (
          <Select key={role} label={desc} value={v[role] ?? ""} onChange={(x) => setV((p) => ({ ...p, [role]: x || null }))} options={options} className="max-w-[640px]" />
        ))}
      </div>
    </FormCard>
  );
}

/* ── 업무 영역 ─────────────────────────────────────── */
function ScopesForm({ meta, reload }: { meta: Meta; reload: () => unknown }) {
  const [v, setV] = useState<ScopesCfg>(() => clone(meta.values["ui.scopes"] as ScopesCfg));
  const { save, busy } = useSave("ui.scopes", reload);
  // 조직이 수천 곳이어도 단위마다 전체 목록을 그리지 않게 검색형 선택 상자로 — 이름은 양식 정보(meta.orgs)에서
  const orgName = new Map(meta.orgs.map((o) => [o.code, o.name]));
  const setKind = (kind: string, patch: Partial<ScopesCfg[string]>) => setV((p) => ({ ...p, [kind]: { ...(p[kind] ?? { label: "", units: [] }), ...patch } }));
  return (
    <FormCard title="업무 영역" settingKey="ui.scopes" meta={meta} busy={busy} onSave={() => void save(v)} onReset={() => setV(clone(meta.defaults["ui.scopes"] as ScopesCfg))}>
      <p className="mb-md text-[12px] leading-relaxed text-charcoal">
        단위 = 조직 + 메뉴 묶음(화면 권한의 section). 메뉴 묶음에 화면이 있으면 영역 전환에서 고를 수 있고, 아직 없으면 &lsquo;준비 중&rsquo;으로 보입니다. 새 부서는 [화면 권한]에서 화면을 등록(묶음 = 부서 이름)한 뒤 여기에 한 줄을
        더하면 됩니다. 영업점 지점은 판정 규칙 BRANCH_SCOPE 의 계산 대상 지점입니다.
      </p>
      <datalist id="ui-sections">
        {meta.sections.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <div className="flex flex-col gap-lg">
        {meta.scopeKinds.map((kind) => {
          const spec = v[kind] ?? { label: "", units: [] };
          return (
            <section key={kind} className="rounded-xl border border-hairline-soft p-md" data-scope-kind={kind}>
              <div className="flex flex-wrap items-end gap-md">
                <h3 className="pb-2 text-[13px] font-bold text-ink-deep">{KIND_LABEL[kind] ?? kind}</h3>
                <TextInput label="영역 이름(헤더 전환)" value={spec.label} onChange={(x) => setKind(kind, { label: x })} className="w-[180px]" />
              </div>
              <ul className="mt-sm flex flex-col gap-xs">
                {spec.units.map((u, i) => (
                  <li key={i} className="flex flex-wrap items-end gap-sm">
                    <OrgPicker
                      label={i === 0 ? "조직" : undefined}
                      ariaLabel={`${kind} ${i + 1}번째 조직`}
                      value={u.org ?? ""}
                      valueLabel={u.org ? orgName.get(u.org) : undefined}
                      empty="조직 없음(영업점 묶음 등)"
                      onChange={(x) => setKind(kind, { units: spec.units.map((w, j) => (j === i ? { ...w, org: x || null } : w)) })}
                      className="w-[260px]"
                    />
                    <label className="block w-[220px]">
                      {i === 0 ? <span className="mb-1 block text-[12px] font-bold text-charcoal">메뉴 묶음</span> : null}
                      <input
                        list="ui-sections"
                        aria-label={`${kind} ${i + 1}번째 메뉴 묶음`}
                        value={u.section}
                        onChange={(e) => setKind(kind, { units: spec.units.map((w, j) => (j === i ? { ...w, section: e.target.value } : w)) })}
                        className="input"
                      />
                    </label>
                    {meta.sections.includes(u.section) ? <Badge tone="success">화면 있음</Badge> : <Badge tone="neutral">준비 중</Badge>}
                    <button type="button" className={rowBtn} onClick={() => setKind(kind, { units: spec.units.filter((_, j) => j !== i) })}>
                      삭제
                    </button>
                  </li>
                ))}
              </ul>
              <button type="button" className={`${rowBtn} mt-sm`} onClick={() => setKind(kind, { units: [...spec.units, { org: null, section: "" }] })}>
                단위 추가
              </button>
            </section>
          );
        })}
      </div>
    </FormCard>
  );
}

/* ── 예시 질문 ─────────────────────────────────────── */
function ExamplesForm({ meta, reload }: { meta: Meta; reload: () => unknown }) {
  const [rows, setRows] = useState<Example[]>(() => clone((meta.values["ui.examples"] as { assist?: Example[] }).assist ?? []));
  const { save, busy } = useSave("ui.examples", reload);
  return (
    <FormCard title="예시 질문 (AI 어시스턴트 첫 화면)" settingKey="ui.examples" meta={meta} busy={busy} onSave={() => void save({ assist: rows })} onReset={() => setRows(clone((meta.defaults["ui.examples"] as { assist?: Example[] }).assist ?? []))}>
      <ul className="flex flex-col gap-xs">
        {rows.map((r, i) => (
          <li key={i} className="flex flex-wrap items-end gap-sm">
            <TextInput label={i === 0 ? "질문" : undefined} ariaLabel={`${i + 1}번째 질문`} value={r.q} onChange={(x) => setRows((p) => p.map((w, j) => (j === i ? { ...w, q: x } : w)))} className="min-w-[320px] flex-1" />
            <TextInput label={i === 0 ? "설명(짧게)" : undefined} ariaLabel={`${i + 1}번째 설명`} value={r.hint} onChange={(x) => setRows((p) => p.map((w, j) => (j === i ? { ...w, hint: x } : w)))} className="w-[200px]" />
            <button type="button" className={rowBtn} onClick={() => setRows((p) => p.filter((_, j) => j !== i))}>
              삭제
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className={`${rowBtn} mt-sm`} disabled={rows.length >= 8} onClick={() => setRows((p) => [...p, { q: "", hint: "" }])}>
        질문 추가
      </button>
    </FormCard>
  );
}

/* ── 알림 ─────────────────────────────────────── */
function NoticesForm({ meta, reload }: { meta: Meta; reload: () => unknown }) {
  const [rows, setRows] = useState<Notice[]>(() => clone(meta.values["ui.notices"] as Notice[]));
  const { save, busy } = useSave("ui.notices", reload);
  const keys = [...new Set([...meta.countKeys, ...rows.map((r) => r.countKey)])].map((k) => ({ value: k, label: k }));
  return (
    <FormCard title="알림 목록 (헤더 종)" settingKey="ui.notices" meta={meta} busy={busy} onSave={() => void save(rows)} onReset={() => setRows(clone(meta.defaults["ui.notices"] as Notice[]))}>
      <p className="mb-md text-[12px] text-charcoal">건수 키는 화면 권한의 건수 키(count_key)입니다 — 알림을 누르면 그 건수를 가진 화면으로 이동하고, 화면 권한이 없는 사용자에게는 보이지 않습니다.</p>
      <ul className="flex flex-col gap-xs">
        {rows.map((r, i) => (
          <li key={i} className="flex flex-wrap items-end gap-sm">
            <Select label={i === 0 ? "건수 키" : undefined} ariaLabel={`${i + 1}번째 건수 키`} value={r.countKey} onChange={(x) => setRows((p) => p.map((w, j) => (j === i ? { ...w, countKey: x } : w)))} options={keys} className="w-[200px]" />
            <TextInput label={i === 0 ? "알림 이름" : undefined} ariaLabel={`${i + 1}번째 알림 이름`} value={r.label} onChange={(x) => setRows((p) => p.map((w, j) => (j === i ? { ...w, label: x } : w)))} className="w-[260px]" />
            <Check label="다른 알림이 없을 때만" checked={Boolean(r.fallback)} onChange={(x) => setRows((p) => p.map((w, j) => (j === i ? { ...w, fallback: x } : w)))} />
            <button type="button" className={rowBtn} onClick={() => setRows((p) => p.filter((_, j) => j !== i))}>
              삭제
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className={`${rowBtn} mt-sm`} disabled={rows.length >= 20} onClick={() => setRows((p) => [...p, { countKey: meta.countKeys[0] ?? "", label: "" }])}>
        알림 추가
      </button>
    </FormCard>
  );
}

/* ── 주요 이슈 순서 ─────────────────────────────────────── */
function IssueOrderForm({ meta, reload }: { meta: Meta; reload: () => unknown }) {
  const [order, setOrder] = useState<string[]>(() => clone(meta.values["ui.issue_order"] as string[]));
  const { save, busy } = useSave("ui.issue_order", reload);
  const move = (i: number, d: number) => setOrder((p) => {
    const next = [...p];
    const j = i + d;
    if (j < 0 || j >= next.length) return p;
    [next[i], next[j]] = [next[j], next[i]];
    return next;
  });
  const off = meta.verdicts.filter((x) => !order.includes(x));
  return (
    <FormCard title="주요 이슈 순서 (종합 현황)" settingKey="ui.issue_order" meta={meta} busy={busy} onSave={() => void save(order)} onReset={() => setOrder(clone(meta.defaults["ui.issue_order"] as string[]))}>
      <ol className="flex flex-col gap-xs">
        {order.map((x, i) => (
          <li key={x} className="flex items-center gap-sm text-[13px]">
            <span className="w-6 text-right tnum text-stone">{i + 1}</span>
            <span className="w-[140px] font-bold text-ink-deep">{VERDICT_LABEL[x] ?? x}</span>
            <button type="button" className={rowBtn} disabled={i === 0} onClick={() => move(i, -1)} aria-label={`${VERDICT_LABEL[x] ?? x} 위로`}>
              위로
            </button>
            <button type="button" className={rowBtn} disabled={i === order.length - 1} onClick={() => move(i, 1)} aria-label={`${VERDICT_LABEL[x] ?? x} 아래로`}>
              아래로
            </button>
            <button type="button" className={rowBtn} onClick={() => setOrder((p) => p.filter((y) => y !== x))}>
              빼기
            </button>
          </li>
        ))}
      </ol>
      {off.length ? (
        <p className="mt-sm flex flex-wrap items-center gap-xs text-[12.5px] text-steel">
          이슈로 보지 않는 판정:
          {off.map((x) => (
            <button key={x} type="button" className={rowBtn} onClick={() => setOrder((p) => [...p, x])}>
              + {VERDICT_LABEL[x] ?? x}
            </button>
          ))}
        </p>
      ) : null}
    </FormCard>
  );
}

/* ── 표시 이름 ─────────────────────────────────────── */
function LabelsForm({ meta, reload }: { meta: Meta; reload: () => unknown }) {
  type Labels = Record<string, Record<string, string>>;
  const toRows = (l: Labels) => Object.fromEntries(Object.keys(meta.labelGroups).map((g) => [g, Object.entries(l?.[g] ?? {})]));
  const [rows, setRows] = useState<Record<string, [string, string][]>>(() => toRows(meta.values["ui.labels"] as Labels));
  const { save, busy } = useSave("ui.labels", reload);
  const out = () => Object.fromEntries(Object.entries(rows).map(([g, list]) => [g, Object.fromEntries(list.filter(([k]) => k.trim()).map(([k, x]) => [k.trim(), x.trim()]))]));
  const set = (g: string, list: [string, string][]) => setRows((p) => ({ ...p, [g]: list }));
  return (
    <FormCard title="표시 이름 · 연결" settingKey="ui.labels" meta={meta} busy={busy} onSave={() => void save(out())} onReset={() => setRows(toRows(meta.defaults["ui.labels"] as Labels))}>
      <div className="grid grid-cols-1 gap-lg xl:grid-cols-2">
        {Object.entries(meta.labelGroups).map(([g, desc]) => (
          <section key={g} className="rounded-xl border border-hairline-soft p-md">
            <h3 className="text-[13px] font-bold text-ink-deep">{desc}</h3>
            <ul className="mt-sm flex flex-col gap-xs">
              {(rows[g] ?? []).map(([k, x], i) => (
                <li key={i} className="flex items-end gap-sm">
                  <TextInput ariaLabel={`${desc} ${i + 1}번째 코드`} value={k} onChange={(y) => set(g, (rows[g] ?? []).map((w, j) => (j === i ? [y, w[1]] : w)))} mono className="w-[160px]" />
                  <TextInput ariaLabel={`${desc} ${i + 1}번째 값`} value={x} onChange={(y) => set(g, (rows[g] ?? []).map((w, j) => (j === i ? [w[0], y] : w)))} className="flex-1" />
                  <button type="button" className={rowBtn} onClick={() => set(g, (rows[g] ?? []).filter((_, j) => j !== i))}>
                    삭제
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" className={`${rowBtn} mt-sm`} onClick={() => set(g, [...(rows[g] ?? []), ["", ""]])}>
              추가
            </button>
          </section>
        ))}
      </div>
    </FormCard>
  );
}
