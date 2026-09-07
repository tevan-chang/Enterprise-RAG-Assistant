"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  FileSpreadsheet,
  FileStack,
  FileText,
  Loader2,
  Wand2,
  Lock,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/stat-card";
import { useAuth } from "@/lib/auth-context";
import { useUploadModal } from "@/lib/upload-modal-context";
import {
  PROCESSING_STATUS_LABEL,
  STATUS_BADGE_CLASS,
  deriveDocumentStats,
} from "@/lib/document-status";
import {
  listDocuments,
  reorganizeDocument,
  unlockDocuments,
  type ClassificationStatus,
  type DocumentListItem,
  type ProcessingStatus,
} from "@/lib/api";

const EDITOR_ROLES = new Set(["admin", "editor"]);

type StatusFilter = "all" | "completed" | "processing" | "failed";

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "completed", label: "已完成" },
  { value: "processing", label: "處理中" },
  { value: "failed", label: "失敗" },
];

const PROCESSING_STATUSES = new Set<ProcessingStatus>(["parsing", "chunking", "embedding"]);

function matchesFilter(status: ProcessingStatus, filter: StatusFilter) {
  if (filter === "all") return true;
  if (filter === "processing") return PROCESSING_STATUSES.has(status);
  return status === filter;
}

/** 對應 §1 文件解析僅支援 PDF/XLSX，其餘副檔名一律走 fallback，不特別配色。 */
function FileTypeIcon({ fileName }: { fileName: string }) {
  const ext = fileName.split(".").pop()?.toLowerCase();
  if (ext === "pdf") {
    return (
      <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-red-100 text-red-600">
        <FileText className="size-3.5" />
      </span>
    );
  }
  if (ext === "xlsx") {
    return (
      <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-emerald-100 text-emerald-600">
        <FileSpreadsheet className="size-3.5" />
      </span>
    );
  }
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
      <FileText className="size-3.5" />
    </span>
  );
}

function ClassificationBadge({ status }: { status: ClassificationStatus }) {
  if (status === "manually_verified") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-solid border-foreground/60 px-2 py-0.5 text-xs">
        <Lock className="size-3" />
        人工鎖定
      </span>
    );
  }
  if (status === "auto_labeled") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-dashed border-muted-foreground px-2 py-0.5 text-xs text-muted-foreground">
        <Wand2 className="size-3" />
        AI 自動標籤
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-md border border-dotted border-muted-foreground/50 px-2 py-0.5 text-xs text-muted-foreground">
      尚未分類
    </span>
  );
}

function DocumentRow({ doc }: { doc: DocumentListItem }) {
  const { session, role } = useAuth();
  const accessToken = session!.access_token;
  const queryClient = useQueryClient();
  const [categoriesInput, setCategoriesInput] = useState(doc.final_categories.join(", "));

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["documents"] });

  const reorganizeMutation = useMutation({
    mutationFn: () => {
      const categories = categoriesInput
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      return reorganizeDocument(doc.document_id, categories, accessToken);
    },
    onSuccess: invalidate,
  });

  const unlockMutation = useMutation({
    mutationFn: () => unlockDocuments([doc.document_id], accessToken),
    onSuccess: invalidate,
  });

  const canReorganize = EDITOR_ROLES.has(role ?? "");
  const canUnlock = role === "admin" && doc.classification_status === "manually_verified";

  return (
    <tr className="border-b">
      <td className="p-2 align-top">
        <div className="flex items-center gap-2">
          <FileTypeIcon fileName={doc.file_name} />
          <span className="truncate">{doc.file_name}</span>
        </div>
      </td>
      <td className="p-2 align-top">
        <Badge className={STATUS_BADGE_CLASS[doc.processing_status]}>
          {PROCESSING_STATUS_LABEL[doc.processing_status] ?? doc.processing_status}
        </Badge>
      </td>
      <td className="p-2 align-top">
        <ClassificationBadge status={doc.classification_status} />
      </td>
      <td className="p-2 align-top">
        {canReorganize ? (
          <div className="flex items-center gap-2">
            <Input
              value={categoriesInput}
              onChange={(e) => setCategoriesInput(e.target.value)}
              placeholder="分類（逗號分隔）"
              className="h-7 w-40 text-xs"
            />
            <Button
              size="xs"
              variant="outline"
              onClick={() => reorganizeMutation.mutate()}
              disabled={reorganizeMutation.isPending}
            >
              整理
            </Button>
          </div>
        ) : (
          doc.final_categories.join(", ") || "—"
        )}
      </td>
      <td className="p-2 align-top">
        {canUnlock && (
          <Button
            size="xs"
            variant="ghost"
            onClick={() => unlockMutation.mutate()}
            disabled={unlockMutation.isPending}
          >
            解鎖
          </Button>
        )}
      </td>
    </tr>
  );
}

export default function DocumentsPage() {
  const { session, isLoading } = useAuth();
  const { open: openUploadModal } = useUploadModal();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const documentsQuery = useQuery({
    queryKey: ["documents", session?.user.id],
    queryFn: () => listDocuments(session!.access_token),
    enabled: !!session,
  });

  const documents = documentsQuery.data ?? [];
  const stats = deriveDocumentStats(documents);
  const filteredDocuments = useMemo(
    () => documents.filter((doc) => matchesFilter(doc.processing_status, statusFilter)),
    [documents, statusFilter],
  );

  if (isLoading || !session) {
    return <main className="mx-auto max-w-4xl p-6 text-sm text-muted-foreground">載入中...</main>;
  }

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">文件列表</h1>
        <Button size="sm" onClick={openUploadModal}>
          + 上傳新文件
        </Button>
      </div>

      {documentsQuery.isError && (
        <p className="text-sm text-destructive">載入失敗：{(documentsQuery.error as Error).message}</p>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="總文件數" value={stats.total} icon={FileStack} tone="primary" loading={documentsQuery.isLoading} />
        <StatCard label="已完成" value={stats.completed} icon={CheckCircle2} tone="emerald" loading={documentsQuery.isLoading} />
        <StatCard
          label="處理中"
          value={stats.processing}
          icon={Loader2}
          tone="amber"
          spin={stats.processing > 0}
          loading={documentsQuery.isLoading}
        />
        <StatCard label="失敗" value={stats.failed} icon={XCircle} tone="red" loading={documentsQuery.isLoading} />
      </div>

      {documentsQuery.isLoading && <p className="text-sm text-muted-foreground">載入中...</p>}

      {documentsQuery.data && documentsQuery.data.length === 0 && (
        <p className="text-sm text-muted-foreground">目前租戶尚無文件，先去上傳一份吧。</p>
      )}

      {documentsQuery.data && documentsQuery.data.length > 0 && (
        <>
          <div className="flex gap-2">
            {STATUS_FILTERS.map((filter) => (
              <Button
                key={filter.value}
                size="xs"
                variant={statusFilter === filter.value ? "default" : "outline"}
                onClick={() => setStatusFilter(filter.value)}
              >
                {filter.label}
              </Button>
            ))}
          </div>

          {filteredDocuments.length === 0 ? (
            <p className="text-sm text-muted-foreground">沒有符合篩選條件的文件。</p>
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="p-2 font-medium">檔案名稱</th>
                  <th className="p-2 font-medium">處理狀態</th>
                  <th className="p-2 font-medium">分類狀態</th>
                  <th className="p-2 font-medium">分類</th>
                  <th className="p-2 font-medium">Admin 操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredDocuments.map((doc) => (
                  <DocumentRow key={doc.document_id} doc={doc} />
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </main>
  );
}
