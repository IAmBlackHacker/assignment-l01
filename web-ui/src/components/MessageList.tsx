import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "../state/store";
import { ToolRow } from "./ToolRow";
import { ScrollArea } from "./ui/scroll-area";

export function MessageList() {
  const { messages, pendingTools } = useStore();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, pendingTools]);

  return (
    <ScrollArea className="flex-1 px-6 py-4 space-y-3">
      {messages.map((m) => {
        if (m.role === "user") {
          return (
            <div key={m.id} className="space-y-1">
              <div className="text-xs text-accent font-medium">you {m.voice && "🎤"}</div>
              <div className="whitespace-pre-wrap">{m.content}</div>
            </div>
          );
        }
        if (m.role === "assistant") {
          return (
            <div key={m.id} className="space-y-1">
              <div className="text-xs text-muted font-medium">assistant {m.voice && "🔊"}</div>
              <div className="prose prose-sm max-w-none prose-pre:my-2 prose-pre:bg-gray-100 prose-pre:text-gray-900 prose-pre:border prose-pre:border-border prose-code:before:content-none prose-code:after:content-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {m.content}
                </ReactMarkdown>
                {m.streaming && <span className="inline-block w-2 h-4 ml-0.5 bg-accent animate-pulse align-baseline" />}
                {m.cancelled && <span className="ml-2 text-xs text-yellow-600">[cancelled]</span>}
              </div>
            </div>
          );
        }
        if (m.role === "tool" && m.toolResults) {
          return (
            <div key={m.id}>
              {m.toolResults.map((r) => (
                <ToolRow key={r.id} name={r.name} pending={false} result={r.content} isError={r.isError} />
              ))}
            </div>
          );
        }
        if (m.role === "error") {
          return (
            <div key={m.id} className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-700">
              <span className="font-mono text-xs mr-2">[error]</span>
              {m.content}
            </div>
          );
        }
        return null;
      })}
      {Object.entries(pendingTools).map(([id, t]) => (
        <ToolRow key={id} name={t.name} pending elapsed={Date.now() - t.startedAt} />
      ))}
      <div ref={bottomRef} />
    </ScrollArea>
  );
}
