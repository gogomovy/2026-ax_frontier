#!/usr/bin/env node
/**
 * 프론트 목데이터(apps/web/src/mock/*.ts) → 백엔드 시드 JSON 추출.
 *
 *   node infra/scripts/export-mock.mjs
 *
 * 1) TypeScript 컴파일러(apps/web/node_modules/typescript)로 mock 모듈을 CommonJS 로 변환
 * 2) 각 화면 데이터 상수를 apps/api/src/nhdip/seed/screens/<key>.json 으로 저장
 *
 * 화면 산출물의 최초 세대(generation 0)가 된다. 이후 값은 워크플로우가 계산해 교체한다.
 */
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const webDir = path.join(root, "apps/web");
const mockDir = path.join(webDir, "src/mock");
const outDir = path.join(root, "apps/api/src/nhdip/seed/screens");
const require = createRequire(path.join(webDir, "package.json"));
const ts = require("typescript");

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "nhdip-mock-"));
for (const file of fs.readdirSync(mockDir).filter((f) => f.endsWith(".ts"))) {
  const src = fs.readFileSync(path.join(mockDir, file), "utf8");
  const out = ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
  });
  fs.writeFileSync(path.join(tmp, file.replace(/\.ts$/, ".js")), out.outputText);
}

const load = (name) => createRequire(path.join(tmp, "x.js"))(`./${name}.js`);
const dashboard = load("dashboard");
const finance = load("finance");
const goals = load("goals");
const knowledge = load("knowledge");
const risk = load("risk");
const terms = load("terms");
const helpers = load("helpers");
const branch = load("branch");

const artifacts = {
  domains: dashboard.DOMAINS,
  hq_dashboard: dashboard.HQ_DASHBOARD,
  attentions: dashboard.ATTENTIONS,
  report_requests: dashboard.REPORT_REQUESTS,
  loan_overview: finance.LOAN_OVERVIEW,
  comparison_view: finance.COMPARISON_VIEW,
  capital_view: finance.CAPITAL_VIEW,
  profitability: finance.PROFITABILITY,
  goals: goals.GOALS,
  proposals: goals.PROPOSALS,
  review_queue: goals.REVIEW_QUEUE,
  cascade: goals.CASCADE,
  risk_dashboard: risk.RISK_DASHBOARD,
  analysis_tabs: { current: risk.ANALYSIS_TABS, previous: risk.PREVIOUS_TABS },
  inclusive: risk.INCLUSIVE,
  action_plans: risk.ACTION_PLANS,
  default_rate_trend: risk.DEFAULT_RATE_TREND,
  branch_targets: risk.BRANCH_TARGETS,
  documents: knowledge.DOCUMENTS,
  dataset_meta: knowledge.DATASETS,
  terms: terms.TERMS,
  insights: [risk.MODEL_OPINION, risk.INCLUSIVE_OPINION, finance.DIVERGENCE_INSIGHT],
  meta: { asOf: helpers.AS_OF, generatedAt: helpers.GENERATED_AT, batchLabel: helpers.BATCH_LABEL },
  // 영업점 (B.29) — 산출물 안의 office.code 로 열람 범위를 판정한다
  branch_dashboard: branch.BRANCH_DASHBOARD,
  branch_tabs: branch.BRANCH_TABS,
};
for (const [tabKey, report] of Object.entries(risk.REPORTS)) artifacts[`report.${tabKey}`] = report;
for (const [tabKey, report] of Object.entries(branch.BRANCH_REPORTS)) artifacts[`report.branch-${tabKey}`] = report;

fs.mkdirSync(outDir, { recursive: true });
for (const f of fs.readdirSync(outDir)) if (f.endsWith(".json")) fs.unlinkSync(path.join(outDir, f));
for (const [key, value] of Object.entries(artifacts)) {
  fs.writeFileSync(path.join(outDir, `${key}.json`), JSON.stringify(value, null, 1) + "\n");
}
// 시드 계산용 원천 값 (데이터셋 시뮬레이션 버전 생성에 사용)
const raw = {
  micro_grades: risk.MICRO_GRADES,
  micro_psi_buckets: risk.MICRO_PSI_BUCKETS,
  micro_total: risk.MICRO_TOTAL,
  corp_models: risk.CORP_MODELS,
  retail_models: risk.RETAIL_MODELS,
  inclusive_products: risk.INCLUSIVE_PRODUCTS,
};
fs.writeFileSync(path.join(outDir, "..", "mock_raw.json"), JSON.stringify(raw, null, 1) + "\n");
fs.rmSync(tmp, { recursive: true, force: true });
console.log(`exported ${Object.keys(artifacts).length} artifacts → ${path.relative(root, outDir)}`);
