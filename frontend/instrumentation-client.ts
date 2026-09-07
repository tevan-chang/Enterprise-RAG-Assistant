import * as Sentry from "@sentry/nextjs";

// 前端 Sentry 接入（見 docs/spec_v3.1.md §2.5 / §3.5、roadmap Day 9）：只做客戶端錯誤回報，
// 對應 app/error.tsx route-level error boundary；沒有另外接 server/edge instrumentation，
// 後端已由 backend/app/observability.py 的 Python SDK 各自處理。
// 未設定 NEXT_PUBLIC_SENTRY_DSN（例如本地開發沒申請帳號）時 dsn 傳空字串，SDK 會直接跳過送出事件。
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,
});
