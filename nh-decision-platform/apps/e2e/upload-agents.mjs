// 업로드 기반 에이전트 시험 (B.40) — 사용자가 [데이터셋 · 문서] 화면에 다음 달 마감 자료를 올렸다고 가정하고,
// 이벤트 → 관련 워크플로우 → 변화 감지 · 실행 계획(LLM 판단) → 근거 · 서술(LLM) → 검증 → 정의서 mart 적재 → 화면 갱신까지 확인한다.
//
//   1) 시험 파일 생성:  docker compose exec -T api env OUT=/tmp/upload-fixtures python - < apps/e2e/fixtures/make_upload_fixtures.py
//                      docker compose cp api:/tmp/upload-fixtures ./upload-fixtures
//   2) 실행:          E2E_BASE=http://localhost:3100 E2E_ADMIN_EMP=... E2E_ADMIN_PW=... FIXTURES=./upload-fixtures node upload-agents.mjs
//      LLM 연결(선택): E2E_LLM_BASE=https://.../v1 E2E_LLM_KEY=... E2E_LLM_MODEL=claude-sonnet-5 E2E_LLM_EMBED=amazon.titan-embed-text-v2:0
//                      (키는 환경변수로만 받는다 — 파일에 남기지 않음)
//      판정 모드(B.45): LLM 연결(주소 · 기본 모델)이 있으면 LLM 판단 · 서술 · 추출을, 없으면 규칙 경로(규칙 판단 · 기존 문장 유지 ·
//                      별칭 사전 추출 · 질의 정리 모드)를 확인한다. E2E_EXPECT_LLM=1|0 으로 강제.
//
// 운영 DB 를 바꾸므로 별도 스택(docker compose -p nhdipe2e …)에서 돌린다. 결과: $E2E_OUT/upload-agents.{json,md}
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const BASE = (process.env.E2E_BASE ?? "http://localhost:3100").replace(/\/$/, "");
const API = `${BASE}/backend`;
const FIX = process.env.FIXTURES ?? "./upload-fixtures";
const OUT = process.env.E2E_OUT ?? path.join(os.tmpdir(), "nhdip-e2e");
const TIMEOUT_MIN = Number(process.env.E2E_FLOW_TIMEOUT_MIN ?? 25);
fs.mkdirSync(OUT, { recursive: true });

