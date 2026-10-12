import Link from "next/link";
import { UploadCta } from "@/components/knowledge/UploadCta";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, DataTable, IconChevron, SectionHead, Td } from "@/components/ui/primitives";
import { formatDate } from "@/lib/format";
import { getDatasets, getDocuments } from "@/lib/data";

const CARDS = [
  {
    dbClass: "gov_policy",
    title: "정부정책 데이터베이스",
    description: "금융위·금감원 등 외부 정책 문서. 경영목표 판단의 외부 근거로 사용됩니다.",
  },
  {
    dbClass: "mgmt_decision",
    title: "경영 의사결정사항",
    description: "경영전략회의·사업계획·지주 통보 등 내부 전략 자료. 정부정책 DB 와 분리 관리합니다.",
  },
  {
    dbClass: "model_method",
    title: "모형·방법론 문서",
    description: "모니터링 보고서와 통계 용어 해설. 용어집 온톨로지의 원천입니다.",
  },
  {
    dbClass: "branch_ref",
    title: "영업점 기준·공문",
    description: "업적평가 세부기준과 본부가 영업점에 배포한 공문. 영업점 영업 가이드의 근거로 사용됩니다.",
  },
];

const QUALITY_TONE = { passed: "success", warning: "attention", failed: "critical" } as const;
const QUALITY_LABEL = { passed: "검증 통과", warning: "주의", failed: "실패" } as const;

export default async function KnowledgePage() {
  const [docs, datasets] = await Promise.all([getDocuments(), getDatasets()]);

  return (
    <>
      <PageHeader
        eyebrow="참고"
        title="데이터베이스"
        description="Agent 판단의 근거가 되는 문서와 정형 데이터입니다. 문서는 원본과 메타데이터를 함께 보관하며 관련성 판단을 통해 선별 사용됩니다."
        actions={<UploadCta />}
      />

      <div className="shell flex flex-col gap-xxl">
        <section>
          <SectionHead title="지식 원천" hint="카드를 선택하면 문서 목록과 메타데이터가 열립니다" />
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-4">
            {CARDS.map((card) => {
              const list = docs.filter((d) => d.dbClass === card.dbClass);
              const latest = list.slice().sort((a, b) => b.registeredAt.localeCompare(a.registeredAt))[0];
              return (
                <Link key={card.dbClass} href={`/knowledge/${card.dbClass}`} className="block h-full">
                  <div className="panel h-full px-base py-3.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="text-[14.5px] font-bold text-ink-deep">{card.title}</p>
                      <span className="text-[11.5px] font-bold text-steel tnum">{list.length}건</span>
                    </div>
                    <p className="mt-1 text-[12.5px] leading-relaxed text-steel">{card.description}</p>
                    {latest ? (
                      <p className="mt-2.5 text-[11px] text-stone">
                        최근 등록 {formatDate(latest.registeredAt)} · {latest.title}
                      </p>
                    ) : null}
                    <span className="mt-2 inline-flex items-center gap-1 text-[12px] font-bold text-primary">
                      문서 목록 <IconChevron />
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        </section>

        <section>
          <SectionHead
            title="정형 데이터 ([데이터] 엑셀)"
            hint={`${datasets.length}개 파일 · 파일명 규약 (YYYYMM)조회코드_명칭.xlsx 으로 기준연월·리포트코드를 자동 인식`}
          />
          <DataTable
            dense
            columns={[
              { key: "file", label: "파일" },
              { key: "code", label: "리포트코드", align: "center" },
              { key: "ym", label: "기준연월", align: "center" },
              { key: "rows", label: "행", align: "right" },
              { key: "unit", label: "단위", align: "center" },
              { key: "quality", label: "품질" },
              { key: "usedBy", label: "사용 화면" },
            ]}
          >
            {datasets.map((d) => (
              <tr key={d.fileName}>
                <Td strong>{d.fileName}</Td>
                <Td align="center">{d.reportCode}</Td>
                <Td align="center">{d.asOfYm}</Td>
                <Td align="right">{d.rows.toLocaleString("ko-KR")}</Td>
                <Td align="center">{d.unit}</Td>
                <Td>
                  <span className="flex flex-col gap-1">
                    <Badge tone={QUALITY_TONE[d.quality]}>{QUALITY_LABEL[d.quality]}</Badge>
                    <span className="text-[10.5px] leading-snug text-stone">{d.qualityNote}</span>
                  </span>
                </Td>
                <Td>
                  <span className="text-[11px] text-steel">{d.usedBy.join(" · ")}</span>
                </Td>
              </tr>
            ))}
          </DataTable>
        </section>

        <p className="text-[11.5px] leading-relaxed text-stone">
          새 자료는 [자료 올리기]에서 올리면 보안 · 형식 · 품질 검사 후 관리자 승인을 거쳐 반영됩니다. 문서는 본문 추출 · 임베딩 색인 · 온톨로지 연결이 이어서 실행됩니다.
        </p>
      </div>
    </>
  );
}
