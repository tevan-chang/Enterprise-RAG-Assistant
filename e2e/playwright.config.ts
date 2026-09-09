import { defineConfig, devices } from "@playwright/test";

// 見 CLAUDE.md Guardrail #7：Playwright 僅涵蓋「上傳解析」1 條 Happy Path，
// Chat/Report/Gmail 一律走 backend/tests/ 的 Pytest API 合約測試，不得擴充進這裡。
//
// 前置：本機 Supabase（`supabase start`）+ backend + frontend 三者需先跑起來，可以是
// `docker compose --env-file frontend/.env.local up --build`，也可以是各自 `npm run dev`
// / `uvicorn app.main:app --reload`（見根目錄 README「E2E 測試」章節）。
export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  globalSetup: require.resolve("./global-setup"),
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
