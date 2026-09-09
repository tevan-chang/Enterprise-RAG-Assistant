import { createBrowserClient } from "@supabase/ssr";

// @supabase/ssr 預設用 Supabase URL 的 host 推導 auth cookie 名稱（見
// node_modules/@supabase/ssr/dist/main/cookies.js），本地 Docker Compose 開發時
// middleware.ts 在 server 端連的是另一個 host（host.docker.internal），若不固定
// cookie 名稱，瀏覽器端寫入的 cookie 名稱會跟 middleware 期待讀取的名稱對不上，
// 導致 middleware 一律判定沒有 session（見 middleware.ts 同一個常數）。
export const SUPABASE_AUTH_COOKIE_NAME = "sb-auth-token";

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookieOptions: { name: SUPABASE_AUTH_COOKIE_NAME } },
  );
}
