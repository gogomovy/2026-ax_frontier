export const dynamic = "force-static";

/** 웹 상태 확인 — 데이터 기준일은 백엔드 화면 API 가 알린다 */
export function GET() {
  return Response.json({
    status: "ok",
    service: "nhdip-web",
  });
}
