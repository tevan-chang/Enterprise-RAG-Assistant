"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useDevIdentity, type UserRole } from "@/lib/dev-identity";

const TENANT_OPTIONS = ["tenant_a", "tenant_b"];
const ROLE_OPTIONS: UserRole[] = ["admin", "editor", "viewer"];

/** 開發期身分模擬切換器，見 lib/dev-identity.tsx 說明。 */
export function IdentitySwitcher() {
  const { tenantId, role, setTenantId, setRole } = useDevIdentity();

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">身分模擬：</span>
      <Select value={tenantId} onValueChange={(value) => value && setTenantId(value)}>
        <SelectTrigger className="w-32">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {TENANT_OPTIONS.map((tenant) => (
            <SelectItem key={tenant} value={tenant}>
              {tenant}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={role} onValueChange={(value) => setRole(value as UserRole)}>
        <SelectTrigger className="w-28">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {ROLE_OPTIONS.map((r) => (
            <SelectItem key={r} value={r}>
              {r}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
