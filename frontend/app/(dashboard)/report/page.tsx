"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/lib/auth-context";
import { generateReport, type ReportToolCall } from "@/lib/api";

type ToolResult = {
  status?: string;
  result?: unknown;
  message?: string;
  error_type?: string;
};

/** 結果欄位依 tool 種類做不同摘要：compute_table_metric 是單一數值，query_documents 是命中列表。 */
function formatToolResult(toolCall: ReportToolCall): string {
  const result = toolCall.result as ToolResult;
  if (result.status === "error") {
    return `⚠️ ${result.error_type ?? "錯誤"}：${result.message ?? "執行失敗"}`;
  }
  if (toolCall.tool === "compute_table_metric") {
    return String(result.result);
  }
  if (Array.isArray(result.result)) {
    return result.result
      .map((hit) =>
        typeof hit === "object" && hit !== null && "label" in hit
          ? String((hit as { label: unknown }).label)
          : JSON.stringify(hit),
      )
      .join("、");
  }
  return JSON.stringify(result.result);
}

function formatToolArguments(toolCall: ReportToolCall): string {
  try {
    const parsed = JSON.parse(toolCall.arguments) as Record<string, unknown>;
    return Object.entries(parsed)
      .map(([key, value]) => `${key}=${value}`)
      .join("，");
  } catch {
    return toolCall.arguments;
  }
}

export default function ReportPage() {
  const { session, isLoading } = useAuth();
  const [query, setQuery] = useState("");

  const reportMutation = useMutation({
    mutationFn: (q: string) => generateReport(q, session!.access_token),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || reportMutation.isPending) return;
    reportMutation.mutate(trimmed);
  }

  if (isLoading || !session) {
    return <main className="mx-auto max-w-3xl p-6 text-sm text-muted-foreground">載入中...</main>;
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
      <div>
        <h1 className="text-xl font-semibold">報告生成 Report Mode</h1>
        <p className="text-sm text-muted-foreground">
          會先呼叫工具做檢索/表格數值運算才產出報告（1-2 輪），回應時間比知識問答 Chat 長，請耐心等候。
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="例如：本季業績加總是多少？"
          disabled={reportMutation.isPending}
        />
        <Button type="submit" disabled={reportMutation.isPending || !query.trim()}>
          產生報告
        </Button>
      </form>

      {reportMutation.isPending && (
        <div className="flex items-center gap-2 rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          報告產生中，正在呼叫工具檢索/運算，請稍候...
        </div>
      )}

      {reportMutation.isError && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          產生報告失敗：{(reportMutation.error as Error).message}
        </p>
      )}

      {reportMutation.isSuccess && (
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>報告內容</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm">
                {reportMutation.data.content || "（模型沒有回傳文字內容）"}
              </p>
            </CardContent>
          </Card>

          {reportMutation.data.tool_calls.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Tool-Calling 過程</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>工具</TableHead>
                      <TableHead>參數</TableHead>
                      <TableHead>結果</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reportMutation.data.tool_calls.map((toolCall, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-mono text-xs">{toolCall.tool}</TableCell>
                        <TableCell className="font-mono text-xs whitespace-pre-wrap">
                          {formatToolArguments(toolCall)}
                        </TableCell>
                        <TableCell className="text-xs whitespace-pre-wrap">{formatToolResult(toolCall)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </main>
  );
}
