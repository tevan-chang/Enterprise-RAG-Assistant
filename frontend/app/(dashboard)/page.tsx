"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, FileStack, Loader2, MessageSquare, FileText, Upload, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/stat-card";
import { useAuth } from "@/lib/auth-context";
import { PROCESSING_STATUS_LABEL, STATUS_BADGE_CLASS, deriveDocumentStats } from "@/lib/document-status";
import { listDocuments } from "@/lib/api";

const QUICK_LINKS = [
  {
    href: "/chat",
    label: "知識問答",
    description: "向已上傳的文件提問，取得含來源標註的回答",
    icon: MessageSquare,
  },
  {
    href: "/documents",
    label: "文件列表",
    description: "檢視處理進度、分類狀態，並可整理／解鎖分類",
    icon: FileText,
  },
  {
    href: "/documents/upload",
    label: "上傳文件",
    description: "上傳 PDF 或 XLSX，進入解析與向量化流程",
    icon: Upload,
  },
];

export default function Home() {
  const { session, isLoading } = useAuth();

  const documentsQuery = useQuery({
    queryKey: ["documents", session?.user.id],
    queryFn: () => listDocuments(session!.access_token),
    enabled: !!session,
  });

  if (isLoading || !session) {
    return <main className="p-6 text-sm text-muted-foreground">載入中...</main>;
  }

  const documents = documentsQuery.data ?? [];
  const stats = deriveDocumentStats(documents);
  const recentDocuments = [...documents]
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    .slice(0, 5);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">工作區總覽</h1>
        <p className="text-sm text-muted-foreground">目前租戶的知識庫文件狀態與功能入口</p>
      </div>

      {documentsQuery.isError && (
        <p className="text-sm text-destructive">
          文件資料載入失敗：{(documentsQuery.error as Error).message}
        </p>
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

      <div className="grid gap-4 md:grid-cols-3">
        {QUICK_LINKS.map(({ href, label, description, icon: Icon }) => (
          <Link key={href} href={href}>
            <Card className="h-full transition-colors hover:border-primary/50 hover:bg-accent/40">
              <CardContent className="flex flex-col gap-2">
                <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="size-4" />
                </span>
                <p className="font-medium">{label}</p>
                <p className="text-xs text-muted-foreground">{description}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">最近更新文件</CardTitle>
          <CardAction>
            <Link href="/documents" className="text-xs text-primary hover:underline">
              查看全部
            </Link>
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {documentsQuery.isLoading && <p className="text-sm text-muted-foreground">載入中...</p>}
          {!documentsQuery.isLoading && recentDocuments.length === 0 && (
            <p className="text-sm text-muted-foreground">目前租戶尚無文件，先去上傳一份吧。</p>
          )}
          {recentDocuments.map((doc) => (
            <div
              key={doc.document_id}
              className="flex items-center justify-between gap-3 border-b pb-3 last:border-b-0 last:pb-0"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{doc.file_name}</p>
                <p className="text-xs text-muted-foreground">
                  {new Date(doc.updated_at).toLocaleString("zh-TW")}
                </p>
              </div>
              <Badge className={STATUS_BADGE_CLASS[doc.processing_status]}>
                {PROCESSING_STATUS_LABEL[doc.processing_status] ?? doc.processing_status}
              </Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </main>
  );
}
