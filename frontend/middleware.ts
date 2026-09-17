import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { SUPABASE_AUTH_COOKIE_NAME } from "@/lib/supabase/client";

const PUBLIC_PATHS = ["/login", "/privacy"];

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });

  // middleware 跑在 Next.js server 端（Docker Compose 本地開發時是 frontend container 內部），
  // 呼叫 Supabase Auth 的網路位置跟瀏覽器端不同：瀏覽器用 NEXT_PUBLIC_SUPABASE_URL（如
  // http://localhost:54321）就能連到本機 Supabase CLI 開的埠；但同一個網址在 frontend
  // container 內部指向的是 container 自己，連不到 host 上的 Supabase，所以另外提供
  // SUPABASE_URL_INTERNAL（如 http://host.docker.internal:54321）給這裡專用，非 Docker 環境
  // 下不需要設定，直接 fallback 回 NEXT_PUBLIC_SUPABASE_URL。
  const supabaseUrl = process.env.SUPABASE_URL_INTERNAL || process.env.NEXT_PUBLIC_SUPABASE_URL!;

  const supabase = createServerClient(
    supabaseUrl,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookieOptions: { name: SUPABASE_AUTH_COOKIE_NAME },
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const isPublicPath = PUBLIC_PATHS.some((path) => request.nextUrl.pathname.startsWith(path));

  if (!user && !isPublicPath) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  if (user && isPublicPath) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
