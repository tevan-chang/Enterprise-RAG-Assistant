"use client";

import { createContext, useContext, useEffect, useState } from "react";

/**
 * 開發期身分模擬（非正式 Auth）：後端目前用 X-Tenant-Id / X-User-Role header
 * 做租戶隔離與角色判斷（見 CLAUDE.md 架構總覽「雙層權限隔離」），尚未接上
 * Supabase Auth JWT 流程。這裡用下拉選單模擬切換身分，方便驗證 RBAC 行為，
 * 不是真正的登入頁面。
 */

export type UserRole = "admin" | "editor" | "viewer";

type DevIdentity = {
  tenantId: string;
  role: UserRole;
  setTenantId: (tenantId: string) => void;
  setRole: (role: UserRole) => void;
};

const STORAGE_KEY = "dev-identity";
const DEFAULT_IDENTITY = { tenantId: "tenant_a", role: "admin" as UserRole };

const DevIdentityContext = createContext<DevIdentity | null>(null);

export function DevIdentityProvider({ children }: { children: React.ReactNode }) {
  const [tenantId, setTenantId] = useState(DEFAULT_IDENTITY.tenantId);
  const [role, setRole] = useState<UserRole>(DEFAULT_IDENTITY.role);

  useEffect(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as { tenantId?: string; role?: UserRole };
      if (parsed.tenantId) setTenantId(parsed.tenantId);
      if (parsed.role) setRole(parsed.role);
    } catch {
      // 忽略壞掉的 localStorage 值，維持預設身分
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ tenantId, role }));
  }, [tenantId, role]);

  return (
    <DevIdentityContext.Provider value={{ tenantId, role, setTenantId, setRole }}>
      {children}
    </DevIdentityContext.Provider>
  );
}

export function useDevIdentity(): DevIdentity {
  const ctx = useContext(DevIdentityContext);
  if (!ctx) throw new Error("useDevIdentity 必須在 DevIdentityProvider 內使用");
  return ctx;
}
