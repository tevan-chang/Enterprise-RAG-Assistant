"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Wand2, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { IdentitySwitcher } from "@/components/identity-switcher";
import { useDevIdentity } from "@/lib/dev-identity";
import {
  listDocuments,
  reorganizeDocument,
  unlockDocuments,
  type ClassificationStatus,
  type DocumentListItem,
} from "@/lib/api";

const EDITOR_ROLES = new Set(["admin", "editor"]);

const PROCESSING_STATUS_LABEL: Record<string, string> = {
  parsing: "解析中",
  chunking: "切分段落中",
  embedding: "產生向量中",
  completed: "已完成",
  failed: "失敗",
};

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
  const identity = useDevIdentity();
  const queryClient = useQueryClient();
  const [categoriesInput, setCategoriesInput] = useState(doc.final_categories.join(", "));

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["documents"] });

  const reorganizeMutation = useMutation({
    mutationFn: () => {
      const categories = categoriesInput
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      return reorganizeDocument(doc.document_id, categories, identity);
    },
    onSuccess: invalidate,
  });

  const unlockMutation = useMutation({
    mutationFn: () => unlockDocuments([doc.document_id], identity),
    onSuccess: invalidate,
  });

  const canReorganize = EDITOR_ROLES.has(identity.role);
  const canUnlock = identity.role === "admin" && doc.classification_status === "manually_verified";

  return (
    <tr className="border-b">
      <td className="p-2 align-top">{doc.file_name}</td>
      <td className="p-2 align-top">
        <Badge variant={doc.processing_status === "failed" ? "destructive" : "secondary"}>
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
  const identity = useDevIdentity();

  const documentsQuery = useQuery({
    queryKey: ["documents", identity.tenantId, identity.role],
    queryFn: () => listDocuments(identity),
  });

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">文件列表</h1>
        <IdentitySwitcher />
      </div>

      <Link href="/documents/upload" className="text-sm text-primary underline-offset-4 hover:underline">
        + 上傳新文件
      </Link>

      {documentsQuery.isLoading && <p className="text-sm text-muted-foreground">載入中...</p>}
      {documentsQuery.isError && (
        <p className="text-sm text-destructive">載入失敗：{(documentsQuery.error as Error).message}</p>
      )}

      {documentsQuery.data && documentsQuery.data.length === 0 && (
        <p className="text-sm text-muted-foreground">目前租戶尚無文件，先去上傳一份吧。</p>
      )}

      {documentsQuery.data && documentsQuery.data.length > 0 && (
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
            {documentsQuery.data.map((doc) => (
              <DocumentRow key={doc.document_id} doc={doc} />
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
