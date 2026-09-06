import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const TONE_CLASS = {
  primary: "bg-primary/10 text-primary",
  emerald: "bg-emerald-100 text-emerald-600",
  amber: "bg-amber-100 text-amber-600",
  red: "bg-red-100 text-red-600",
} as const;

export function StatCard({
  label,
  value,
  icon: Icon,
  tone,
  spin,
  loading,
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  tone: keyof typeof TONE_CLASS;
  spin?: boolean;
  loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-start justify-between">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <span className={cn("flex size-8 items-center justify-center rounded-full", TONE_CLASS[tone])}>
            <Icon className={cn("size-4", spin && "animate-spin")} />
          </span>
        </div>
        <p className="text-2xl font-bold">{loading ? "—" : value}</p>
      </CardContent>
    </Card>
  );
}
