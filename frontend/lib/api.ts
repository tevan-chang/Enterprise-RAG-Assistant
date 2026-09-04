import type { UserRole } from "@/lib/dev-identity";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ProcessingStatus = "parsing" | "chunking" | "embedding" | "completed" | "failed";
export type ClassificationStatus = "pending_auto" | "auto_labeled" | "manually_verified";

export type DocumentUploadResponse = {
  document_id: string;
  processing_status: ProcessingStatus;
};

export type DocumentStatusResponse = {
  document_id: string;
  processing_status: ProcessingStatus;
  file_name: string;
  updated_at: string;
};

export type DocumentListItem = {
  document_id: string;
  file_name: string;
  processing_status: ProcessingStatus;
  classification_status: ClassificationStatus;
  final_categories: string[];
  confidentiality: string;
  updated_at: string;
};

/** Chat SSE `citations` 事件裡的單筆結構（見 backend/app/services/chat.py `_build_citations`）。
 * `label` 與訊息文字中的 `[來源：...]` 標籤完全一致，前端靠這個欄位比對訊息裡出現的標籤。
 */
export type ChatCitation = {
  label: string;
  document_id: string;
  file_name: string;
  page_number: number | null;
  sheet_name: string | null;
  cell_range: string | null;
};

export type CitationDetailResponse = {
  document_id: string;
  file_name: string;
  page_number: number | null;
  sheet_name: string | null;
  cell_range: string | null;
  content: string;
};

export type Identity = { tenantId: string; role: UserRole };

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, identity: Identity, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "X-Tenant-Id": identity.tenantId,
      "X-User-Role": identity.role,
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export function uploadDocument(file: File, identity: Identity): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return request<DocumentUploadResponse>("/api/documents/upload", identity, {
    method: "POST",
    body: formData,
  });
}

export function getDocumentStatus(documentId: string, identity: Identity): Promise<DocumentStatusResponse> {
  return request<DocumentStatusResponse>(`/api/documents/${documentId}/status`, identity);
}

export function listDocuments(identity: Identity): Promise<DocumentListItem[]> {
  return request<DocumentListItem[]>("/api/documents", identity);
}

export function reorganizeDocument(
  documentId: string,
  manualCategories: string[],
  identity: Identity,
): Promise<void> {
  return request("/api/documents/reorganize", identity, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, manual_categories: manualCategories }),
  });
}

/** Citation 跳轉 API（見 roadmap Day 7）：依 citation 的 page_number 或 sheet_name+cell_range 定位。 */
export function getCitationDetail(
  citation: Pick<ChatCitation, "document_id" | "page_number" | "sheet_name" | "cell_range">,
  identity: Identity,
): Promise<CitationDetailResponse> {
  const params = new URLSearchParams();
  if (citation.page_number != null) {
    params.set("page_number", String(citation.page_number));
  }
  if (citation.sheet_name != null && citation.cell_range != null) {
    params.set("sheet_name", citation.sheet_name);
    params.set("cell_range", citation.cell_range);
  }
  return request<CitationDetailResponse>(
    `/api/documents/${citation.document_id}/citation?${params.toString()}`,
    identity,
  );
}

export function unlockDocuments(documentIds: string[], identity: Identity): Promise<void> {
  return request("/api/documents/unlock", identity, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_ids: documentIds }),
  });
}

/**
 * Chat SSE 串流（見 roadmap Day 6）：原生 `EventSource` 不支援自訂 header 帶身分資訊，
 * 改用 `fetch` 回傳原始 Response，呼叫端自行用 `ReadableStream` 逐段讀取 body。
 */
export async function streamChatQuery(
  query: string,
  identity: Identity,
  signal?: AbortSignal,
): Promise<ReadableStream<Uint8Array>> {
  const res = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Id": identity.tenantId,
      "X-User-Role": identity.role,
    },
    body: JSON.stringify({ query }),
    signal,
  });

  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => "");
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.body;
}
