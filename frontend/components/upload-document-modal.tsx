"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuth } from "@/lib/auth-context";
import { useUploadModal } from "@/lib/upload-modal-context";
import { getDocumentStatus, uploadDocument, type ProcessingStatus } from "@/lib/api";

const TERMINAL_STATUSES = new Set<ProcessingStatus>(["completed", "failed"]);

const STATUS_LABEL: Record<ProcessingStatus, string> = {
  parsing: "解析中",
  chunking: "切分段落中",
  embedding: "產生向量中",
  completed: "已完成",
  failed: "失敗",
};

export function UploadDocumentModal() {
  const { isOpen, close } = useUploadModal();
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("請先選擇檔案");
      return uploadDocument(file, session!.access_token);
    },
    onSuccess: (data) => {
      setDocumentId(data.document_id);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const statusQuery = useQuery({
    queryKey: ["document-status", documentId, session?.user.id],
    queryFn: () => getDocumentStatus(documentId as string, session!.access_token),
    enabled: documentId !== null && !!session,
    refetchInterval: (query) => {
      const status = query.state.data?.processing_status;
      if (status && TERMINAL_STATUSES.has(status)) {
        queryClient.invalidateQueries({ queryKey: ["documents"] });
        return false;
      }
      return 2000;
    },
  });

  const status = statusQuery.data?.processing_status;

  function resetState() {
    setFile(null);
    setDocumentId(null);
    uploadMutation.reset();
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      close();
      resetState();
    }
  }

  if (!session) {
    return null;
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>上傳文件</DialogTitle>
          <DialogDescription>支援 PDF / XLSX，上傳後會自動進入解析與向量化流程。</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
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
              <span className="truncate">文件 ID：{documentId}</span>
              <Badge variant={status === "failed" ? "destructive" : "secondary"}>
                {status ? STATUS_LABEL[status] : "查詢中"}
              </Badge>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            onClick={() => uploadMutation.mutate()}
            disabled={!file || uploadMutation.isPending}
          >
            {uploadMutation.isPending ? "上傳中..." : "上傳"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