let cookie = "";
let LLM_MODE = true; // 연결 상태를 읽은 뒤 정한다
let EMBED_MODE = true;
const results = [];
const ok = (name, cond, detail = "") => {
  results.push({ name, pass: !!cond, detail });
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${detail ? " — " + detail : ""}`);
};
const info = (name, detail) => {
  results.push({ name, pass: null, detail });
  console.log(`INFO  ${name} — ${detail}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function call(method, p, body, form) {
  const headers = { Origin: BASE, Cookie: cookie };
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const r = await fetch(API + p, { method, headers, body: payload });
  const set = r.headers.getSetCookie?.() ?? [];
  if (set.length) cookie = set.map((c) => c.split(";")[0]).join("; ");
  const text = await r.text();
  let json = null;
  try {
    json = JSON.parse(text);
  } catch {
    json = text;
  }
  return { status: r.status, body: json };
}
const get = (p) => call("GET", p).then((r) => r.body);

function file(name) {
  const p = path.join(FIX, name);
  if (!fs.existsSync(p)) throw new Error(`시험 파일 없음: ${p} — fixtures/make_upload_fixtures.py 로 먼저 만드세요`);
  return new Blob([fs.readFileSync(p)]);
}

const DATASETS = [
  ["PROVISION_BY_PRODUCT", "(202609)7790_상품별_충당금.xlsx", "2026.09 상품별 충당금 마감"],
  ["MODEL_MONITORING_GRADE", "신용평가모형_등급별_모니터링_집계(2026.09).xlsx", "2026.09 등급별 모니터링 집계"],
  ["OBLG_GRD_DEF", "Oblg_grd_def_202609.xlsx", "2026.09 기업 익스포저(지점 신규 유치 2건 포함)"],
  ["RETAIL_EXPOSURE", "TB_JC_PM_C_LA_202609.xlsx", "2026.09 소매 익스포저(새희망홀씨 신규 8건)"],
  ["BRANCH_KPI_SCORE", "영업점 업적평가 득점 현황(202609).xlsx", "2026.09.30 업적평가 득점"],
];
const DOCS = [
  { file: "(시뮬레이션) 2026년 하반기 서민금융 공급 확대 및 취약차주 보호 방안.pdf", origin: "ext", doc_class: "gov_policy", title: "(시뮬레이션) 2026년 하반기 서민금융 공급 확대 및 취약차주 보호 방안", issuer: "정책 당국(시뮬레이션)", published_at: "2026-09-25", doc_code: "doc-sim-seomin-2026h2" },
  { file: "(시뮬레이션) 신용리스크관리부 공문 - 소기업 모형 6B 등급 부도율 점검 요청(2026.09).pdf", origin: "bank", doc_class: "model_method", title: "(시뮬레이션) 소기업 모형 6B 등급 부도율 점검 및 등급계량화 재검토 요청", issuer: "신용리스크관리부", published_at: "2026-10-05", doc_code: "doc-sim-micro-6b-2609" },
];
const KEY_METRICS = ["dr_6b", "pd_mid_6b", "breach_gap_6b", "psi_micro", "share_now", "share_delta_pp", "prov_inclusive_now", "br_corp_cnt", "br_avg_grade", "br_prime_score_now", "br_seomin_cnt", "br_seomin_share", "br_seomin_score_now", "br_seomin_rec_cnt", "br_kpi_total"];

async function snapshot() {
  const m = await get("/admin/metrics");
  const metrics = Object.fromEntries((m.metrics ?? []).filter((x) => KEY_METRICS.includes(x.code)).map((x) => [x.code, x.latest?.display ?? null]));
  const c = await get("/admin/contracts");
  const contracts = Object.fromEntries(
    (c.tables ?? []).map((t) => {
      const cols = Object.fromEntries((t.report?.columns ?? []).map((x) => [x.column, x]));
      return [t.code, { baseYm: t.report?.baseYm ?? null, rows: t.report?.rows ?? null, summary: t.report?.summary ?? {}, summaryText: cols.AGENT_SUMMARY?.value ?? cols.AGENT_SUMMARY_TEXT?.value ?? null, at: t.reportAt }];
    }),
  );
  return { metrics, contracts };
}

try {
  // 1) 로그인
  const login = await call("POST", "/auth/login", { emp_no: process.env.E2E_ADMIN_EMP, password: process.env.E2E_ADMIN_PW });
  ok("관리자 로그인", login.status === 200, `HTTP ${login.status}`);
  if (login.status !== 200) throw new Error("로그인 실패");

  // 2) LLM 연결(선택)
  if (process.env.E2E_LLM_BASE && process.env.E2E_LLM_KEY) {
    const r = await call("POST", "/admin/llm/setup", { base_url: process.env.E2E_LLM_BASE, api_key: process.env.E2E_LLM_KEY, model: process.env.E2E_LLM_MODEL ?? "claude-sonnet-5", embedding_model: process.env.E2E_LLM_EMBED ?? null });
    const t = r.body?.test ?? {};
    ok("LLM 간단 설정 · 연결 확인", r.status === 200 && t.ok === true, `HTTP ${r.status} · 모델 ${r.body?.model ?? "-"} · 임베딩 ${r.body?.embeddingModel ?? "-"} · 모델 목록 ${(t.models ?? []).length ?? 0}개 · chat ${t.chat_ok}`);
  }
  const setup = await get("/admin/llm/setup");
  // LLM 없는 모드(B.45) — 연결 주소 · 기본 모델이 없으면 판단 · 서술 · 추출은 규칙으로 돈다. 판정을 그 모드에 맞춘다.
  // E2E_EXPECT_LLM=1 / 0 으로 강제할 수 있다(예: CI 에서 LLM 없이 규칙 경로만 확인).
  LLM_MODE = process.env.E2E_EXPECT_LLM ? process.env.E2E_EXPECT_LLM === "1" : Boolean(setup?.connection?.active && setup?.connection?.baseUrl && setup?.model);
  EMBED_MODE = LLM_MODE && Boolean(setup?.embeddingModel);
  info("LLM 연결", `${setup?.connection?.baseUrl || "-"} · 키 ${setup?.connection?.hasKey ? "있음" : "없음"} · 기본 모델 ${setup?.model || "-"} · 임베딩 ${setup?.embeddingModel || "-"} · 판정 모드 ${LLM_MODE ? "LLM" : "LLM 없음(규칙)"}`);

  // 3) 이전 상태
  const before = await snapshot();
  const lastEvent = (await get("/admin/monitor/flow?limit=1"))[0]?.id ?? 0;
  const t0 = Date.now();

  // 4) 업로드 — 화면의 [업로드]와 같은 API
  const uploads = [];
  for (const [code, name, note] of DATASETS) {
    const fd = new FormData();
    fd.append("file", file(name), name);
    fd.append("origin", "bank");
    fd.append("data_origin", "simulated");
    fd.append("note", `업로드 시험(B.40) — ${note}`);
    const r = await call("POST", `/admin/datasets/${code}/upload`, undefined, fd);
    const v = r.body ?? {};
    uploads.push({ code, file: name, status: r.status, version: v.version, rows: v.rows, quality: v.quality?.status, adapter: v.quality?.source?.adapter ?? null });
    ok(`업로드 ${code}`, r.status === 201 && v.status === "committed" && v.isCurrent, `HTTP ${r.status} · v${v.version ?? "-"} · ${v.rows ?? "-"}행 · 품질 ${v.quality?.status ?? "-"}${v.quality?.source?.adapter ? " · 원본 양식 " + v.quality.source.adapter : ""}${typeof v === "string" || v.detail ? " · " + JSON.stringify(v).slice(0, 160) : ""}`);
  }
  for (const d of DOCS) {
    const fd = new FormData();
    fd.append("file", file(d.file), d.file);
    for (const k of ["origin", "doc_class", "title", "issuer", "published_at", "doc_code"]) fd.append(k, d[k]);
    const r = await call("POST", "/admin/documents/upload", undefined, fd);
    uploads.push({ code: d.doc_code, file: d.file, status: r.status, docClass: d.doc_class });
    ok(`문서 업로드 ${d.doc_class}`, r.status === 201, `HTTP ${r.status} · ${d.title}`);
  }

  // 5) 흐름 대기 — 이벤트가 모두 디스패치되고 실행 · 대기 작업이 끝날 때까지
  let events = [];
  let quiet = 0;
  for (let i = 0; i < TIMEOUT_MIN * 6; i++) {
    await sleep(10000);
    events = (await get("/admin/monitor/flow?limit=80")).filter((e) => e.id > lastEvent);
    const pending = events.some((e) => !e.dispatchedAt || e.pending.length || e.runs.some((r) => r.status === "running"));
    const pipe = await get("/admin/pipeline");
    const busy = pipe.workflows.some((w) => w.live);
    process.stderr.write(`… ${Math.round((Date.now() - t0) / 1000)}s 이벤트 ${events.length} · ${busy ? "실행 중 " + pipe.workflows.filter((w) => w.live).map((w) => w.code).join(",") : "대기 없음"}\n`);
    quiet = !pending && !busy ? quiet + 1 : 0;
    if (quiet >= 2) break;
  }
  ok("흐름 완료(타임아웃 전)", quiet >= 2, `${Math.round((Date.now() - t0) / 1000)}초 · 이벤트 ${events.length}건`);

  // 6) 결과 수집
  const flow = events
    .slice()
    .reverse()
    .map((e) => ({ id: e.id, type: e.type, payload: { dataset: e.payload.dataset, doc_code: e.payload.doc_code, doc_class: e.payload.doc_class, workflow: e.payload.workflow, by: e.payload.by, reason: e.payload.reason }, matched: e.matched.map((m) => ({ workflow: m.workflow, reasons: m.reasons, note: m.note })), runs: e.runs.map((r) => ({ workflow: r.workflow, status: r.status, run: r.run, published: r.published })) }));
  const ds = (code) => flow.find((e) => e.type === "dataset.committed" && e.payload.dataset === code);
  const wfOf = (e) => (e?.matched ?? []).map((m) => m.workflow).filter(Boolean).sort();
  ok("7790 → 포용금융 워크플로우", wfOf(ds("PROVISION_BY_PRODUCT")).includes("wf_inclusive_risk"), wfOf(ds("PROVISION_BY_PRODUCT")).join(", "));
  ok("등급별 모니터링 → 모형 모니터링", wfOf(ds("MODEL_MONITORING_GRADE")).includes("wf_model_monitoring"), wfOf(ds("MODEL_MONITORING_GRADE")).join(", "));
  ok("기업 · 소매 · 득점 → 영업점", ["OBLG_GRD_DEF", "RETAIL_EXPOSURE", "BRANCH_KPI_SCORE"].every((c) => wfOf(ds(c)).includes("wf_branch_kpi")), ["OBLG_GRD_DEF", "RETAIL_EXPOSURE", "BRANCH_KPI_SCORE"].map((c) => `${c}: ${wfOf(ds(c)).join("+")}`).join(" · "));
  ok("관련 없는 워크플로우는 실행 안 함(7790 → 종기부 X)", !wfOf(ds("PROVISION_BY_PRODUCT")).includes("wf_hq_goal_review"), wfOf(ds("PROVISION_BY_PRODUCT")).join(", "));

  const runs = (await get("/admin/monitor/runs?limit=60")).filter((r) => new Date(r.startedAt).getTime() >= t0 - 5000);
  const byWf = {};
  for (const r of runs) (byWf[r.workflow] ??= []).push(r);
  ok("실행 실패 없음", runs.length > 0 && runs.every((r) => r.status !== "failed"), runs.map((r) => `${r.workflow}:${r.status}`).join(", "));
  info("실행 병합(디바운스)", Object.entries(byWf).map(([w, rs]) => `${w} ${rs.length}회 · 원인 ${rs.reduce((a, r) => a + (r.causes?.length ?? 0), 0)}건`).join(" · "));
  const llmCalls = runs.reduce((a, r) => a + (r.llmCalls ?? 0), 0);
  const tokens = runs.reduce((a, r) => a + (r.tokens ?? 0), 0);
  info("LLM 호출", `${llmCalls}회 · 토큰 ${tokens.toLocaleString()}`);

  const decisions = (await get("/admin/agents/decisions?limit=200")).items.filter((d) => new Date(d.at).getTime() >= t0 - 5000);
  const byAgent = {};
  for (const d of decisions) {
    const k = `${d.agent}:${d.decision}`;
    byAgent[k] ??= { llm: 0, rule: 0, other: 0, samples: [] };
    const by = d.detail?.by;
    byAgent[k][by === "llm" ? "llm" : by === "rule" ? "rule" : "other"] += 1;
    if (byAgent[k].samples.length < 2) byAgent[k].samples.push(d.summary);
  }
  const llmBy = (agent) => Object.entries(byAgent).filter(([k]) => k.startsWith(agent + ":")).reduce((a, [, v]) => a + v.llm, 0);
  const allBy = (agent) => Object.entries(byAgent).filter(([k]) => k.startsWith(agent + ":")).reduce((a, [, v]) => a + v.llm + v.rule + v.other, 0);
  const agentDetail = (agent) => JSON.stringify(Object.fromEntries(Object.entries(byAgent).filter(([k]) => k.startsWith(agent)).map(([k, v]) => [k, { llm: v.llm, rule: v.rule }])));
  if (LLM_MODE) {
    ok("변화 감지 — LLM 판단", llmBy("change_detector") > 0, agentDetail("change_detector"));
    ok("실행 계획(플래너) — LLM 판단", llmBy("planner") > 0, agentDetail("planner"));
  } else {
    // LLM 없이도 판단 에이전트는 규칙(CHANGE_SIGNIFICANCE · PLANNER_POLICY)으로 결정을 남겨야 한다 — LLM 판단은 0
    ok("변화 감지 — 규칙 판단(LLM 없음)", allBy("change_detector") > 0 && llmBy("change_detector") === 0, agentDetail("change_detector"));
    ok("실행 계획(플래너) — 규칙 판단(LLM 없음)", allBy("planner") > 0 && llmBy("planner") === 0, agentDetail("planner"));
  }
  info("오케스트레이터", JSON.stringify(Object.fromEntries(Object.entries(byAgent).filter(([k]) => k.startsWith("orchestrator")).map(([k, v]) => [k, { llm: v.llm, rule: v.rule, other: v.other }]))));

  const pipe = await get("/admin/pipeline");
  const nodeView = {};
  for (const w of pipe.workflows) {
    if (!byWf[w.code]) continue;
    nodeView[w.code] = w.nodes.filter((n) => n.last).map((n) => ({ key: n.key, status: n.last.status, ms: n.last.ms, agent: n.agent ? `${n.agent.kind}${n.agent.model ? ":" + n.agent.model : ""}` : null, summary: n.last.summary }));
  }
  const narr = Object.entries(nodeView).flatMap(([w, ns]) => ns.filter((n) => n.key === "narrate").map((n) => `${w}: ${n.summary}`));
  if (LLM_MODE) ok("의견 서술 — LLM 모델로 생성", narr.some((s) => /sonnet|claude|gpt|haiku|opus/i.test(s)), narr.join(" · "));
  else {
    // LLM 없으면 서술 노드는 기존 문장을 유지하고 실패하지 않아야 한다
    const narrSt = Object.entries(nodeView).flatMap(([w, ns]) => ns.filter((n) => n.key === "narrate").map((n) => `${w}:${n.status}`));
    ok("의견 서술 — LLM 없음(기존 문장 유지 · 실패 없음)", narrSt.length > 0 && narrSt.every((s) => !s.endsWith("failed")), narr.join(" · "));
  }
  const crit = Object.entries(nodeView).flatMap(([w, ns]) => ns.filter((n) => n.key === "critic").map((n) => `${w}:${n.status}`));
  ok("검증(Critic) 통과", crit.length > 0 && crit.every((s) => !s.endsWith("failed")), crit.join(", "));
  const detected = Object.entries(nodeView).flatMap(([w, ns]) => ns.filter((n) => n.key === "detect").map((n) => `${w}: ${n.summary}`));
  ok("유의 변화 감지", detected.some((s) => /유의 변화 [1-9]/.test(s)), detected.join(" · "));

  const docs = (await get("/admin/documents")).filter((d) => DOCS.some((x) => x.doc_code === d.docCode));
  const docLine = docs.map((d) => `${d.docCode}: 청크 ${d.chunks} · 임베딩 ${d.embedded} · 상태 ${d.status}`).join(" · ");
  if (EMBED_MODE) ok("문서 청크 · 임베딩", docs.length === DOCS.length && docs.every((d) => d.chunks > 0 && d.embedded === d.chunks), docLine);
  else ok("문서 청크(임베딩 모델 없음 — 키워드 검색)", docs.length === DOCS.length && docs.every((d) => d.chunks > 0), docLine);
  const extLine = docs.map((d) => `${d.docCode}: ${d.extraction?.by ?? "-"} 개체 ${d.extraction?.entities ?? 0} · 관계 ${d.extraction?.relations ?? 0}${d.extraction?.fallbackReason ? " · " + d.extraction.fallbackReason : ""}`).join(" · ");
  if (LLM_MODE) ok("온톨로지 추출(LLM)", docs.some((d) => String(d.extraction?.by ?? "").startsWith("llm") && d.extraction.entities > 0), extLine);
  else ok("온톨로지 추출(규칙 — 별칭 사전)", docs.length > 0 && docs.every((d) => d.extraction?.by === "rule" && d.extraction.entities > 0), extLine);

  // 7) 이후 상태 · 비교
  const after = await snapshot();
  const diff = KEY_METRICS.map((k) => ({ metric: k, before: before.metrics[k], after: after.metrics[k] }));
  for (const d of diff) console.log(`      ${d.metric}: ${d.before} → ${d.after}`);
  ok("6B 실제부도율 갱신(7.929 → 8.233)", Number(after.metrics.dr_6b).toFixed(3) === "8.233", `${before.metrics.dr_6b} → ${after.metrics.dr_6b}`);
  ok("포용금융 충당금 비중 상승", Number(after.metrics.share_now) > Number(before.metrics.share_now), `${before.metrics.share_now} → ${after.metrics.share_now}`);
  ok("서민금융 신규 실적 반영(득점 상승)", Number(after.metrics.br_seomin_score_now) > Number(before.metrics.br_seomin_score_now), `${before.metrics.br_seomin_score_now} → ${after.metrics.br_seomin_score_now}`);
  ok("업적평가 총득점 — 스냅숏 중복 합산 없음", Number(after.metrics.br_kpi_total) < Number(before.metrics.br_kpi_total) * 1.2, `${before.metrics.br_kpi_total} → ${after.metrics.br_kpi_total}`);
  for (const code of ["RISK_T01", "RISK_T02", "RISK_T03", "BRANCH_T01", "BRANCH_T02", "BRANCH_T03"]) {
    const a = after.contracts[code] ?? {};
    ok(`정의서 ${code} 2026.09 적재`, a.baseYm === YM_EXPECTED(code), `기준월 ${before.contracts[code]?.baseYm} → ${a.baseYm} · ${a.rows ?? "-"}행 · ${JSON.stringify(a.summary)}`);
  }
  const sumChanged = ["RISK_T01", "RISK_T03", "BRANCH_T03"].filter((c) => before.contracts[c]?.summaryText !== after.contracts[c]?.summaryText);
  info("의견 문장 갱신(정의서 AGENT_SUMMARY)", `${sumChanged.length}개 표 문장 변경 — ${sumChanged.join(", ")}`);
  info("정의서 목업값 대조", "목업값은 2026.08 화면 기준 — 2026.09 자료에서는 6B 7.929% · 0.196%p 대조가 '불일치' 로 바뀌는 것이 정상(차이 표시)");

  // 8) 질의 — 새 수치를 LLM 이 도구 결과로만 답하는지
  const ask = await call("POST", "/assist", { question: "2026년 9월 기준 소기업 6B 등급 실제부도율과 예측부도율 대표값 차이는 얼마이고 최대값 이내인가요?", screen: "RISK_HOME" });
  const askLine = `${ask.body?.mode} · ${ask.body?.model ?? "-"} · 검증 ${ask.body?.verification?.passed} · ${String(ask.body?.answer ?? ask.body?.detail ?? "").slice(0, 220)}`;
  if (LLM_MODE) ok("질의 — LLM 답변 · 수치 출처 검증", ask.status === 200 && ask.body?.mode === "llm" && ask.body?.verification?.passed !== false, askLine);
  else ok("질의 — LLM 없음(확정 수치 · 근거 정리)", ask.status === 200 && ask.body?.mode === "fallback" && String(ask.body?.answer ?? "").length > 0, askLine);
  // B.44 — '차이' 로 물어도 '대표값 초과 폭' 지표를 찾아 LLM 이 직접 빼지 않게 한다(두 모드 공통)
  const askMetrics = (ask.body?.metrics ?? []).map((m) => m.code);
  ok("질의 — '차이' 질문에 대표값 초과 폭 지표 포함", askMetrics.includes("breach_gap_6b"), askMetrics.join(", "));

  const report = { at: new Date().toISOString(), base: BASE, seconds: Math.round((Date.now() - t0) / 1000), uploads, flow, runs: runs.map((r) => ({ workflow: r.workflow, status: r.status, startedAt: r.startedAt, finishedAt: r.finishedAt, causes: r.causes?.length ?? 0, llmCalls: r.llmCalls, tokens: r.tokens })), decisions: byAgent, nodes: nodeView, documents: docs, metrics: diff, contracts: { before: before.contracts, after: after.contracts }, assist: ask.body, results };
  fs.writeFileSync(path.join(OUT, "upload-agents.json"), JSON.stringify(report, null, 1));
  fs.writeFileSync(path.join(OUT, "upload-agents.md"), markdown(report));
  console.log(`\n결과: ${path.join(OUT, "upload-agents.md")}`);
} catch (e) {
  ok("시험 중단", false, e.message);
}
const failed = results.filter((r) => r.pass === false);
console.log(`\n${results.filter((r) => r.pass === true).length} passed · ${failed.length} failed`);
process.exit(failed.length ? 1 : 0);

function YM_EXPECTED() {
  return "202609";
}

function markdown(r) {
  const L = [];
  L.push(`# 업로드 기반 에이전트 시험 결과 (${r.at.slice(0, 16).replace("T", " ")} UTC)`, "");
  L.push(`대상 ${r.base} · 업로드부터 흐름 완료까지 ${r.seconds}초`, "");
  L.push("## 판정", "", "| 결과 | 항목 | 내용 |", "|---|---|---|");
  for (const x of r.results) L.push(`| ${x.pass === null ? "INFO" : x.pass ? "PASS" : "FAIL"} | ${x.name} | ${String(x.detail).replace(/\|/g, "/").slice(0, 400)} |`);
  L.push("", "## 업로드", "", "| 대상 | 파일 | HTTP | 버전 · 행 |", "|---|---|---|---|");
  for (const u of r.uploads) L.push(`| ${u.code} | ${u.file} | ${u.status} | ${u.version ? `v${u.version} · ${u.rows ?? "-"}행` : u.docClass ?? ""} |`);
  L.push("", "## 이벤트 → 워크플로우", "", "| 이벤트 | 대상 | 매칭(사유) | 실행 |", "|---|---|---|---|");
  for (const e of r.flow) L.push(`| #${e.id} ${e.type} | ${e.payload.dataset ?? e.payload.doc_code ?? e.payload.workflow ?? ""} | ${e.matched.map((m) => (m.workflow ? `${m.workflow}(${(m.reasons ?? []).slice(0, 2).join(" · ")})` : m.note)).join("<br>")} | ${e.runs.map((x) => `${x.workflow}:${x.status}`).join("<br>")} |`);
  L.push("", "## 노드 결과", "");
  for (const [w, ns] of Object.entries(r.nodes)) {
    L.push(`### ${w}`, "", "| 노드 | 상태 | 소요 | 에이전트 | 요약 |", "|---|---|---|---|---|");
    for (const n of ns) L.push(`| ${n.key} | ${n.status} | ${n.ms ?? "-"}ms | ${n.agent ?? "-"} | ${n.summary} |`);
    L.push("");
  }
  L.push("## 에이전트 판단", "", "| 에이전트:결정 | LLM | 규칙 | 기타 | 예 |", "|---|---|---|---|---|");
  for (const [k, v] of Object.entries(r.decisions)) L.push(`| ${k} | ${v.llm} | ${v.rule} | ${v.other} | ${v.samples.join(" / ").replace(/\|/g, "/").slice(0, 200)} |`);
  L.push("", "## 핵심 수치 (커널 계산 · 표시값)", "", "| 지표 | 이전 | 이후 |", "|---|---|---|");
  for (const m of r.metrics) L.push(`| ${m.metric} | ${m.before ?? "-"} | ${m.after ?? "-"} |`);
  L.push("", "## 정의서 mart", "", "| 표 | 기준월 | 행 | 판정 요약 |", "|---|---|---|---|");
  for (const [k, v] of Object.entries(r.contracts.after)) L.push(`| ${k} | ${r.contracts.before[k]?.baseYm ?? "-"} → ${v.baseYm ?? "-"} | ${v.rows ?? "-"} | ${JSON.stringify(v.summary)} |`);
  L.push("", "## 의견 문장(이후)", "");
  for (const [k, v] of Object.entries(r.contracts.after)) if (v.summaryText) L.push(`- **${k}** ${v.summaryText.slice(0, 400)}`);
  L.push("", "## 질의", "", `- 질문: 2026년 9월 기준 소기업 6B 등급 실제부도율과 예측부도율 대표값 차이`, `- 모드 ${r.assist?.mode} · 모델 ${r.assist?.model ?? "-"} · 수치 출처 검증 ${r.assist?.verification?.passed}`, `- 답변: ${String(r.assist?.answer ?? "").replace(/\n/g, " ")}`, "");
  return L.join("\n");
}
