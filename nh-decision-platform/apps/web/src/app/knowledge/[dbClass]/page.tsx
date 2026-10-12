import Link from "next/link";
import { notFound } from "next/navigation";
import { TermText } from "@/components/data/TermText";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, DataTable, SectionHead, Td } from "@/components/ui/primitives";
import { API_MODE } from "@/lib/config";
import { formatDate } from "@/lib/format";
import { getDocuments, getTerms } from "@/lib/data";

const META: Record<string, { title: string; description: string }> = {
  gov_policy: {
    title: "정부정책 데이터베이스",
    description:
      "외부 정책 문서를 저장합니다. 공식 정부·금융당국 자료를 주요 근거로 사용하고 기사 등은 보조자료로만 활용합니다.",
  },
  mgmt_decision: {
    title: "경영 의사결정사항 데이터베이스",
    description:
      "경영전략회의·사업계획·지주 통보 등 내부 전략 자료입니다. 정부정책 DB 와 물리적·논리적으로 분리 관리합니다.",
  },
  model_method: {
    title: "모형·방법론 문서",
    description:
      "모니터링 보고서와 통계방법론·용어 해설입니다. 용어집 온톨로지의 원천으로 사용되어 보고서 도움말과 연결됩니다.",
  },
  branch_ref: {
    title: "영업점 기준·공문",
    description:
      "업적평가 세부기준(반기)과 본부가 영업점에 배포한 공문입니다. 영업점 Agent 는 이 분류와 정부정책 DB 만 근거로 쓰고, 본부 내부 문서는 인용하지 않습니다.",
  },
};

const ACCESS_LABEL = { public: "공개", internal: "행내", dept_only: "부서한정" } as const;
const ACCESS_TONE = { public: "success", internal: "info", dept_only: "critical" } as const;

// 데이터(분석 탭·문서)가 실행 시점에 바뀌므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";

export default async function KnowledgeDbPage(props: { params: Promise<{ dbClass: string }> }) {
  const params = await props.params;
  const meta = META[params.dbClass];
  if (!meta) notFound();

  const [docs, terms] = await Promise.all([getDocuments(params.dbClass), getTerms()]);

  return (
    <>
      <PageHeader
        crumbs={[{ label: "데이터베이스", href: "/knowledge" }, { label: meta.title }]}
        title={meta.title}
        description={meta.description}
      />

      <div className="shell flex flex-col gap-xxl">
        <section>
          <SectionHead
            title="문서 목록"
            hint={`${docs.length}건 · 부서한정 문서는 권한 범위 밖 사용자에게 노출되지 않습니다`}
          />
          <DataTable
            columns={[
              { key: "title", label: "문서명" },
              { key: "issuer", label: "기관·출처" },
              { key: "date", label: "기준일", align: "center" },
              { key: "domain", label: "적용 사업부문" },
              { key: "access", label: "접근등급", align: "center" },
              { key: "pages", label: "면", align: "right" },
              { key: "used", label: "근거 사용", align: "right" },
            ]}
          >
            {docs.map((doc) => (
              <tr key={doc.docId}>
                <Td strong>
                  {API_MODE ? (
                    <Link href={`/knowledge/doc?id=${encodeURIComponent(doc.docId)}`} className="hover:underline" data-doc-link>
                      {doc.title}
                    </Link>
                  ) : (
                    doc.title
                  )}
                  <span className="mt-0.5 block text-[10.5px] font-normal text-stone">{doc.fileName}</span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    {doc.tags.slice(0, 3).map((t) => (
                      <span key={t} className="rounded-pill bg-surface-soft px-1.5 py-0.5 text-[10px] text-steel">
                        #{t}
                      </span>
                    ))}
                  </span>
                </Td>
                <Td>
                  {doc.issuer}
                  {doc.isOfficial ? (
                    <span className="ml-1 rounded-pill bg-success-soft px-1.5 py-0.5 text-[10px] font-bold text-success">
                      공식
                    </span>
                  ) : null}
                  <span className="mt-0.5 block text-[10.5px] text-stone">{doc.docType}</span>
                </Td>
                <Td align="center">{formatDate(doc.effectiveDate)}</Td>
                <Td>{doc.domainLabels.join(" · ")}</Td>
                <Td align="center">
                  <Badge tone={ACCESS_TONE[doc.accessClass]}>{ACCESS_LABEL[doc.accessClass]}</Badge>
                </Td>
                <Td align="right">{doc.pageCount}</Td>
                <Td align="right">{doc.usedByCount}회</Td>
              </tr>
            ))}
          </DataTable>
        </section>

        {params.dbClass === "model_method" ? (
          <section>
            <SectionHead
              title="용어집 온톨로지"
              hint={`${terms.length}개 용어 · 보고서 본문의 용어에 호버·클릭하면 이 정의와 근거문서가 표시됩니다`}
            />
            <div className="grid grid-cols-1 gap-md md:grid-cols-2 xl:grid-cols-3">
              {terms.map((term) => (
                <div key={term.termCode} className="rounded-2xl border border-hairline-soft px-base py-3.5">
                  <div className="mb-1 flex items-center gap-1.5">
                    <TermText code={term.termCode} />
                    <span className="text-[10.5px] text-stone">{term.termCode}</span>
                  </div>
                  <p className="text-[12.5px] leading-snug text-charcoal">{term.definition}</p>
                  {term.formula ? (
                    <p className="mt-1.5 rounded-md bg-surface-soft px-2 py-1 font-mono text-[10.5px] text-steel">
                      {term.formula}
                    </p>
                  ) : null}
                  <p className="mt-1.5 text-[10.5px] text-stone">
                    근거 · {term.src.title} p.{term.src.page}
                  </p>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </>
  );
}
