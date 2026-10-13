import Link from "next/link";
import { DatasetTable, KnowledgeFootnote } from "@/components/knowledge/DatasetTable";
import { UploadCta } from "@/components/knowledge/UploadCta";
import { PageHeader } from "@/components/layout/PageHeader";
import { IconChevron, SectionHead } from "@/components/ui/primitives";
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

export default async function KnowledgePage() {
  const [docs, datasets] = await Promise.all([getDocuments(), getDatasets()]);

  return (
    <>
      <PageHeader
        eyebrow="참고"
        title="데이터베이스"
        description="AI 판단의 근거가 되는 문서와 정형 데이터입니다. 문서는 원본과 메타데이터를 함께 보관하며 관련성 판단을 통해 선별 사용됩니다."
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
            hint={`현재 확정 버전 ${datasets.length}개 · 파일 이름이 규약 (YYYYMM)조회코드_명칭.xlsx 이면 [자료 올리기]가 맞는 자료를 추천합니다`}
          />
          <DatasetTable datasets={datasets} />
        </section>

        <KnowledgeFootnote />
      </div>
    </>
  );
}
