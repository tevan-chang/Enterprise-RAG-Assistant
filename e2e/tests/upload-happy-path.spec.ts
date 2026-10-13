import path from "node:path";
import { expect, test } from "@playwright/test";

import { E2E_USER } from "../test-user";

const TEST_PDF_PATH = path.resolve(__dirname, "../../docs/test_document.pdf");

// 見 roadmap Day 10：唯一一條 Playwright Happy Path。
// 流程：登入 → 上傳 PDF → Polling 轉 Completed → 文件列表出現 Auto 標籤（虛線 + Wand2）。
// Chat/Report/Gmail 通知一律不進這支測試（見 CLAUDE.md Guardrail #7），改由 backend/tests/
// 的 Pytest API 合約測試覆蓋。
test("上傳 PDF 後解析完成並顯示 AI 自動標籤", async ({ page }) => {
  await page.goto("/login");
  // Shadcn Form 的 FormLabel 沒有用 htmlFor 綁定 input（見 frontend/app/login/page.tsx），
  // getByLabel 撈不到，改用 input type 定位（頁面上僅此一組登入表單）。
  await page.locator('input[type="email"]').fill(E2E_USER.email);
  await page.locator('input[type="password"]').fill(E2E_USER.password);
  await page.getByRole("button", { name: "登入工作區" }).click();

  await page.waitForURL("/");

  await page.goto("/documents");
  await page.getByRole("button", { name: "+ 上傳新文件" }).click();

  const uploadDialog = page.getByRole("dialog");
  await uploadDialog.locator('input[type="file"]').setInputFiles(TEST_PDF_PATH);
  await uploadDialog.getByRole("button", { name: "上傳" }).click();

  // 上傳 modal 內建 Polling（見 frontend/components/upload-document-modal.tsx），
  // 狀態轉 completed/failed 前每 2 秒重打一次 /status。modal 的「已完成」文字只在
  // processing_status 與 classification_status 兩者都收斂後才顯示（isFullyResolved），
  // 分類仍在跑時會先顯示「分類中」，所以看到「已完成」此時分類必定也已完成，
  // 且 modal 在判定收斂的同一刻已呼叫 invalidateQueries(["documents"])，
  // 不需要額外 reload 輪詢等文件列表的 Auto 標籤出現。斷言限定在 dialog 範圍內，
  // 避免 Playwright strict mode 撞到文件列表裡同樣的「已完成」文字。
  await expect(uploadDialog.getByText("已完成")).toBeVisible({ timeout: 90_000 });
  // invalidateQueries 只是標記 stale、觸發下一次 refetch，不是同步完成；多留一點餘裕
  // 給 /api/documents 的網路往返與 React re-render，避免 CI 環境偶發延遲造成誤判為失敗。
  await expect(page.getByText("AI 自動標籤")).toBeVisible({ timeout: 20_000 });
});
