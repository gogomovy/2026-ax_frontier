export const dynamic = "force-static";

export function GET() {
  return Response.json({
    status: "ok",
    service: "nhdip-web",
    dataSource: process.env.NEXT_PUBLIC_DATA_SOURCE ?? "mock",
    asOf: process.env.NEXT_PUBLIC_AS_OF ?? "2026-08-31",
  });
}
