"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/lib/auth-context";
import { generateReport, type ReportToolCall } from "@/lib/api";

type ToolResult = {
  status?: string;
  result?: unknown;
  message?: string;
  error_type?: string;
};

type DocumentHit = { label?: unknown; content?: unknown };

type MetricGroup = { group: string; value: number; share: number };

type GroupedMetricPayload = {
  groups: MetricGroup[];
  filter: { column: string; value: string } | null;
};

/** compute_table_metric 帶 group_by_column 時，result 是 { groups, filter } 結構而非單一數值。 */
function isGroupedMetricPayload(value: unknown): value is GroupedMetricPayload {
  return typeof value === "object" && value !== null && Array.isArray((value as { groups?: unknown }).groups);
}

function hitLabel(hit: unknown, fallbackIndex: number): string {
  if (typeof hit === "object" && hit !== null && "label" in hit) {
    return String((hit as DocumentHit).label);
  }
  return `結果 ${fallbackIndex + 1}`;
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

/** tool call 執行狀態徽章：取代舊版把 ⚠️ 塞進結果字串前綴的做法，比照 documents 頁的狀態 Badge 慣例。 */
function ToolStatusBadge({ toolCall }: { toolCall: ReportToolCall }) {
  const result = toolCall.result as ToolResult;
  if (result.status === "error") {
    return <Badge variant="destructive">失敗</Badge>;
  }
  return <Badge className="bg-emerald-100 text-emerald-700">成功</Badge>;
}

/** 結果欄位依 tool 種類與資料形狀分流渲染，取代舊版一律壓成單行字串（對物件呼叫 String() 會印出
 * "[object Object]"，新增 group_by_column 分組結果後必須改成結構化渲染）。
 */
function ToolResultCell({ toolCall }: { toolCall: ReportToolCall }) {
  const result = toolCall.result as ToolResult;

  if (result.status === "error") {
    return (
      <span className="text-xs text-destructive" title={result.error_type}>
        {result.message ?? "執行失敗"}
      </span>
    );
  }

  if (toolCall.tool === "compute_table_metric") {
    if (isGroupedMetricPayload(result.result)) {
      const { groups, filter } = result.result;
      return (
        <div className="flex flex-col gap-1">
          {filter && (
            <div className="text-xs text-muted-foreground">
              篩選條件：{filter.column} = {filter.value}
            </div>
          )}
          <div className="flex flex-col gap-0.5">
            {groups.map(({ group, value, share }) => (
              <div key={group} className="text-xs">
                {group}：{value.toLocaleString()}（{(share * 100).toFixed(1)}%）
              </div>
            ))}
          </div>
        </div>
      );
    }
    return <span className="text-xs">{Number(result.result).toLocaleString()}</span>;
  }

  if (Array.isArray(result.result)) {
    const hits = result.result as DocumentHit[];
    if (hits.length === 0) {
      return <span className="text-xs text-muted-foreground">（無命中）</span>;
    }
    return (
      <Popover>
        <PopoverTrigger
          render={
            <Button variant="ghost" size="xs" className="h-auto whitespace-normal text-left font-mono">
              {hits.map((hit, i) => hitLabel(hit, i)).join("、")}
            </Button>
          }
        />
        <PopoverContent className="w-96">
          <div className="flex max-h-80 flex-col gap-3 overflow-y-auto">
            {hits.map((hit, i) => (
              <div key={i} className="text-xs">
                <p className="font-medium">{hitLabel(hit, i)}</p>
                <p className="whitespace-pre-wrap text-muted-foreground">
                  {"content" in hit ? String(hit.content) : JSON.stringify(hit)}
                </p>
              </div>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    );
  }

  return <span className="text-xs">{JSON.stringify(result.result)}</span>;
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
                      <TableHead>狀態</TableHead>
                      <TableHead>參數</TableHead>
                      <TableHead>結果</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reportMutation.data.tool_calls.map((toolCall, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-mono text-xs">{toolCall.tool}</TableCell>
                        <TableCell>
                          <ToolStatusBadge toolCall={toolCall} />
                        </TableCell>
                        <TableCell className="font-mono text-xs whitespace-pre-wrap">
                          {formatToolArguments(toolCall)}
                        </TableCell>
                        <TableCell className="text-xs whitespace-pre-wrap">
                          <ToolResultCell toolCall={toolCall} />
                        </TableCell>
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
