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
  // 狀態轉 completed/failed 前每 2 秒重打一次 /status。文件列表本身也可能在差不多
  // 同時被 invalidate 出現同樣的「已完成」文字，斷言要限定在 dialog 範圍內避免
  // Playwright strict mode 撞到兩個相符節點。
  await expect(uploadDialog.getByText("已完成")).toBeVisible({ timeout: 90_000 });

  // 分類（auto_classify）在 processing_status 寫入 completed"之後"才觸發（見
  // CLAUDE.md 自動分類章節），文件列表沒有自己的輪詢、只在上傳完成當下 invalidate 一次，
  // 可能剛好搶在分類完成之前 refetch，所以用 reload 輪詢直到 Auto 標籤出現。
  const autoLabelBadge = page.getByText("AI 自動標籤");
  await expect(async () => {
    await page.reload();
    await expect(autoLabelBadge).toBeVisible();
  }).toPass({ timeout: 60_000, intervals: [3_000] });
});
