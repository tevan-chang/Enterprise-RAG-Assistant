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

/** Report Mode tool-calling 結果（見 backend/app/schemas/reports.py，roadmap Day 8-9）。 */
export type ReportToolCall = {
  tool: string;
  arguments: string;
  result: Record<string, unknown>;
};

export type ReportGenerateResponse = {
  content: string;
  tool_calls: ReportToolCall[];
};

export class ApiError extends Error {
  /** 後端結構化錯誤（例如 409 detail 為 dict）時，解析後的 JSON 內容；純文字錯誤則為 undefined。 */
  public body: unknown;

  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    try {
      this.body = JSON.parse(message);
    } catch {
      this.body = undefined;
    }
  }
}

/** 401 全域登出機制：`api.ts` 不能直接 import React context，改由 `AuthProvider`
 * 註冊這個模組層級 handler；`unauthorizedTriggered` 避免同時炸開的多個 401 重複導頁。 */
type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;
let unauthorizedTriggered = false;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler;
}

export function resetUnauthorizedTrigger() {
  unauthorizedTriggered = false;
}

function notifyUnauthorized() {
  if (unauthorizedTriggered) return;
  unauthorizedTriggered = true;
  unauthorizedHandler?.();
}

async function request<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...init?.headers,
    },
  });

  if (!res.ok) {
    if (res.status === 401) notifyUnauthorized();
    const detail = await res.text();
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export function uploadDocument(
  file: File,
  accessToken: string,
  options?: { force?: boolean },
): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const query = options?.force ? "?force=true" : "";
  return request<DocumentUploadResponse>(`/api/documents/upload${query}`, accessToken, {
    method: "POST",
    body: formData,
  });
}

/** 使用者在上傳的 409 filename_exists 衝突提示中選擇「覆蓋既有文件」時呼叫（見 upload-document-modal.tsx）。 */
export function reuploadDocument(
  documentId: string,
  file: File,
  accessToken: string,
): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return request<DocumentUploadResponse>(`/api/documents/${documentId}/reupload`, accessToken, {
    method: "POST",
    body: formData,
  });
}

export function getDocumentStatus(documentId: string, accessToken: string): Promise<DocumentStatusResponse> {
  return request<DocumentStatusResponse>(`/api/documents/${documentId}/status`, accessToken);
}

export function listDocuments(accessToken: string): Promise<DocumentListItem[]> {
  return request<DocumentListItem[]>("/api/documents", accessToken);
}

export function reorganizeDocument(
  documentId: string,
  manualCategories: string[],
  accessToken: string,
): Promise<void> {
  return request("/api/documents/reorganize", accessToken, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, manual_categories: manualCategories }),
  });
}

/** Citation 跳轉 API（見 roadmap Day 7）：依 citation 的 page_number 或 sheet_name+cell_range 定位。 */
export function getCitationDetail(
  citation: Pick<ChatCitation, "document_id" | "page_number" | "sheet_name" | "cell_range">,
  accessToken: string,
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
    accessToken,
  );
}

export function deleteDocument(documentId: string, accessToken: string): Promise<void> {
  return request<void>(`/api/documents/${documentId}`, accessToken, { method: "DELETE" });
}

export function unlockDocuments(documentIds: string[], accessToken: string): Promise<void> {
  return request("/api/documents/unlock", accessToken, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_ids: documentIds }),
  });
}

/** Report Mode（見 roadmap Day 8-9）：bounded tool-calling，回應比 Chat 慢（1-2 輪 LLM 呼叫），
 * 走一般 JSON 回應而非 SSE（SSE 僅限 Chat 使用，見 CLAUDE.md Guardrail #3）。
 */
export function generateReport(query: string, accessToken: string): Promise<ReportGenerateResponse> {
  return request<ReportGenerateResponse>("/api/reports/generate", accessToken, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

/**
 * Chat SSE 串流（見 roadmap Day 6）：用 `fetch` 讀取原始 Response，呼叫端自行用
 * `ReadableStream` 逐段讀取 body（`Authorization` header 直接帶 access token 即可，
 * 不需要 query string 傳 token 的過渡方案）。
 */
export async function streamChatQuery(
  query: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<ReadableStream<Uint8Array>> {
  const res = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ query }),
    signal,
  });

  if (!res.ok || !res.body) {
    if (res.status === 401) notifyUnauthorized();
    const detail = await res.text().catch(() => "");
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.body;
}
