"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

import { Button } from "@/components/ui/button";

/** Route-level error boundary（見 spec §3.5 / roadmap Day 9）：Next.js 不會自動把這裡攔到的
 * render 錯誤送進 Sentry，一定要手動呼叫 captureException。
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <main className="mx-auto flex max-w-lg flex-col items-start gap-3 p-6">
      <h2 className="text-lg font-semibold">發生非預期錯誤</h2>
      <p className="text-sm text-muted-foreground">
        這個頁面出了問題，已回報給系統。你可以重試，或稍後再回來看看。
      </p>
      <Button type="button" variant="outline" onClick={() => reset()}>
        重試
      </Button>
    </main>
  );
}
