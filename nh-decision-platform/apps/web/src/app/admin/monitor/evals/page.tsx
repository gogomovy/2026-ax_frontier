"use client";
import { AdminPage, C, Card, Collapse, JsonView, Loading, Table, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";

interface Category {
  passed: number;
  total: number;
  rate: number;
  threshold: number;
  ok: boolean;
  failures: Record<string, unknown>[];
}
interface Report {
  version: number;
  at: string;
  passed: boolean;
  categories: Record<string, Category>;
}
const LABEL: Record<string, string> = {
  metrics: "확정 수치(커널)",
  verdicts: "판정(규칙)",
  artifacts: "화면 산출물 값",
  narration: "서술 숫자 출처(마커)",
  retrieval: "근거 검색",
  assist: "질의 지표 선택",
};

/** 골든셋 평가 (작업 8.1) — 시나리오 기준값 · 추천안 결정값과 현재 계산 · 화면 · 검색 결과를 대조 */
export default function EvalsAdmin() {
  const data = useApiData<Report>("/admin/evals/latest");
  const { busy, run } = useAction();
  const rep = data.data;
  return (
    <AdminPage
      title="골든셋 평가"
      description="시나리오 기준값(6B 7.929% · PSI 0.082 · 충당금 비중 9.16% 등)과 추천안으로 확정한 값이 현재 계산 · 화면 · 근거 검색 · 질의 결과와 같은지 확인합니다. 같은 평가가 CI 에서도 실행됩니다."
      actions={
        <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost("/admin/evals/run"), "평가를 실행했습니다", data.reload)}>
          지금 평가
        </Button>
      }
    >
      <Card title={rep ? <span>결과 · {fmtTime(rep.at)} · <Badge tone={rep.passed ? "success" : "critical"}>{rep.passed ? "통과" : "기준 미달"}</Badge></span> : "결과"}>
        <Loading error={data.error && !rep ? "아직 평가 결과가 없습니다 — [지금 평가]를 누르세요" : null} loading={!rep && data.loading} />
        {rep ? (
          <Table head={["범주", "통과", "비율", "기준", "판정", "실패 항목"]}>
            {Object.entries(rep.categories).map(([k, c]) => (
              <tr key={k} data-eval-category={k}>
                <C>{LABEL[k] ?? k}</C>
                <C right>
                  {c.passed}/{c.total}
                </C>
                <C right>{Math.round(c.rate * 100)}%</C>
                <C right>{Math.round(c.threshold * 100)}%</C>
                <C>
                  <Badge tone={c.ok ? "success" : "critical"}>{c.ok ? "통과" : "미달"}</Badge>
                </C>
                <C className="min-w-[240px]">{c.failures.length ? <Collapse label={`${c.failures.length}건`}><JsonView value={c.failures} maxHeight={220} /></Collapse> : "-"}</C>
              </tr>
            ))}
          </Table>
        ) : null}
      </Card>
    </AdminPage>
  );
}
