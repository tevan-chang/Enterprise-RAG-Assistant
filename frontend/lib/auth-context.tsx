"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";

import { createClient } from "@/lib/supabase/client";

type Auth = {
  session: Session | null;
  user: User | null;
  /** 從 JWT app_metadata 解出，純 UX 遮罩用（例如是否顯示「整理」按鈕）。
   * 真正的授權邊界永遠在後端重新驗證 JWT（見 CLAUDE.md 雙層權限隔離）。 */
  tenantId: string | null;
  role: string | null;
  isLoading: boolean;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const supabase = createClient();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setIsLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });

    return () => subscription.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signOut = async () => {
    await supabase.auth.signOut();
  };

  const user = session?.user ?? null;
  const appMetadata = (user?.app_metadata ?? {}) as { tenant_id?: string; role?: string };

  return (
    <AuthContext.Provider
      value={{
        session,
        user,
        tenantId: appMetadata.tenant_id ?? null,
        role: appMetadata.role ?? null,
        isLoading,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): Auth {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必須在 AuthProvider 內使用");
  return ctx;
}
