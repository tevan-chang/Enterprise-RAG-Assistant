"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  FileSpreadsheet,
  FileStack,
  FileText,
  Loader2,
  Trash2,
  Wand2,
  Lock,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  AlertDialog,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { StatCard } from "@/components/stat-card";
import { useAuth } from "@/lib/auth-context";
import { useUploadModal } from "@/lib/upload-modal-context";
import {
  PROCESSING_STATUS_LABEL,
  STATUS_BADGE_CLASS,
  deriveDocumentStats,
} from "@/lib/document-status";
import {
  deleteDocument,
  listDocuments,
  reorganizeDocument,
  unlockDocuments,
  type ClassificationStatus,
  type Confidentiality,
  type DocumentListItem,
  type ProcessingStatus,
} from "@/lib/api";

const EDITOR_ROLES = new Set(["admin", "editor"]);

const CONFIDENTIALITY_LABEL: Record<string, string> = {
  public: "公開",
  internal: "內部",
  restricted: "機密",
};

const CONFIDENTIALITY_BADGE_CLASS: Record<string, string> = {
  public: "bg-emerald-100 text-emerald-700",
  internal: "bg-muted text-muted-foreground",
  restricted: "bg-red-100 text-red-700",
};

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

function ConfidentialityBadge({ confidentiality }: { confidentiality: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs ${CONFIDENTIALITY_BADGE_CLASS[confidentiality] ?? "bg-muted text-muted-foreground"}`}
    >
      {CONFIDENTIALITY_LABEL[confidentiality] ?? confidentiality}
    </span>
  );
}

function DocumentRow({ doc }: { doc: DocumentListItem }) {
  const { session, role } = useAuth();
  const accessToken = session!.access_token;
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [categoriesInput, setCategoriesInput] = useState(doc.final_categories.join(", "));
  const [departmentsInput, setDepartmentsInput] = useState(doc.departments.join(", "));
  const [confidentiality, setConfidentiality] = useState<Confidentiality>(
    (doc.confidentiality as Confidentiality) ?? "internal",
  );
  const [categoriesError, setCategoriesError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["documents"] });

  const resetDraft = () => {
    setCategoriesInput(doc.final_categories.join(", "));
    setDepartmentsInput(doc.departments.join(", "));
    setConfidentiality((doc.confidentiality as Confidentiality) ?? "internal");
    setCategoriesError(null);
  };

  const reorganizeMutation = useMutation({
    mutationFn: () => {
      const categories = categoriesInput
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      const departments = departmentsInput
        .split(",")
        .map((d) => d.trim())
        .filter(Boolean);
      return reorganizeDocument(doc.document_id, categories, accessToken, {
        departments,
        confidentiality,
      });
    },
    onSuccess: () => {
      invalidate();
      setOpen(false);
    },
  });

  const handleReorganize = () => {
    const hasCategory = categoriesInput.split(",").some((c) => c.trim().length > 0);
    if (!hasCategory) {
      setCategoriesError("請先輸入至少一個分類標籤，才能整理此文件");
      return;
    }
    setCategoriesError(null);
    reorganizeMutation.mutate();
  };

  const handleCancel = () => {
    resetDraft();
    setOpen(false);
  };

  const categorySummary = [...doc.final_categories, ...doc.departments].join(" / ");

  const unlockMutation = useMutation({
    mutationFn: () => unlockDocuments([doc.document_id], accessToken),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteDocument(doc.document_id, accessToken),
    onSuccess: invalidate,
  });

  const canReorganize = EDITOR_ROLES.has(role ?? "");
  const canUnlock = role === "admin" && doc.classification_status === "manually_verified";
  const canDelete = EDITOR_ROLES.has(role ?? "");

  return (
    <TableRow>
      <TableCell className="whitespace-normal py-3 align-top">
        <div className="flex items-center gap-2">
          <FileTypeIcon fileName={doc.file_name} />
          <span className="truncate">{doc.file_name}</span>
        </div>
      </TableCell>
      <TableCell className="py-3 align-top">
        <Badge className={STATUS_BADGE_CLASS[doc.processing_status]}>
          {PROCESSING_STATUS_LABEL[doc.processing_status] ?? doc.processing_status}
        </Badge>
      </TableCell>
      <TableCell className="whitespace-normal py-3 align-top">
        <div className="flex flex-col items-start gap-1">
          <ClassificationBadge status={doc.classification_status} />
          <ConfidentialityBadge confidentiality={doc.confidentiality} />
        </div>
      </TableCell>
      <TableCell className="whitespace-normal py-3 align-top">
        {canReorganize ? (
          <Popover
            open={open}
            onOpenChange={(next) => {
              if (next) resetDraft();
              setOpen(next);
            }}
          >
            <PopoverTrigger
              render={
                <Button
                  variant="outline"
                  size="xs"
                  className="max-w-full justify-between gap-1"
                  title={categorySummary || undefined}
                >
                  <span className="truncate">{categorySummary || "尚未設定，點擊分類"}</span>
                  <ChevronDown className="size-3 shrink-0" />
                </Button>
              }
            />
            <PopoverContent>
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium text-muted-foreground">標籤</span>
                  <Input
                    value={categoriesInput}
                    onChange={(e) => {
                      setCategoriesInput(e.target.value);
                      if (categoriesError) setCategoriesError(null);
                    }}
                    placeholder="分類（逗號分隔）"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium text-muted-foreground">部門</span>
                  <Input
                    value={departmentsInput}
                    onChange={(e) => setDepartmentsInput(e.target.value)}
                    placeholder="部門（逗號分隔）"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium text-muted-foreground">權限</span>
                  <Select
                    value={confidentiality}
                    onValueChange={(value) => setConfidentiality(value as Confidentiality)}
                  >
                    <SelectTrigger size="sm" className="w-full text-xs">
                      <SelectValue placeholder="機密等級" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="public">公開</SelectItem>
                      <SelectItem value="internal">內部</SelectItem>
                      <SelectItem value="restricted">機密</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {categoriesError && (
                  <span className="text-xs text-red-600">{categoriesError}</span>
                )}
                <div className="flex justify-end gap-2 pt-1">
                  <Button size="xs" variant="outline" onClick={handleCancel}>
                    取消
                  </Button>
                  <Button
                    size="xs"
                    onClick={handleReorganize}
                    disabled={reorganizeMutation.isPending}
                  >
                    儲存並整理
                  </Button>
                </div>
              </div>
            </PopoverContent>
          </Popover>
        ) : (
          doc.final_categories.join(", ") || "—"
        )}
      </TableCell>
      <TableCell className="py-3 align-top">
        <div className="flex items-center gap-2">
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
          {canDelete && (
            <AlertDialog>
              <AlertDialogTrigger
                render={
                  <Button size="icon-xs" variant="ghost" disabled={deleteMutation.isPending}>
                    <Trash2 className="text-destructive" />
                    <span className="sr-only">刪除</span>
                  </Button>
                }
              />
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>確定要刪除《{doc.file_name}》嗎？</AlertDialogTitle>
                  <AlertDialogDescription>
                    此操作無法復原，將一併清除已解析的內容與向量資料。
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogClose render={<Button variant="outline" size="xs" />}>
                    取消
                  </AlertDialogClose>
                  <AlertDialogClose
                    render={
                      <Button
                        variant="destructive"
                        size="xs"
                        onClick={() => deleteMutation.mutate()}
                      />
                    }
                  >
                    確定刪除
                  </AlertDialogClose>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </TableCell>
    </TableRow>
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
    return <main className="mx-auto max-w-6xl p-6 text-sm text-muted-foreground">載入中...</main>;
  }

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 p-6">
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
            <Table>
              <colgroup>
                <col style={{ width: "26%" }} />
                <col style={{ width: "12%" }} />
                <col style={{ width: "20%" }} />
                <col style={{ width: "22%" }} />
                <col style={{ width: "20%" }} />
              </colgroup>
              <TableHeader>
                <TableRow>
                  <TableHead>檔案名稱</TableHead>
                  <TableHead>處理狀態</TableHead>
                  <TableHead>分類狀態</TableHead>
                  <TableHead>分類</TableHead>
                  <TableHead>Admin 操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredDocuments.map((doc) => (
                  <DocumentRow key={doc.document_id} doc={doc} />
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </main>
  );
}
