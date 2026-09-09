import path from "node:path";
import dotenv from "dotenv";
import { createClient } from "@supabase/supabase-js";

import { E2E_USER } from "./test-user";

// supabase-js 的 realtime 子模組在建構時無條件檢查全域 WebSocket（Node 22+ 才內建），
// 這裡只用 auth admin API，用不到 realtime，補一個 polyfill 純粹是避免建構期噴錯。
if (typeof globalThis.WebSocket === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  (globalThis as { WebSocket?: unknown }).WebSocket = require("ws");
}

// 讀 backend/.env 取得本機 Supabase 的 service_role key（見 CLAUDE.md §8：backend 設定
// 讀 backend/.env，跟 repo 根目錄的 .env 是兩個獨立檔案，根目錄那份放的是 Supabase
// Cloud/Gmail 正式環境憑證，E2E 只能連本機 Supabase，不能誤用到那份）。
dotenv.config({ path: path.resolve(__dirname, "../backend/.env") });

const SUPABASE_URL = process.env.SUPABASE_URL ?? "http://127.0.0.1:54321";
const SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

async function globalSetup() {
  if (!SERVICE_ROLE_KEY) {
    throw new Error(
      "backend/.env 缺少 SUPABASE_SERVICE_ROLE_KEY，E2E 需要用 service_role key 建立測試使用者（見 e2e/global-setup.ts）。",
    );
  }

  const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
    auth: { autoRefreshToken: false, persistSession: false },
  });

  // 1. Upsert 測試使用者：tenant_id/role 一律放 app_metadata（見 backend/app/dependencies/auth.py
  //    的 get_current_user，只認 app_metadata，不是使用者可自行竄改的 user_metadata）。
  //    listUsers 不支援用 email 過濾，只能撈全部使用者用 .find() 比對；GoTrue 預設
  //    perPage=50，本機測試/開發帳號量不大，但顯式帶大一點的 perPage 避免帳號數一多，
  //    測試使用者剛好落到後面分頁而撈不到，導致下面誤判成「不存在」去 createUser 撞
  //    email 已存在的錯誤。
  const { data: existingUsers, error: listError } = await admin.auth.admin.listUsers({ perPage: 1000 });
  if (listError) throw listError;

  const existing = existingUsers.users.find((u) => u.email === E2E_USER.email);
  const appMetadata = { tenant_id: E2E_USER.tenantId, role: E2E_USER.role };

  if (existing) {
    const { error } = await admin.auth.admin.updateUserById(existing.id, {
      password: E2E_USER.password,
      app_metadata: appMetadata,
      email_confirm: true,
    });
    if (error) throw error;
  } else {
    const { error } = await admin.auth.admin.createUser({
      email: E2E_USER.email,
      password: E2E_USER.password,
      app_metadata: appMetadata,
      email_confirm: true,
    });
    if (error) throw error;
  }

  // 2. 清掉這個測試租戶之前留下的文件，避免重跑時撞到 content-hash 409（見
  //    routers/documents.py upload_document：同租戶內容雜湊重複一律回 409，force 也擋不掉）。
  //    documents row 刪除會 FK cascade 連 document_chunks 一起清（見 CLAUDE.md 雙軌分類鎖說明）。
  const { error: deleteError } = await admin.from("documents").delete().eq("tenant_id", E2E_USER.tenantId);
  if (deleteError) throw deleteError;
}

export default globalSetup;
