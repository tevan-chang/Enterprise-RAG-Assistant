"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileText, MessageSquare, Sparkles, Upload } from "lucide-react";

import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth-context";
import { SignOutButton } from "@/components/sign-out-button";

const NAV_ITEMS = [
  { href: "/chat", label: "知識問答", icon: MessageSquare },
  { href: "/documents", label: "文件列表", icon: FileText },
  { href: "/documents/upload", label: "上傳文件", icon: Upload },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, role, isLoading } = useAuth();

  return (
    <div className="flex min-h-screen bg-muted/30">
      <aside className="flex w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
        <Link href="/" className="flex items-center gap-2 px-5 py-5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
            <Sparkles className="size-4" />
          </span>
          <span className="text-sm leading-tight font-semibold">
            Enterprise AI
            <br />
            Knowledge Assistant
          </span>
        </Link>

        <nav className="flex flex-1 flex-col gap-1 px-3">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-sidebar-border px-3 py-3">
          {!isLoading && user && (
            <div className="mb-2 truncate px-1">
              <p className="truncate text-xs font-medium text-sidebar-foreground">{user.email}</p>
              {role && <p className="truncate text-xs text-muted-foreground">{role}</p>}
            </div>
          )}
          <SignOutButton />
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
