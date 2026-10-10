import { notFound } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { LinkButton, SectionHead, TextLink } from "@/components/ui/primitives";
import { getDomain, getDomains } from "@/lib/data";

const PLANNED_SCOPE = [
  "사업부문 Dashboard 및 AI 주요 Attention",
  "부문별 경영목표 List 및 수정·신규 제안",
  "정부정책 · 경영 의사결정 근거 연결",
  "확정 목표의 사업부서 · 영업점 전파",
];

// 데이터(분석 탭·문서)가 실행 시점에 바뀌므로 요청 시 렌더링한다
export const dynamic = "force-dynamic";

export default async function DomainPlaceholderPage(props: { params: Promise<{ domain: string }> }) {
  const params = await props.params;
  const domain = await getDomain(params.domain);
  if (!domain) notFound();

  return (
    <>
      <PageHeader
        crumbs={[{ label: "현황·목표", href: "/hq/overview" }, { label: domain.name }]}
        title={`${domain.name} 부문 — 준비 중`}
        description="1차 범위는 여신 부문입니다. 이 부문은 도메인 정의 · 지표 정의 · Agent 플레이북 설정만 등록하면 동일한 구조로 동작합니다."
      />

      <div className="shell">
        <SectionHead title="예정 범위" hint="신규 코드 추가 없이 설정 등록만으로 동작하도록 설계되어 있습니다" />
        <ul className="flex flex-col divide-y divide-hairline-soft overflow-hidden rounded-xl border border-hairline-soft">
          {PLANNED_SCOPE.map((item) => (
            <li key={item} className="px-base py-2.5 text-[13px] text-charcoal">
              {item}
            </li>
          ))}
        </ul>

        <div className="mt-lg flex flex-wrap items-center gap-md">
          <LinkButton href="/hq/overview" size="sm">
            현황·목표로 돌아가기
          </LinkButton>
          <TextLink href="/hq/analysis">여신 부문 구현 화면</TextLink>
        </div>
      </div>
    </>
  );
}
