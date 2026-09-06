import type { DocumentListItem, ProcessingStatus } from "@/lib/api";

export const PROCESSING_STATUS_LABEL: Record<ProcessingStatus, string> = {
  parsing: "解析中",
  chunking: "切分段落中",
  embedding: "產生向量中",
  completed: "已完成",
  failed: "失敗",
};

/** 對應規格書 §4.2／計畫書 §3.0 的狀態色慣例：完成=emerald、處理中=amber、失敗=red。 */
export const STATUS_BADGE_CLASS: Record<ProcessingStatus, string> = {
  completed: "bg-emerald-100 text-emerald-700",
  parsing: "bg-amber-100 text-amber-700",
  chunking: "bg-amber-100 text-amber-700",
  embedding: "bg-amber-100 text-amber-700",
  failed: "bg-red-100 text-red-700",
};

export const PROCESSING_IN_PROGRESS_STATUSES = new Set<ProcessingStatus>([
  "parsing",
  "chunking",
  "embedding",
]);

export type DocumentStats = {
  total: number;
  completed: number;
  processing: number;
  failed: number;
};

export function deriveDocumentStats(documents: DocumentListItem[]): DocumentStats {
  return {
    total: documents.length,
    completed: documents.filter((d) => d.processing_status === "completed").length,
    processing: documents.filter((d) => PROCESSING_IN_PROGRESS_STATUSES.has(d.processing_status)).length,
    failed: documents.filter((d) => d.processing_status === "failed").length,
  };
}
