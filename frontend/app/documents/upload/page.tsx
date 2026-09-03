"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { IdentitySwitcher } from "@/components/identity-switcher";
import { useDevIdentity } from "@/lib/dev-identity";
import { getDocumentStatus, uploadDocument, type ProcessingStatus } from "@/lib/api";

const TERMINAL_STATUSES = new Set<ProcessingStatus>(["completed", "failed"]);

const STATUS_LABEL: Record<ProcessingStatus, string> = {
  parsing: "解析中",
  chunking: "切分段落中",
  embedding: "產生向量中",
  completed: "已完成",
  failed: "失敗",
};

export default function UploadPage() {
  const identity = useDevIdentity();
  const [file, setFile] = useState<File | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("請先選擇檔案");
      return uploadDocument(file, identity);
    },
    onSuccess: (data) => setDocumentId(data.document_id),
  });

  const statusQuery = useQuery({
    queryKey: ["document-status", documentId, identity.tenantId, identity.role],
    queryFn: () => getDocumentStatus(documentId as string, identity),
    enabled: documentId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.processing_status;
      return status && TERMINAL_STATUSES.has(status) ? false : 2000;
    },
  });

  const status = statusQuery.data?.processing_status;

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">上傳文件</h1>
        <IdentitySwitcher />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>PDF / XLSX 上傳</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Input
            type="file"
            accept=".pdf,.xlsx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            disabled={uploadMutation.isPending}
          />

          {uploadMutation.isError && (
            <p className="text-sm text-destructive">
              上傳失敗：{(uploadMutation.error as Error).message}
            </p>
          )}

          {documentId && (
            <div className="flex items-center gap-2 rounded-md border p-3 text-sm">
              {status === "completed" && <CheckCircle2 className="size-4 text-green-600" />}
              {status === "failed" && <XCircle className="size-4 text-destructive" />}
              {status && !TERMINAL_STATUSES.has(status) && (
                <Loader2 className="size-4 animate-spin text-muted-foreground" />
              )}
              <span>文件 ID：{documentId}</span>
              <Badge variant={status === "failed" ? "destructive" : "secondary"}>
                {status ? STATUS_LABEL[status] : "查詢中"}
              </Badge>
            </div>
          )}
        </CardContent>
        <CardFooter className="flex items-center justify-between">
          <Button
            onClick={() => uploadMutation.mutate()}
            disabled={!file || uploadMutation.isPending}
          >
            {uploadMutation.isPending ? "上傳中..." : "上傳"}
          </Button>
          <Link href="/documents" className="text-sm text-primary underline-offset-4 hover:underline">
            查看文件列表 →
          </Link>
        </CardFooter>
      </Card>
    </main>
  );
}
