"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export function SignOutButton() {
  const router = useRouter();
  const { signOut } = useAuth();

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={async () => {
        await signOut();
        router.push("/login");
        router.refresh();
      }}
    >
      登出
    </Button>
  );
}
