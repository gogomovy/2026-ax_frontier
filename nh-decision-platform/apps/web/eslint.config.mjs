// ESLint flat config (Next.js 16 — `next lint` 제거, ESLint CLI 직접 사용)
import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...nextVitals,
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts", "public/**"] },
];

export default config;
