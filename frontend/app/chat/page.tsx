"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { IdentitySwitcher } from "@/components/identity-switcher";
import { useDevIdentity } from "@/lib/dev-identity";
import { streamChatQuery } from "@/lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
  status: "streaming" | "done" | "error";
};

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
  const lastQueryRef = useRef("");

  async function runQuery(query: string) {
    setIsStreaming(true);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", status: "streaming" },
    ]);

    const appendDelta = (delta: string) => {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, content: last.content + delta };
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
    setMessages((prev) => [...prev, { role: "user", content: query, status: "done" }]);
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
            {message.content}
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
    </main>
  );
}
