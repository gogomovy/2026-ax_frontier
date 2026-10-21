"use client";

import { useState } from "react";
import { AdminPage, C, Card, Check, JsonEditor, Loading, Table, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { useConfirm } from "@/components/providers/UiProvider";
import { FileDrop } from "@/components/ui/FileDrop";
import { KeyValueList, Notice } from "@/components/ui/Layout";
import { Badge, Button, PillTabs } from "@/components/ui/primitives";
import { api, apiPost, apiPut } from "@/lib/api-client";
import { KIND_LABEL, MIN_FIELDS, asRuleList, countsLine, pasteStats, syncActionLabel, type SyncCounts, type SyncKind, type SyncResult } from "@/lib/dataSync";

interface Overview {
  orgs: { dat: number; datActive: number; manual: number };
  users: Record<string, number>;
  history: { id: number; at: string; actor: string | null; action: string; file: string | null; detail: (SyncCounts & { errors?: number; warnings?: number; file?: string }) | null }[];
  settings: Record<string, unknown>;
  rulesError: string | null;
  defaults: { orgTypeRules: unknown[] };
  sso: { enabled: boolean; verifier?: string; ok?: boolean; detail?: string; label: string; allowedToa: string; localLogin: string; loginUrl: string };
}

const ACCEPT = ".dat,.txt";

/** 조직 · 인사 .dat 동기화 (Phase R) — 조직 → 인사 순서로 올린다. 미리보기는 저장하지 않고 결과만 보여준다 */
export default function DataSyncAdmin() {
  const data = useApiData<Overview>("/admin/data-sync");
  const { run, busy } = useAction();
  const d = data.data;
  const users = d?.users ?? {};
  const datActive = users["dat:active"] ?? 0;
  const datDisabled = users["dat:disabled"] ?? 0;

  const saveSettings = (patch: Record<string, unknown>, ok = "설정을 저장했습니다") =>
    run(() => apiPut<Overview>("/admin/data-sync/settings", patch), ok, data.reload);

  return (
    <AdminPage
      title="조직 · 인사 동기화"
      description="인사 시스템에서 받은 조직정보 · 인사정보 .dat 파일을 올려(또는 내용을 붙여 넣어) 조직과 사용자(사번)를 맞춥니다. 조직을 먼저, 인사를 나중에 넣으세요. [미리보기]는 저장하지 않고 바뀔 내용만 셉니다. 동기화된 사번은 비밀번호가 없어 사내 SSO 로만 로그인합니다."
      summary={
        <div className="grid grid-cols-2 gap-md md:grid-cols-4">
          <Stat label="동기화 조직(사용 중)" value={d ? `${d.orgs.datActive.toLocaleString("ko-KR")} / ${d.orgs.dat.toLocaleString("ko-KR")}` : "-"} />
          <Stat label="직접 만든 조직" value={d ? d.orgs.manual.toLocaleString("ko-KR") : "-"} />
          <Stat label="동기화 사용자(사용 중 · 중지)" value={d ? `${datActive.toLocaleString("ko-KR")} · ${datDisabled.toLocaleString("ko-KR")}` : "-"} />
          <Stat label="사내 SSO" value={!d ? "-" : !d.sso.enabled ? "꺼짐" : d.sso.ok ? "정상" : "검증기 오류"} tone={d?.sso.enabled && !d.sso.ok ? "critical" : undefined} />
        </div>
      }
    >
      <Loading error={data.error} loading={!d && data.loading} />
      {d?.rulesError ? (
        <Notice tone="critical" title="필터 규칙 오류 — 동기화를 할 수 없습니다">
          {d.rulesError}
        </Notice>
      ) : null}

      <div className="grid grid-cols-1 gap-lg lg:grid-cols-2">
        <UploadCard
          step={1}
          kind="organization"
          hint="구분자 '|' · UTF-8 또는 EUC-KR. 1번째 칸 사무소코드가 조직 코드가 됩니다. 파일에 없는 동기화 조직은 지우지 않고 '사용 안 함'으로 바꿉니다(30% 를 넘으면 건너뜀)."
          busy={busy}
          run={run}
          onDone={data.reload}
        />
        <UploadCard
          step={2}
          kind="employee"
          hint="구분자 '|' · UTF-8 또는 EUC-KR. 0번째 칸 개인번호가 SSO 사번입니다. 소속 사무소가 조직에 없으면 건너뜁니다. 파일에 없는 동기화 사용자는 사용 중지합니다(30% 를 넘으면 건너뜀 · 관리자 제외)."
          busy={busy}
          run={run}
          onDone={data.reload}
        />
      </div>

      <Card title="최근 동기화 이력">
        {d && d.history.length === 0 ? <p className="text-[12.5px] text-stone">아직 이력이 없습니다.</p> : null}
        {d && d.history.length > 0 ? (
          <Table head={["시각", "대상", "방식", "파일", "결과", "오류 · 경고", "실행자"]}>
            {d.history.map((h) => {
              const a = syncActionLabel(h.action);
              const kind = h.action.includes("organization") ? "organization" : h.action.includes("employee") ? "employee" : undefined;
              return (
                <tr key={h.id}>
                  <C className="whitespace-nowrap tnum">{fmtTime(h.at)}</C>
                  <C>{a.target}</C>
                  <C>
                    <Badge tone={a.mode === "반영" ? "info" : "neutral"}>{a.mode}</Badge>
                  </C>
                  <C className="max-w-[220px] truncate">{kind ? (h.detail?.file ?? h.file ?? "-") : "-"}</C>
                  <C>{kind ? countsLine(h.detail, kind) : "-"}</C>
                  <C className="tnum">{kind ? `${h.detail?.errors ?? 0} · ${h.detail?.warnings ?? 0}` : "-"}</C>
                  <C mono>{h.actor ?? "-"}</C>
                </tr>
              );
            })}
          </Table>
        ) : null}
      </Card>

      {d ? <RulesCard d={d} busy={busy} save={saveSettings} /> : null}
      {d ? <SsoCard d={d} busy={busy} save={saveSettings} /> : null}
    </AdminPage>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "critical" }) {
  return (
    <div className="rounded-2xl border border-hairline-soft bg-canvas px-md py-3">
      <p className="text-[11.5px] font-bold text-steel">{label}</p>
      <p className={tone === "critical" ? "mt-0.5 text-[18px] font-bold text-critical" : "mt-0.5 text-[18px] font-bold text-ink-deep tnum"}>{value}</p>
    </div>
  );
}

type Run = ReturnType<typeof useAction>["run"];

function UploadCard({ step, kind, hint, busy, run, onDone }: { step: number; kind: SyncKind; hint: string; busy: boolean; run: Run; onDone: () => unknown }) {
  const confirm = useConfirm();
  // 파일을 올릴 수 없을 때(DRM 등) 메모장에서 복사한 본문을 붙여 넣는다 — 서버가 파일과 같은 검사 · 파서로 처리
  const [mode, setMode] = useState<"file" | "paste">("file");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [result, setResult] = useState<SyncResult | null>(null);
  const label = KIND_LABEL[kind];
  const stats = pasteStats(text);
  const ready = mode === "file" ? Boolean(file) : stats.lines > 0;
  const source = mode === "file" ? (file?.name ?? "") : `붙여 넣은 ${stats.lines.toLocaleString("ko-KR")}줄`;

  const send = async (dryRun: boolean) => {
    if (!ready) return;
    if (!dryRun) {
      const ok = await confirm({
        title: `${label}정보를 반영할까요?`,
        body: `${source} 의 내용으로 ${kind === "organization" ? "조직을 추가 · 변경하고, 목록에 없는 동기화 조직은 사용 안 함으로" : "사용자를 추가 · 변경하고, 목록에 없는 동기화 사용자는 사용 중지(세션 종료)로"} 바꿉니다. 먼저 [미리보기]로 건수를 확인하세요.`,
        confirmLabel: "반영",
      });
      if (!ok) return;
    }
    const call =
      mode === "file"
        ? () => {
            const fd = new FormData();
            fd.append("file", file as File);
            fd.append("dry_run", dryRun ? "true" : "false");
            return api<SyncResult>(`/admin/data-sync/${kind}`, { method: "POST", body: fd });
          }
        : () => apiPost<SyncResult>(`/admin/data-sync/${kind}/text`, { text, dry_run: dryRun });
    const r = await run(call, (x) => `${label} ${dryRun ? "미리보기" : "반영"} — ${countsLine(x, kind)}`, onDone);
    if (r) {
      setResult(r);
      if (!dryRun && mode === "paste") setText(""); // 인사 정보가 화면에 남지 않게 — 반영하면 비운다
    }
  };

  return (
    <Card
      title={
        <span>
          <span className="mr-1.5 inline-flex h-6 w-6 items-center justify-center rounded-circle bg-ink-deep text-[12px] text-white">{step}</span>
          {label}정보 (.dat)
        </span>
      }
    >
      <div className="mb-md">
        <PillTabs
          size="sm"
          label={`${label}정보 넣는 방법`}
          value={mode}
          onChange={(m) => {
            setMode(m);
            setResult(null);
          }}
          items={[
            { key: "file", label: "파일 올리기" },
            { key: "paste", label: "내용 붙여넣기" },
          ]}
        />
      </div>
      {mode === "file" ? (
        <FileDrop
          id={`sync-${kind}`}
          accept={ACCEPT}
          file={file}
          onFile={(f) => {
            setFile(f);
            setResult(null);
          }}
          hint={hint}
          disabled={busy}
          compact
          data-testid={`sync-${kind}`}
        />
      ) : (
        <div className="flex flex-col gap-1">
          <label htmlFor={`sync-${kind}-text`} className="text-[12px] font-bold text-charcoal">
            {label}정보 본문
          </label>
          <p id={`sync-${kind}-text-hint`} className="text-[11.5px] leading-relaxed text-steel">
            DRM 등으로 파일을 올릴 수 없으면 메모장에서 파일을 열어 전체 선택(Ctrl+A) · 복사(Ctrl+C)한 뒤 여기에 붙여 넣으세요. 파일과 같은 규칙(구분자 &apos;|&apos;, 한 줄에 한 건)으로 읽습니다.
          </p>
          <textarea
            id={`sync-${kind}-text`}
            aria-describedby={`sync-${kind}-text-hint sync-${kind}-text-stats`}
            className="input min-h-[160px] font-mono text-[11.5px] leading-snug"
            rows={8}
            spellCheck={false}
            autoComplete="off"
            value={text}
            disabled={busy}
            onChange={(e) => {
              setText(e.target.value);
              setResult(null);
            }}
            placeholder={kind === "organization" ? "법인|사무소코드|사무소명|…" : "개인번호|성명|법인|…"}
            data-testid={`sync-${kind}-text`}
          />
          <p id={`sync-${kind}-text-stats`} className="text-[11.5px] text-steel tnum" aria-live="polite">
            {stats.lines ? (
              <>
                {stats.lines.toLocaleString("ko-KR")}줄 · 첫 줄 {stats.fields}칸
                {stats.fields < MIN_FIELDS[kind] ? <span className="ml-1 font-bold text-attention">— {label} .dat 는 {MIN_FIELDS[kind]}칸 이상이어야 합니다</span> : null}
                {stats.ragged ? <span className="ml-1 text-attention">· 칸 수가 다른 줄 {stats.ragged.toLocaleString("ko-KR")}개</span> : null}
              </>
            ) : (
              "붙여 넣은 내용 없음"
            )}
          </p>
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-xs">
        <Button size="sm" variant="secondary" disabled={busy || !ready} onClick={() => send(true)}>
          미리보기
        </Button>
        <Button size="sm" variant="confirm" disabled={busy || !ready} onClick={() => send(false)}>
          반영
        </Button>
      </div>
      {result ? <ResultView r={result} /> : null}
    </Card>
  );
}

function ResultView({ r }: { r: SyncResult }) {
  return (
    <div className="mt-md flex flex-col gap-sm" data-sync-result={r.kind}>
      <Notice tone={r.errors.length ? "attention" : "success"} title={`${r.dryRun ? "미리보기 (저장 안 함)" : "반영 완료"} — ${r.file}`}>
        {countsLine(r, r.kind)} · 인코딩 {r.encoding}
      </Notice>
      {r.warnings.length ? <Lines title={`경고 ${r.warnings.length}건`} items={r.warnings} tone="attention" /> : null}
      {r.errors.length ? <Lines title={`오류 ${r.errors.length}건 (해당 줄은 건너뜀)`} items={r.errors} tone="critical" /> : null}
    </div>
  );
}

function Lines({ title, items, tone }: { title: string; items: string[]; tone: "attention" | "critical" }) {
  return (
    <div>
      <p className={tone === "critical" ? "text-[12px] font-bold text-critical" : "text-[12px] font-bold text-attention"}>{title}</p>
      <ul className="mt-1 max-h-48 overflow-auto rounded-lg bg-surface-soft px-md py-2 font-mono text-[11px] leading-relaxed text-charcoal">
        {items.map((m, i) => (
          <li key={i}>{m}</li>
        ))}
      </ul>
    </div>
  );
}

function RulesCard({ d, busy, save }: { d: Overview; busy: boolean; save: (patch: Record<string, unknown>, ok?: string) => unknown }) {
  const filters = asRuleList(d.settings["sync.filter_rules"]);
  const typeRules = asRuleList(d.settings["sync.org_type_rules"]);
  return (
    <Card title="동기화 규칙">
      <div className="grid grid-cols-1 gap-lg lg:grid-cols-2">
        <div>
          <p className="mb-1 text-[12.5px] font-bold text-ink-deep">가져올 대상 (필터 규칙)</p>
          <p className="mb-xs text-[11.5px] leading-relaxed text-steel">
            비워 두면 파일 전체를 가져옵니다. 규칙끼리는 OR, 규칙 안의 키끼리는 AND 입니다. 키: corpType · regionCode(s) · parent2Code(s) · parent3Code(s), 여러 값은 쉼표로. 예: {'[{"corpType":"1","regionCodes":"01,02"}]'}
          </p>
          <JsonEditor value={filters ?? d.settings["sync.filter_rules"]} rows={8} disabled={busy} onSave={(v) => save({ filter_rules: v }, "필터 규칙을 저장했습니다")} />
        </div>
        <div>
          <p className="mb-1 text-[12.5px] font-bold text-ink-deep">조직 유형 (이름 끝말 규칙)</p>
          <p className="mb-xs text-[11.5px] leading-relaxed text-steel">
            위에서부터 처음 맞는 규칙의 유형을 씁니다(pattern 은 정규식). 유형 코드는 [조직] 화면의 유형(HQ_DIV · DEPT · BUREAU · TEAM · REGION · BRANCH)입니다.
          </p>
          <JsonEditor value={typeRules && typeRules.length ? typeRules : d.defaults.orgTypeRules} rows={8} disabled={busy} onSave={(v) => save({ org_type_rules: v }, "유형 규칙을 저장했습니다")} />
        </div>
      </div>
      <div className="mt-md">
        <Check
          label="직접 만든 조직도 파일 기준으로 상위 · 유형을 덮어쓰기 (기본: 이름 · 사용 여부만 맞춤)"
          checked={Boolean(d.settings["sync.overwrite_manual_orgs"])}
          disabled={busy}
          onChange={(v) => save({ overwrite_manual_orgs: v })}
        />
      </div>
      <p className="mt-sm text-[11.5px] text-stone">새로 들어온 조직의 화면 권한은 [화면 권한]에서 정합니다. 상위 조직의 권한이 하위로 상속됩니다.</p>
    </Card>
  );
}

function SsoCard({ d, busy, save }: { d: Overview; busy: boolean; save: (patch: Record<string, unknown>, ok?: string) => unknown }) {
  const [org, setOrg] = useState(String(d.settings["sso.default_org"] ?? ""));
  const s = d.sso;
  return (
    <Card title="사내 SSO (INISAFE Nexess)">
      {!s.enabled ? (
        <Notice tone="info" title="사내 SSO 가 꺼져 있습니다">
          배포 설정 NC_SSO_ENABLED=1 과 검증기(sso-verifier) 를 켜면 로그인 화면에 통합 로그인 단추가 나타납니다.
        </Notice>
      ) : (
        <KeyValueList
          items={[
            { label: "검증기", value: <Badge tone={s.ok ? "success" : "critical"}>{`${s.verifier ?? "-"} · ${s.ok ? "정상" : "응답 없음"}`}</Badge>, hint: s.ok ? undefined : s.detail },
            { label: "로그인 단추", value: s.label },
            { label: "허용 인증 방식(TOA)", value: s.allowedToa },
            { label: "사번 · 비밀번호 로그인", value: s.localLogin === "all" ? "모두 허용" : s.localLogin === "admin" ? "관리자 비상 로그인만" : "사용 안 함" },
            { label: "NLS 로그인 주소", value: s.loginUrl || "-" },
          ]}
        />
      )}
      <div className="mt-md flex flex-col gap-sm">
        <Check
          label="인사 동기화에 없는 사번도 SSO 로그인 때 자동으로 만들기 (기본 끔 — 아래 기본 소속 필요)"
          checked={Boolean(d.settings["sso.auto_create_user"])}
          disabled={busy}
          onChange={(v) => save({ auto_create_user: v })}
        />
        <Check
          label="사용 중지된 사번이 SSO 로 로그인하면 다시 사용으로 바꾸기 (기본 끔 — 거부)"
          checked={Boolean(d.settings["sso.reactivate_disabled"])}
          disabled={busy}
          onChange={(v) => save({ reactivate_disabled: v })}
        />
        <div className="flex flex-wrap items-end gap-xs">
          <TextInput label="자동 생성 사용자의 기본 소속 조직 코드" value={org} onChange={setOrg} mono className="w-64" />
          <Button size="sm" variant="secondary" disabled={busy || org === String(d.settings["sso.default_org"] ?? "")} onClick={() => save({ default_org: org.trim() }, "기본 소속을 저장했습니다")}>
            저장
          </Button>
        </div>
      </div>
    </Card>
  );
}
