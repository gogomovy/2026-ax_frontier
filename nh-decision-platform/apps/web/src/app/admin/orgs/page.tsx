"use client";

import { useDeferredValue, useMemo, useState } from "react";
import { AdminPage, C, Card, Check, Loading, Select, Table, TextInput, useAction, useApiData } from "@/components/admin/kit";
import { OrgPicker, forgetOrgNames } from "@/components/admin/OrgPicker";
import { useConfirm } from "@/components/providers/UiProvider";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPatch, apiPost } from "@/lib/api-client";
import { buildOrgTree, orgMatches } from "@/lib/orgLookup";

interface OrgRow {
  code: string;
  name: string;
  level: number;
  unitType: string | null;
  unitLabel: string;
  parent: string | null;
  sort: number;
  active: boolean;
  users: number;
}
interface UnitType {
  code: string;
  label: string;
  parents: string[];
}

/** 한 번에 그리는 행 수 — 인사 동기화로 조직이 수천 곳이어도 화면이 멈추지 않게. [더 보기]로 늘린다 */
const ROW_STEP = 200;

/** 조직 — 본부 > 부 > 국 > 팀 / 지역본부 > 영업점. 화면 권한은 상위 조직에서 하위로 상속된다 (ADM-03, Q12) */
export default function OrgsAdmin() {
  const data = useApiData<{ unitTypes: UnitType[]; orgs: OrgRow[] }>("/admin/orgs");
  const { run, busy } = useAction();
  const confirm = useConfirm();
  const types = useMemo(() => data.data?.unitTypes ?? [], [data.data]);
  const orgs = useMemo(() => data.data?.orgs ?? [], [data.data]);
  const [form, setForm] = useState({ code: "", name: "", unit_type: "DEPT", parent_code: "", parent_name: "" });
  const [sortText, setSortText] = useState("0");
  const [text, setText] = useState("");
  const q = useDeferredValue(text.trim());
  /** 펼친 조직 — null 이면 기본(최상위 조직만 펼침 = 2단계까지 보임) */
  const [expanded, setExpanded] = useState<Set<string> | null>(null);
  const [limit, setLimit] = useState(ROW_STEP);

  // 트리 순서 · 하위 수 · 경로를 한 번에(O(N)) — 예전에는 조직마다 전체를 다시 훑었다
  const tree = useMemo(() => buildOrgTree(orgs), [orgs]);
  const roots = tree.kids.get(null) ?? [];
  const open = useMemo(() => expanded ?? new Set((tree.kids.get(null) ?? []).map((o) => o.code)), [expanded, tree]);

  const rows = useMemo(() => {
    if (q) return tree.order.filter((o) => orgMatches(o, tree.path(o.code).slice(0, -1).map((x) => x.name), q));
    const out: OrgRow[] = [];
    const stack = [...(tree.kids.get(null) ?? [])].reverse();
    const seen = new Set<string>();
    while (stack.length) {
      const o = stack.pop()!;
      if (seen.has(o.code)) continue;
      seen.add(o.code);
      out.push(o);
      if (open.has(o.code)) stack.push(...[...(tree.kids.get(o.code) ?? [])].reverse());
    }
    return out;
  }, [q, tree, open]);
  const shown = rows.slice(0, limit);

  const toggle = (code: string) =>
    setExpanded(() => {
      const next = new Set(open);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  const allowedParents = (unitType: string) => types.find((t) => t.code === unitType)?.parents ?? [];
  const typeOptions = types.map((t) => ({ value: t.code, label: t.label }));
  const reload = () => {
    forgetOrgNames();
    return data.reload();
  };
  const move = async (o: OrgRow, parent: string, to: string, below: number) => {
    const ok = await confirm({ title: "상위 조직을 바꿀까요?", body: `${o.name}과(와) 하위 조직 ${below.toLocaleString("ko-KR")}곳이 ${to} 아래로 옮겨지고, 상속되는 화면 권한이 새 위치 기준으로 바뀝니다.`, confirmLabel: "옮기기" });
    if (ok) await run(() => apiPatch(`/admin/orgs/${o.code}`, { parent_code: parent || null }), "상위 조직을 바꿨습니다 (하위 조직 함께 이동)", reload);
  };
  const inactive = orgs.filter((o) => !o.active).length;

  return (
    <AdminPage
      title="조직"
      description={`조직 유형: ${types.map((t) => t.label).join(" · ")}. 본점은 본부 > 부 > 국 > 팀, 영업 조직은 지역본부 > 영업점(지역본부 직속 국·팀 허용)입니다. 유형과 허용 상위 유형은 [시스템 상태 > 운영 설정값]의 org.unit_types 에서 바꿀 수 있습니다.`}
    >
      <Card title="조직 추가">
        <div className="grid grid-cols-2 gap-md md:grid-cols-6">
          <TextInput label="코드" value={form.code} onChange={(v) => setForm({ ...form, code: v.toUpperCase() })} mono />
          <TextInput label="이름" value={form.name} onChange={(v) => setForm({ ...form, name: v })} className="md:col-span-2" />
          <Select label="유형" value={form.unit_type} onChange={(v) => setForm({ ...form, unit_type: v, parent_code: "", parent_name: "" })} options={typeOptions} />
          {allowedParents(form.unit_type).length ? (
            <OrgPicker
              label="상위 조직"
              value={form.parent_code}
              valueLabel={form.parent_name || undefined}
              types={allowedParents(form.unit_type)}
              placeholder="상위 조직 선택"
              onChange={(code, o) => setForm({ ...form, parent_code: code, parent_name: o?.name ?? "" })}
            />
          ) : (
            <div>
              <span className="mb-1 block text-[11.5px] font-bold text-steel">상위 조직</span>
              <p className="flex h-9 items-center text-[13px] text-stone">(최상위)</p>
            </div>
          )}
          <TextInput label="정렬" value={sortText} onChange={setSortText} type="number" />
        </div>
        <Button
          size="sm"
          variant="confirm"
          className="mt-md"
          disabled={busy || !form.code || !form.name}
          onClick={() =>
            run(
              () => apiPost("/admin/orgs", { code: form.code, name: form.name, unit_type: form.unit_type, parent_code: form.parent_code || null, sort: Number(sortText) }),
              "조직을 추가했습니다",
              () => {
                setForm({ ...form, code: "", name: "" });
                setSortText("0");
                return reload();
              },
            )
          }
        >
          추가
        </Button>
      </Card>
      <Card
        title="조직 트리"
        actions={
          q ? null : (
            <>
              <Button size="sm" variant="quiet" onClick={() => setExpanded(new Set())} disabled={!open.size}>
                모두 접기
              </Button>
              <Button size="sm" variant="quiet" onClick={() => setExpanded(null)}>
                처음처럼(2단계)
              </Button>
            </>
          )
        }
      >
        <div className="mb-md flex flex-wrap items-end gap-md" role="search" aria-label="조직 찾기">
          <TextInput
            label="찾기"
            value={text}
            onChange={(v) => {
              setText(v);
              setLimit(ROW_STEP);
            }}
            placeholder="이름 · 코드 · 상위 조직 이름"
            className="w-[300px]"
          />
          <p className="ml-auto text-[12px] text-steel tnum" role="status" aria-live="polite">
            {data.data
              ? q
                ? `맞는 조직 ${rows.length.toLocaleString("ko-KR")}곳`
                : `전체 ${orgs.length.toLocaleString("ko-KR")}곳${inactive ? ` (사용 안 함 ${inactive.toLocaleString("ko-KR")})` : ""} · 최상위 ${roots.length.toLocaleString("ko-KR")}곳`
              : ""}
          </p>
        </div>
        <Loading error={data.error} loading={!data.data && data.loading} />
        <Table head={["조직", "코드", "유형", "상위 조직", "사용자", "정렬", "사용", "이름 변경"]}>
          {shown.map((o) => {
            const kids = tree.kids.get(o.code)?.length ?? 0;
            const below = tree.below.get(o.code) ?? 0;
            const allowed = allowedParents(o.unitType ?? "");
            const above = q ? tree.path(o.code).slice(0, -1).map((x) => x.name) : [];
            return (
              <tr key={o.code} className={o.active ? "" : "opacity-50"}>
                <C>
                  <span style={{ paddingLeft: q ? 0 : (o.level - 1) * 20 }} className="inline-flex items-start gap-1">
                    {!q && kids ? (
                      <button
                        type="button"
                        onClick={() => toggle(o.code)}
                        aria-expanded={open.has(o.code)}
                        aria-label={`${o.name} 하위 조직 ${below.toLocaleString("ko-KR")}곳 ${open.has(o.code) ? "접기" : "펼치기"}`}
                        className="w-4 shrink-0 text-left text-steel"
                      >
                        {open.has(o.code) ? "▾" : "▸"}
                      </button>
                    ) : (
                      <span className="w-4 shrink-0 text-stone" aria-hidden="true">
                        {!q && o.level > 1 ? "└" : ""}
                      </span>
                    )}
                    <span>
                      <span className={o.level === 1 ? "font-bold text-ink-deep" : ""}>{o.name}</span>
                      {!q && kids && !open.has(o.code) ? <span className="ml-1 text-[10.5px] text-stone tnum">하위 {below.toLocaleString("ko-KR")}</span> : null}
                      {above.length ? <span className="block text-[10.5px] text-stone">{above.join(" > ")}</span> : null}
                    </span>
                  </span>
                </C>
                <C mono>{o.code}</C>
                <C>
                  <Badge tone={o.unitType === "REGION" || o.unitType === "BRANCH" ? "info" : o.unitType === "HQ_DIV" ? "dark" : "neutral"}>{o.unitLabel}</Badge>
                </C>
                <C className="min-w-[200px]">
                  {allowed.length ? (
                    <OrgPicker
                      value={o.parent ?? ""}
                      valueLabel={o.parent ? (tree.by.get(o.parent)?.name ?? o.parent) : undefined}
                      types={allowed}
                      exclude={o.code}
                      placeholder="상위 조직 선택"
                      includeInactive
                      disabled={busy}
                      ariaLabel={`${o.name} 상위 조직`}
                      onChange={(v, picked) => void move(o, v, picked?.name ?? v, below)}
                    />
                  ) : o.parent ? (
                    // 최상위 유형인데 상위가 걸려 있다(동기화 · 유형 설정 변경 뒤) — 최상위로만 옮길 수 있다
                    <span className="flex items-center gap-xs text-[12px] text-charcoal">
                      {tree.by.get(o.parent)?.name ?? o.parent}
                      <Button size="sm" variant="quiet" disabled={busy} onClick={() => void move(o, "", "없음(최상위)", below)}>
                        최상위로
                      </Button>
                    </span>
                  ) : (
                    <span className="text-[12px] text-stone">(최상위)</span>
                  )}
                </C>
                <C right>{o.users.toLocaleString("ko-KR")}</C>
                <C right>{o.sort}</C>
                <C>
                  <Check label="" ariaLabel={`${o.name} 사용`} checked={o.active} disabled={busy} onChange={(v) => run(() => apiPatch(`/admin/orgs/${o.code}`, { active: v }), v ? "사용으로 바꿨습니다" : "사용 중지했습니다", reload)} />
                </C>
                <C>
                  <Button
                    size="sm"
                    variant="quiet"
                    disabled={busy}
                    aria-label={`${o.name} 이름 변경`}
                    onClick={async () => {
                      const name = await confirm({ title: "조직 이름 바꾸기", confirmLabel: "저장", input: { label: "새 이름", initial: o.name, validate: (v) => (v.trim() ? (v.trim().length > 100 ? "100자 이하로 입력하세요" : null) : "이름을 입력하세요") } });
                      if (typeof name === "string" && name.trim() && name.trim() !== o.name) await run(() => apiPatch(`/admin/orgs/${o.code}`, { name: name.trim() }), "이름을 바꿨습니다", reload);
                    }}
                  >
                    변경
                  </Button>
                </C>
              </tr>
            );
          })}
        </Table>
        {data.data && !rows.length ? <p className="py-lg text-center text-[12.5px] text-stone">{q ? "맞는 조직이 없습니다." : "조직이 없습니다."}</p> : null}
        {rows.length > shown.length ? (
          <div className="mt-md flex items-center justify-center gap-sm text-[12px] text-steel">
            <span className="tnum">
              {rows.length.toLocaleString("ko-KR")}곳 중 {shown.length.toLocaleString("ko-KR")}곳 표시
            </span>
            <Button size="sm" variant="ghost" onClick={() => setLimit((n) => n + ROW_STEP)}>
              {Math.min(ROW_STEP, rows.length - shown.length).toLocaleString("ko-KR")}곳 더 보기
            </Button>
          </div>
        ) : null}
      </Card>
    </AdminPage>
  );
}
