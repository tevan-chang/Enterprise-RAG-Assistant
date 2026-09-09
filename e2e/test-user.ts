// 見 roadmap Day 10：唯一一條 Playwright Happy Path 共用的測試租戶/使用者設定，
// global-setup.ts 負責建立（idempotent upsert），tests/*.spec.ts 負責登入使用。
export const E2E_USER = {
  email: "e2e-demo@enterprise-rag.test",
  password: "E2E-demo-pass-12345",
  tenantId: "e2e-demo-tenant",
  role: "admin",
} as const;
