"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useSession } from "@/components/providers/SessionProvider";
import { EmptyState } from "@/components/ui/Layout";
import { Badge, DataTable, Td } from "@/components/ui/primitives";
import { qualityLabel } from "@/lib/labels";
import type { DatasetMeta } from "@/lib/types";

const QUALITY_TONE = { passed: "success", warning: "attention", failed: "critical" } as const;

/** 메뉴에 [자료 올리기] 화면이 있는지 — 데이터베이스 화면의 올리기 안내 · 행 단추를 같은 기준으로 (UploadCta 와 같음) */
export function useCanUpload() {
  const { menu } = useSession();
  return (menu?.sections ?? []).some((s) => [...s.flow, ...s.reference].some((i) => i.href === "/knowledge/upload"));
}

/**
 * [데이터베이스] 정형 데이터 표 (Phase E · UXF-05 · LAY-01) — 찾기, 품질은 배지 하나(통과가 아니면 이유를 덧붙임),
 * 올리기 권한이 있으면 행마다 '새 버전 올리기'(→ /knowledge/upload?target=코드).
 */
export function DatasetTable({ datasets }: { datasets: DatasetMeta[] }) {
  const canUpload = useCanUpload();
  const [q, setQ] = useState("");
  const [mineOnly, setMineOnly] = useState(false);
  const hasMine = datasets.some((d) => d.mine);
  const list = useMemo(() => {
    const low = q.trim().toLowerCase();
    const base = mineOnly ? datasets.filter((d) => d.mine) : datasets;
    if (!low) return base;
    return base.filter((d) => `${d.fileName} ${d.reportCode} ${d.datasetName ?? ""} ${d.dataset ?? ""} ${d.owner?.name ?? "전행 공통"} ${d.usedBy.join(" ")}`.toLowerCase().includes(low));
  }, [datasets, q, mineOnly]);
  const showAction = canUpload && datasets.some((d) => d.dataset);

  return (
    <div className="flex flex-col gap-sm">
      <div className="flex flex-wrap items-center gap-md">
        <input className="input !h-9 w-full max-w-[360px] text-[13px]" placeholder="파일 · 리포트코드 · 소유 팀 · 사용 화면으로 찾기" aria-label="정형 데이터 찾기" value={q} onChange={(e) => setQ(e.target.value)} data-dataset-search />
        {hasMine ? (
          <label className="inline-flex items-center gap-1.5 text-[12.5px] text-charcoal">
            <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} data-dataset-mine />
            우리 팀 자료만
          </label>
        ) : null}
      </div>
      {q.trim() ? (
        <p className="text-[11.5px] text-steel" aria-live="polite">
          {datasets.length}개 중 {list.length}개
        </p>
      ) : null}
      {list.length ? (
        <DataTable
          dense
          columns={[
            { key: "file", label: "파일" },
            { key: "code", label: "리포트코드", align: "center" },
            { key: "ym", label: "기준연월", align: "center" },
            { key: "owner", label: "소유 팀" },
            { key: "rows", label: "행", align: "right" },
            { key: "unit", label: "단위", align: "center" },
            { key: "quality", label: "품질" },
            { key: "usedBy", label: "사용 화면" },
            ...(showAction ? [{ key: "action", label: <span className="sr-only">작업</span> }] : []),
          ]}
        >
          {list.map((d) => (
            <tr key={`${d.dataset ?? ""}-${d.fileName}-${d.owner?.code ?? ""}`}>
              <Td strong>
                {d.fileName}
                {d.datasetName ? <span className="block text-[11px] font-medium text-stone">{d.datasetName}</span> : null}
              </Td>
              <Td align="center">{d.reportCode}</Td>
              <Td align="center">{d.asOfYm}</Td>
              <Td>
                {d.owner ? <Badge tone={d.mine ? "info" : "neutral"}>{d.owner.name}</Badge> : <span className="text-[11px] text-stone">전행 공통</span>}
              </Td>
              <Td align="right">{d.rows.toLocaleString("ko-KR")}</Td>
              <Td align="center">{d.unit}</Td>
              <Td>
                <span className="flex flex-col gap-1">
                  <Badge tone={QUALITY_TONE[d.quality] ?? "neutral"}>{qualityLabel(d.quality)}</Badge>
                  {d.quality !== "passed" && d.qualityNote ? <span className="text-[10.5px] leading-snug text-stone">{d.qualityNote}</span> : null}
                </span>
              </Td>
              <Td>
                <span className="text-[11px] text-steel">{d.usedBy.join(" · ")}</span>
              </Td>
              {showAction ? (
                <Td>
                  {d.dataset ? (
                    <Link
                      href={`/knowledge/upload?target=${encodeURIComponent(d.dataset)}`}
                      className="inline-flex whitespace-nowrap rounded-pill border border-hairline px-3 py-1.5 text-[12px] font-bold text-ink-deep hover:bg-surface-soft"
                      aria-label={`${d.datasetName ?? d.fileName} 새 버전 올리기`}
                      data-dataset-upload={d.dataset}
                    >
                      새 버전 올리기
                    </Link>
                  ) : null}
                </Td>
              ) : null}
            </tr>
          ))}
        </DataTable>
      ) : (
        <EmptyState compact title="맞는 자료가 없습니다" description="찾는 말을 바꿔 보세요." />
      )}
    </div>
  );
}

/** 데이터베이스 화면 아래 안내 — 올리기 권한에 따라 다르게 (Phase E · TXT-01) */
export function KnowledgeFootnote() {
  const canUpload = useCanUpload();
  return (
    <p className="text-[11.5px] leading-relaxed text-stone">
      {canUpload
        ? "새 자료는 [자료 올리기]에서 올리면 보안 · 형식 · 품질 검사 후 부서 데이터 책임자 또는 관리자의 승인을 거쳐 반영됩니다. 문서는 본문 추출 · 임베딩 색인 · 온톨로지 연결이 이어서 실행됩니다."
        : "자료는 부서 데이터 책임자 또는 관리자의 승인을 거쳐 반영됩니다. 새 자료를 올려야 하면 소속 부서의 데이터 책임자나 관리자에게 [자료 올리기] 권한을 요청하세요."}
    </p>
  );
}
