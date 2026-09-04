"use client";

import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { IdentitySwitcher } from "@/components/identity-switcher";
import { useDevIdentity } from "@/lib/dev-identity";
import { streamChatQuery, getCitationDetail, type ChatCitation } from "@/lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
  status: "streaming" | "done" | "error";
  citations: ChatCitation[];
};

/** 對應 backend/app/services/chat.py `_citation_label`：比對訊息文字中的 `[來源：...]` 標籤。 */
const CITATION_TAG_REGEX = /\[來源：([^\]]+)\]/g;

/** 把訊息文字中能對應到 citations 列表的 `[來源：...]` 標籤換成可點擊按鈕，其餘維持純文字。 */
function renderMessageContent(
  content: string,
  citations: ChatCitation[],
  onCitationClick: (citation: ChatCitation) => void,
): React.ReactNode[] {
  if (citations.length === 0) return [content];

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  const regex = new RegExp(CITATION_TAG_REGEX);
  let match: RegExpExecArray | null;

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index));
    }
    const citation = citations.find((c) => c.label === match![1]);
    parts.push(
      citation ? (
        <button
          key={`citation-${key++}`}
          type="button"
          onClick={() => onCitationClick(citation)}
          className="mx-0.5 rounded border border-primary/50 px-1 text-primary underline-offset-2 hover:underline"
        >
          {match[0]}
        </button>
      ) : (
        match[0]
      ),
    );
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }
  return parts;
}

/** Citation 跳轉 Modal（見 roadmap Day 7）：打 Citation 跳轉 API 顯示整段原文，不做精確段落高亮。 */
function CitationModal({ citation, onClose }: { citation: ChatCitation; onClose: () => void }) {
  const identity = useDevIdentity();
  const detailQuery = useQuery({
    queryKey: ["citation", citation.document_id, citation.page_number, citation.sheet_name, citation.cell_range],
    queryFn: () => getCitationDetail(citation, identity),
  });

  const location =
    citation.sheet_name != null
      ? `工作表：${citation.sheet_name} ${citation.cell_range ?? ""}`
      : `第 ${citation.page_number} 頁`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-md border bg-background p-4 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold">{citation.file_name}</p>
            <p className="text-xs text-muted-foreground">{location}</p>
          </div>
          <Button type="button" variant="ghost" size="xs" onClick={onClose}>
            關閉
          </Button>
        </div>

        {detailQuery.isLoading && <p className="text-sm text-muted-foreground">載入中...</p>}
        {detailQuery.isError && (
          <p className="text-sm text-destructive">載入失敗：{(detailQuery.error as Error).message}</p>
        )}
        {detailQuery.data && (
          <p className="whitespace-pre-wrap text-sm">{detailQuery.data.content}</p>
        )}
      </div>
    </div>
  );
}

/** 逐段解析 SSE frame（"event: X\ndata: Y\n\n"），對應 backend/app/services/chat.py 的事件格式。 */
function parseSseFrame(frame: string): { event: string; data: unknown } | null {
  const eventLine = frame.split("\n").find((line) => line.startsWith("event: "));
  const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
  if (!eventLine || !dataLine) return null;
  return {
    event: eventLine.slice("event: ".length),
    data: JSON.parse(dataLine.slice("data: ".length)),
  };
}

export default function ChatPage() {
  const identity = useDevIdentity();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<ChatCitation | null>(null);
  const lastQueryRef = useRef("");

  async function runQuery(query: string) {
    setIsStreaming(true);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", status: "streaming", citations: [] },
    ]);

    const appendDelta = (delta: string) => {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, content: last.content + delta };
        return next;
      });
    };

    const setCitations = (citations: ChatCitation[]) => {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, citations };
        return next;
      });
    };

    const markStatus = (status: Message["status"], errorSuffix?: string) => {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = {
          ...last,
          status,
          content: errorSuffix ? `${last.content}\n\n⚠️ ${errorSuffix}` : last.content,
        };
        return next;
      });
    };

    try {
      const body = await streamChatQuery(query, identity);
      const reader = body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const rawFrame of frames) {
          const parsed = parseSseFrame(rawFrame);
          if (!parsed) continue;

          if (parsed.event === "message") {
            appendDelta((parsed.data as { delta: string }).delta);
          } else if (parsed.event === "citations") {
            setCitations((parsed.data as { citations: ChatCitation[] }).citations);
          } else if (parsed.event === "error") {
            markStatus("error", (parsed.data as { message: string }).message);
            setIsStreaming(false);
            return;
          } else if (parsed.event === "done") {
            markStatus("done");
            setIsStreaming(false);
            return;
          }
        }
      }

      markStatus("done");
    } catch {
      markStatus("error", "串流連線中斷，請重試");
    } finally {
      setIsStreaming(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const query = input.trim();
    if (!query || isStreaming) return;

    lastQueryRef.current = query;
    setMessages((prev) => [...prev, { role: "user", content: query, status: "done", citations: [] }]);
    setInput("");
    void runQuery(query);
  }

  function handleRetry() {
    if (!lastQueryRef.current || isStreaming) return;
    setMessages((prev) => prev.slice(0, -1));
    void runQuery(lastQueryRef.current);
  }

  const lastMessage = messages[messages.length - 1];

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">知識問答 Chat</h1>
        <IdentitySwitcher />
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto rounded-md border p-4">
        {messages.length === 0 && (
          <p className="text-sm text-muted-foreground">輸入問題開始對話，回答只依據已上傳文件的檢索內容。</p>
        )}
        {messages.map((message, i) => (
          <div
            key={i}
            className={`whitespace-pre-wrap rounded-md px-3 py-2 text-sm ${
              message.role === "user" ? "ml-auto max-w-[80%] bg-primary text-primary-foreground" : "max-w-[80%] bg-muted"
            }`}
          >
            {renderMessageContent(message.content, message.citations, setSelectedCitation)}
            {message.status === "streaming" && <span className="animate-pulse">▍</span>}
          </div>
        ))}
      </div>

      {lastMessage?.status === "error" && (
        <Button type="button" variant="outline" size="sm" onClick={handleRetry} className="self-start">
          重試
        </Button>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="輸入問題..."
          disabled={isStreaming}
        />
        <Button type="submit" disabled={isStreaming || !input.trim()}>
          送出
        </Button>
      </form>

      {selectedCitation && (
        <CitationModal citation={selectedCitation} onClose={() => setSelectedCitation(null)} />
      )}
    </main>
  );
}
