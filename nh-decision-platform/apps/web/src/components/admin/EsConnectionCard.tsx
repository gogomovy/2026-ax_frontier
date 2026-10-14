"use client";

import { useState } from "react";
import { Card, TextInput, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiDelete, apiPost, apiPut } from "@/lib/api-client";
import type { SearchBackendStatus } from "@/lib/search-engines";

interface EsConnView {
  source: "db" | "env";
  saved: { url: string; user: string; password: string; updatedBy: string | null; updatedAt: string | null } | null;
  env: { url: string; user: string; passwordSet: boolean };
}
interface Probe {
  ok: boolean;
  errorKind: "auth" | "down" | "rejected" | null;
  message: string;
  cluster?: { status?: string; nodes?: number };
}

const KIND_LABEL: Record<NonNullable<Probe["errorKind"]>, string> = { auth: "인증 실패", down: "연결 불가", rejected: "요청 거절" };

/**
 * Elasticsearch 연결 설정 (Phase K · ES-01~03 · Q154) — 인증 실패(401) 원인 · 조치 안내, 주소 · 계정 · 비밀번호 입력 · 시험 · 저장.
 * 저장한 값은 환경변수(ES_URL · ES_USER · ES_PASSWORD)보다 먼저 쓰고, 비밀번호는 서버에 암호화되어 화면에는 가린 값만 보인다.
 */
export function EsConnectionCard({ es, reload }: { es: SearchBackendStatus["es"] | undefined; reload: () => unknown }) {
  const conn = useApiData<EsConnView>("/admin/knowledge/es-connection");
  const { run, busy } = useAction();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [probe, setProbe] = useState<Probe | null>(null);
  const c = conn.data;
  const auth = es?.errorKind === "auth";

  const start = () => {
    setUrl(c?.saved?.url || c?.env.url || "");
    setUser(c?.saved?.user || c?.env.user || "elastic");
    setPassword("");
    setProbe(null);
    setOpen(true);
  };
  const body = () => ({ url: url.trim(), user: user.trim(), password: password || null });
  const test = () => run(() => apiPost<Probe>("/admin/knowledge/es-connection/test", body())).then((r) => r && setProbe(r));
  const save = () =>
    run(
      () => apiPut<EsConnView & { test: Probe }>("/admin/knowledge/es-connection", body()),
      "연결 설정을 저장했습니다 — 워커는 30초 안에 새 값으로 다시 연결합니다",
      async () => {
        setOpen(false);
        await conn.reload();
        await reload();
      },
    );
  const clear = () =>
    run(() => apiDelete<EsConnView>("/admin/knowledge/es-connection"), "환경변수 값으로 되돌렸습니다", async () => {
      await conn.reload();
      await reload();
    });
  const reconnect = () => run(() => apiPost("/admin/knowledge/es-reconnect"), "다시 연결해 봤습니다", reload);

  return (
    <div className="mb-lg" data-es-connection>
      <Card
        title="Elasticsearch 연결"
        actions={
          <div className="flex flex-wrap gap-xs">
            <Button size="sm" variant="quiet" disabled={busy} onClick={reconnect}>
              다시 연결
            </Button>
            <Button size="sm" variant="quiet" disabled={busy || !c} onClick={start}>
              연결 설정
            </Button>
          </div>
        }
      >
        <p className="text-[12.5px] text-steel">
          지금 쓰는 값: <b className="text-ink-deep">{c ? (c.source === "db" ? "관리자 입력" : "환경변수(.env)") : "–"}</b>
          {c ? ` · ${c.source === "db" ? c.saved?.url : c.env.url || "ES_URL 없음"} · 계정 ${c.source === "db" ? c.saved?.user || "-" : c.env.user || "-"}` : ""}
          {c?.source === "env" && c.env.url && !c.env.passwordSet ? <Badge tone="warning">ES_PASSWORD 비어 있음</Badge> : null}
        </p>
        {es?.error ? (
          <div role="alert" className="mt-sm rounded-xl border border-hairline bg-attention-faint p-md text-[12.5px] leading-relaxed" data-es-error={es.errorKind ?? "down"}>
            <p className="font-bold text-ink-deep">
              {es.errorKind ? KIND_LABEL[es.errorKind] : "연결 안 됨"} — 검색은 PostgreSQL 로 계속 동작합니다
            </p>
            <p className="mt-1 text-charcoal">{es.error}</p>
            {auth && es.remedy?.length ? (
              <ol className="mt-sm list-decimal space-y-1 pl-5 text-charcoal">
                {es.remedy.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ol>
            ) : null}
          </div>
        ) : null}
        {open ? (
          <form
            className="mt-md grid gap-sm md:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <TextInput label="주소" value={url} onChange={setUrl} placeholder="http://elasticsearch:9200" mono />
            <TextInput label="계정" value={user} onChange={setUser} placeholder="elastic" mono />
            <TextInput label="비밀번호 (비우면 지금 값 유지)" value={password} onChange={setPassword} type="password" />
            <div className="flex flex-wrap items-center gap-xs md:col-span-3">
              <Button type="button" size="sm" variant="quiet" disabled={busy || !url.trim()} onClick={test}>
                연결 시험
              </Button>
              <Button type="submit" size="sm" variant="confirm" disabled={busy || !url.trim()}>
                시험 후 저장
              </Button>
              {c?.source === "db" ? (
                <Button type="button" size="sm" variant="quiet" disabled={busy} onClick={clear}>
                  환경변수로 되돌리기
                </Button>
              ) : null}
              <Button type="button" size="sm" variant="quiet" onClick={() => setOpen(false)}>
                닫기
              </Button>
              <span aria-live="polite" className="text-[12.5px]">
                {probe ? (
                  probe.ok ? (
                    <Badge tone="success">연결됨{probe.cluster?.status ? ` · ${probe.cluster.status}` : ""}</Badge>
                  ) : (
                    <span className="text-critical">
                      {probe.errorKind ? KIND_LABEL[probe.errorKind] : "실패"} — {probe.message}
                    </span>
                  )
                ) : null}
              </span>
            </div>
          </form>
        ) : null}
      </Card>
    </div>
  );
}
