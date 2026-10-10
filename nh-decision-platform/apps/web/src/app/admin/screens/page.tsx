"use client";

import { useMemo, useState } from "react";
import { AdminPage, C, Card, Loading, Table, TextInput, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPatch, apiPut } from "@/lib/api-client";

interface ScreenRow {
  code: string;
  path: string;
  label: string;
  section: string;
  kind: string;
  adminOnly: boolean;
  active: boolean;
  resources: string[];
}
interface OrgRow {
  code: string;
  name: string;
  level: number;
  parent: string | null;
  active: boolean;
}
interface Data {
  screens: ScreenRow[];
  grants: { org: string; screen: string }[];
  orgs: OrgRow[];
}

/** 화면 × 조직 권한 — 상위 조직에 부여하면 하위 국·팀이 상속한다 (ADM-04, AUTH-08) */
export default function ScreensAdmin() {
  const data = useApiData<Data>("/admin/screens");
  const { run, busy } = useAction();
  const [showAll, setShowAll] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [resText, setResText] = useState("");
  const d = data.data;

  const granted = useMemo(() => new Set((d?.grants ?? []).map((g) => `${g.org}|${g.screen}`)), [d]);
  const orgMap = useMemo(() => Object.fromEntries((d?.orgs ?? []).map((o) => [o.code, o])), [d]);
  const inherited = (org: string, screen: string): string | null => {
    let cur = orgMap[org]?.parent ?? null;
    while (cur) {
      if (granted.has(`${cur}|${screen}`)) return orgMap[cur]?.name ?? cur;
      cur = orgMap[cur]?.parent ?? null;
    }
    return null;
  };
  const orgs = (d?.orgs ?? []).filter((o) => o.active && (showAll || o.level <= 2));
  const screens = (d?.screens ?? []).filter((s) => !s.adminOnly);

  return (
    <AdminPage
      title="화면 권한"
      description="체크한 조직과 그 하위 조직이 화면을 봅니다. API 도 같은 기준(화면이 쓰는 리소스)으로 403 을 반환합니다. 관리자 화면은 관리자 역할만 접근합니다."
      actions={
        <Button size="sm" variant="quiet" onClick={() => setShowAll((v) => !v)}>
          {showAll ? "상위 2단계만 보기" : "전체 조직 보기"}
        </Button>
      }
    >
      <Loading error={data.error} loading={!d && data.loading} />
      {d ? (
        <Card>
          <Table head={["화면", ...orgs.map((o) => <span key={o.code} title={o.code} className={o.level === 1 ? "" : "font-medium text-steel"}>{o.name}</span>)]}>
            {screens.map((s) => (
              <tr key={s.code}>
                <C className="min-w-[200px]">
                  <span className="font-bold text-ink-deep">{s.label}</span> <Badge>{s.section}</Badge>
                  <p className="font-mono text-[10.5px] text-stone">{s.path}</p>
                </C>
                {orgs.map((o) => {
                  const on = granted.has(`${o.code}|${s.code}`);
                  const inh = inherited(o.code, s.code);
                  return (
                    <C key={o.code} className="text-center">
                      <input
                        type="checkbox"
                        aria-label={`${o.name} — ${s.label}`}
                        checked={on}
                        disabled={busy}
                        onChange={(e) => run(() => apiPut("/admin/screens/grants", { org_code: o.code, screen_code: s.code, granted: e.target.checked }), e.target.checked ? "권한을 부여했습니다" : "권한을 회수했습니다", data.reload)}
                      />
                      {!on && inh ? <p className="text-[9.5px] text-success">상속</p> : null}
                    </C>
                  );
                })}
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}
      <Card title="화면 → API 리소스">
        <p className="mb-md text-[12px] text-steel">화면이 호출하는 화면 API 리소스입니다. 권한이 있는 화면의 리소스만 API 에서 허용됩니다.</p>
        <Table head={["화면", "리소스", ""]}>
          {(d?.screens ?? []).filter((s) => !s.adminOnly).map((s) => (
            <tr key={s.code}>
              <C mono>{s.code}</C>
              <C>
                {editing === s.code ? (
                  <TextInput value={resText} onChange={setResText} mono />
                ) : (
                  <span className="font-mono text-[11px] text-charcoal">{s.resources.join(", ") || "-"}</span>
                )}
              </C>
              <C>
                {editing === s.code ? (
                  <Button
                    size="sm"
                    variant="confirm"
                    disabled={busy}
                    onClick={() =>
                      run(() => apiPatch(`/admin/screens/${s.code}`, { resources: resText.split(",").map((x) => x.trim()).filter(Boolean) }), "저장했습니다", async () => {
                        setEditing(null);
                        await data.reload();
                      })
                    }
                  >
                    저장
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="quiet"
                    onClick={() => {
                      setEditing(s.code);
                      setResText(s.resources.join(", "));
                    }}
                  >
                    편집
                  </Button>
                )}
              </C>
            </tr>
          ))}
        </Table>
      </Card>
    </AdminPage>
  );
}
