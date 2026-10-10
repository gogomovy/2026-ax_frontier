import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// 프론트 단위 테스트 (B.33) — 화면 없이 확인할 수 있는 순수 로직(형식 · 보안 · 접근성 규칙)
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
