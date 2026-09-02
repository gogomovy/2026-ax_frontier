import path from "node:path";
import { fileURLToPath } from "node:url";

const workspaceRoot = fileURLToPath(new URL("../../..", import.meta.url));

export const config = {
  port: Number(process.env.PORT ?? 3001),
  databaseUrl: process.env.DATABASE_URL ?? "postgresql://ax:ax@127.0.0.1:5432/ax_frontier",
  knowledgeFilesDir: process.env.KNOWLEDGE_FILES_DIR ?? path.join(workspaceRoot, "data", "knowledge"),
  officialSearchApiKey: process.env.OFFICIAL_SEARCH_API_KEY ?? "",
  hwpExtractCmd: process.env.HWP_EXTRACT_CMD ?? "",
  workspaceRoot,
};
