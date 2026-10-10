"use client";

import { useState } from "react";
import { AdminPage, C, Card, Check, Loading, Select, Table, TextInput, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPatch, apiPost } from "@/lib/api-client";

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

/** 조직 — 본부 > 부 > 국 > 팀 / 지역본부 > 영업점. 화면 권한은 상위 조직에서 하위로 상속된다 (ADM-03, Q12) */
export default function OrgsAdmin() {
  const data = useApiData<{ unitTypes: UnitType[]; orgs: OrgRow[] }>("/admin/orgs");
  const { run, busy } = useAction();
  const types = data.data?.unitTypes ?? [];
  const orgs = data.data?.orgs ?? [];
  const [form, setForm] = useState({ code: "", name: "", unit_type: "DEPT", parent_code: "", sort: "0" });

  // 트리 순서로 정렬
  const ordered: OrgRow[] = [];
  const walk = (parent: string | null) =>
    orgs
      .filter((o) => o.parent === parent)
      .sort((a, b) => a.sort - b.sort)
      .forEach((o) => {
        ordered.push(o);
        walk(o.code);
      });
  walk(null);

  const allowedParents = (unitType: string) => types.find((t) => t.code === unitType)?.parents ?? [];
  const parentOptions = (unitType: string, self?: string) => {
    const allowed = allowedParents(unitType);
    return [
      ...(allowed.length === 0 ? [{ value: "", label: "(최상위)" }] : [{ value: "", label: "상위 조직 선택" }]),
      ...orgs.filter((o) => o.code !== self && o.unitType && allowed.includes(o.unitType)).map((o) => ({ value: o.code, label: `${o.unitLabel} · ${o.name}` })),
    ];
  };
  const typeOptions = types.map((t) => ({ value: t.code, label: t.label }));

  return (
    <AdminPage
      title="조직"
      description={`조직 유형: ${types.map((t) => t.label).join(" · ")}. 본점은 본부 > 부 > 국 > 팀, 영업 조직은 지역본부 > 영업점(지역본부 직속 국·팀 허용)입니다. 유형과 허용 상위 유형은 [시스템 상태 > 운영 설정값]의 org.unit_types 에서 바꿀 수 있습니다.`}
    >
      <Card title="조직 추가">
        <div className="grid grid-cols-2 gap-md md:grid-cols-6">
          <TextInput label="코드" value={form.code} onChange={(v) => setForm({ ...form, code: v.toUpperCase() })} mono />
          <TextInput label="이름" value={form.name} onChange={(v) => setForm({ ...form, name: v })} className="md:col-span-2" />
          <Select label="유형" value={form.unit_type} onChange={(v) => setForm({ ...form, unit_type: v, parent_code: "" })} options={typeOptions} />
          <Select label="상위 조직" value={form.parent_code} onChange={(v) => setForm({ ...form, parent_code: v })} options={parentOptions(form.unit_type)} />
          <TextInput label="정렬" value={form.sort} onChange={(v) => setForm({ ...form, sort: v })} type="number" />
        </div>
        <Button
          size="sm"
          variant="confirm"
          className="mt-md"
          disabled={busy || !form.code || !form.name}
          onClick={() =>
            run(
              () => apiPost("/admin/orgs", { code: form.code, name: form.name, unit_type: form.unit_type, parent_code: form.parent_code || null, sort: Number(form.sort) }),
              "조직을 추가했습니다",
              () => {
                setForm({ ...form, code: "", name: "", sort: "0" });
                return data.reload();
              },
            )
          }
        >
          추가
        </Button>
      </Card>
      <Card title="조직 트리">
        <Loading error={data.error} loading={!data.data && data.loading} />
        <Table head={["조직", "코드", "유형", "상위 조직", "사용자", "정렬", "사용", "이름 변경"]}>
          {ordered.map((o) => (
            <tr key={o.code} className={o.active ? "" : "opacity-50"}>
              <C>
                <span style={{ paddingLeft: (o.level - 1) * 20 }} className={o.level === 1 ? "font-bold text-ink-deep" : ""}>
                  {o.level > 1 ? "└ " : ""}
                  {o.name}
                </span>
              </C>
              <C mono>{o.code}</C>
              <C>
                <Badge tone={o.unitType === "REGION" || o.unitType === "BRANCH" ? "info" : o.unitType === "HQ_DIV" ? "dark" : "neutral"}>{o.unitLabel}</Badge>
              </C>
              <C className="min-w-[200px]">
                <Select
                  value={o.parent ?? ""}
                  options={parentOptions(o.unitType ?? "", o.code)}
                  onChange={(v) => run(() => apiPatch(`/admin/orgs/${o.code}`, { parent_code: v || null }), "상위 조직을 바꿨습니다 (하위 조직 함께 이동)", data.reload)}
                />
              </C>
              <C right>{o.users}</C>
              <C right>{o.sort}</C>
              <C>
                <Check label="" checked={o.active} onChange={(v) => run(() => apiPatch(`/admin/orgs/${o.code}`, { active: v }), v ? "사용으로 바꿨습니다" : "사용 중지했습니다", data.reload)} />
              </C>
              <C>
                <Button
                  size="sm"
                  variant="quiet"
                  disabled={busy}
                  onClick={() => {
                    const name = window.prompt("새 이름", o.name);
                    if (name && name !== o.name) run(() => apiPatch(`/admin/orgs/${o.code}`, { name }), "이름을 바꿨습니다", data.reload);
                  }}
                >
                  변경
                </Button>
              </C>
            </tr>
          ))}
        </Table>
      </Card>
    </AdminPage>
  );
}
