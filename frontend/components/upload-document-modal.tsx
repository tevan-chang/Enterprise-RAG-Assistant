"use client";

import { useRef, useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/lib/auth-context";
import { useUploadModal } from "@/lib/upload-modal-context";
import { CONFIDENTIALITY_LABEL, isDocumentFullyResolved } from "@/lib/document-status";
import {
  ApiError,
  getDocumentStatus,
  reuploadDocument,
  uploadDocument,
  type Confidentiality,
  type ProcessingStatus,
} from "@/lib/api";

type FilenameConflict = { documentId: string; fileName: string };

function asFilenameConflict(error: unknown): FilenameConflict | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const detail = (error.body as { detail?: Record<string, unknown> } | undefined)?.detail;
  if (detail?.reason !== "filename_exists") return null;
  return { documentId: String(detail.document_id), fileName: String(detail.file_name) };
}

/** 只取後端回傳的人類可讀訊息，不把 document_id 等結構化欄位或原始 JSON 顯示給使用者。 */
function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") {
      return (detail as { message: string }).message;
    }
  }
  return error instanceof Error ? error.message : "發生未知錯誤";
}

const STATUS_LABEL: Record<ProcessingStatus, string> = {
  parsing: "解析中",
  chunking: "切分段落中",
  embedding: "產生向量中",
  completed: "已完成",
  failed: "失敗",
};

/** auto_classify() 失敗時刻意把 classification_status 永遠留在 pending_auto、不重試
 * （見 backend/app/services/classification.py docstring），所以等分類收斂不能無限等待——
 * 超過這個 tick 數（2 秒一次，20 秒）就放棄等待，直接視為完成，避免分類永久失敗時
 * modal 卡住無限輪詢。分類本身只是一次 LLM 呼叫，正常應在數秒內完成，20 秒已足夠寬裕。 */
const CLASSIFICATION_MAX_WAIT_TICKS = 10;

export function UploadDocumentModal() {
  const { isOpen, close } = useUploadModal();
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [confidentiality, setConfidentiality] = useState<Confidentiality>("internal");
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [conflict, setConflict] = useState<FilenameConflict | null>(null);
  const [classificationTimedOut, setClassificationTimedOut] = useState(false);
  const classificationWaitTicksRef = useRef(0);

  const uploadMutation = useMutation({
    mutationFn: (options?: { force?: boolean }) => {
      if (!file) throw new Error("請先選擇檔案");
      return uploadDocument(file, session!.access_token, { ...options, confidentiality });
    },
    onSuccess: (data) => {
      setConflict(null);
      setDocumentId(data.document_id);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (error) => {
      setConflict(asFilenameConflict(error));
    },
  });

  const reuploadMutation = useMutation({
    mutationFn: () => {
      if (!file || !conflict) throw new Error("請先選擇檔案");
      return reuploadDocument(conflict.documentId, file, session!.access_token);
    },
    onSuccess: (data) => {
      setConflict(null);
      uploadMutation.reset();
      setDocumentId(data.document_id);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const statusQuery = useQuery({
    queryKey: ["document-status", documentId, session?.user.id],
    queryFn: () => getDocumentStatus(documentId as string, session!.access_token),
    enabled: documentId !== null && !!session,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && isDocumentFullyResolved(data)) {
        queryClient.invalidateQueries({ queryKey: ["documents"] });
        return false;
      }
      if (data?.processing_status === "completed" && data.classification_status === "pending_auto") {
        classificationWaitTicksRef.current += 1;
        if (classificationWaitTicksRef.current >= CLASSIFICATION_MAX_WAIT_TICKS) {
          setClassificationTimedOut(true);
          queryClient.invalidateQueries({ queryKey: ["documents"] });
          return false;
        }
      }
      return 2000;
    },
  });

  const status = statusQuery.data?.processing_status;
  const classificationStatus = statusQuery.data?.classification_status;
  const isResolved = (statusQuery.data && isDocumentFullyResolved(statusQuery.data)) || classificationTimedOut;
  const isClassifying = status === "completed" && classificationStatus === "pending_auto" && !classificationTimedOut;

  function resetState() {
    setFile(null);
    setConfidentiality("internal");
    setDocumentId(null);
    setConflict(null);
    setClassificationTimedOut(false);
    classificationWaitTicksRef.current = 0;
    uploadMutation.reset();
    reuploadMutation.reset();
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
            disabled={uploadMutation.isPending || !!documentId}
          />

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">機密等級</span>
            <Select
              value={confidentiality}
              onValueChange={(value) => setConfidentiality(value as Confidentiality)}
              disabled={uploadMutation.isPending || !!documentId}
            >
              <SelectTrigger size="sm" className="w-full text-xs">
                <SelectValue placeholder="機密等級" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="public">{CONFIDENTIALITY_LABEL.public}</SelectItem>
                <SelectItem value="internal">{CONFIDENTIALITY_LABEL.internal}</SelectItem>
                <SelectItem value="restricted">{CONFIDENTIALITY_LABEL.restricted}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {uploadMutation.isError && !conflict && (
            <p className="text-sm text-destructive">
              上傳失敗：{getErrorMessage(uploadMutation.error)}
            </p>
          )}

          {conflict && (
            <div className="flex flex-col gap-2 rounded-md border border-destructive/50 p-3 text-sm">
              <p>
                已有相同檔名的文件《{conflict.fileName}》，請選擇覆蓋既有文件，或修改檔名後仍要新建。
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => reuploadMutation.mutate()}
                  disabled={reuploadMutation.isPending}
                >
                  {reuploadMutation.isPending ? "覆蓋中..." : "覆蓋既有文件"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => uploadMutation.mutate({ force: true })}
                  disabled={uploadMutation.isPending}
                >
                  仍要新建
                </Button>
              </div>
              {reuploadMutation.isError && (
                <p className="text-destructive">
                  覆蓋失敗：{getErrorMessage(reuploadMutation.error)}
                </p>
              )}
            </div>
          )}

          {documentId && (
            <div className="flex items-center gap-2 rounded-md border p-3 text-sm">
              {status === "failed" && <XCircle className="size-4 text-destructive" />}
              {status === "completed" && isResolved && <CheckCircle2 className="size-4 text-green-600" />}
              {status !== "failed" && !isResolved && (
                <Loader2 className="size-4 animate-spin text-muted-foreground" />
              )}
              <span className="truncate">文件 ID：{documentId}</span>
              <Badge variant={status === "failed" ? "destructive" : "secondary"}>
                {isClassifying ? "分類中" : status ? STATUS_LABEL[status] : "查詢中"}
              </Badge>
            </div>
          )}
        </div>

        {!conflict && (
          <DialogFooter>
            <Button
              onClick={() => uploadMutation.mutate(undefined)}
              disabled={!file || uploadMutation.isPending}
            >
              {uploadMutation.isPending ? "上傳中..." : "上傳"}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
