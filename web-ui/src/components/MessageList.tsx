import { useEffect, useRef } from "react";
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
              <div className="whitespace-pre-wrap">
                {m.content}
                {m.streaming && <span className="inline-block w-2 h-4 ml-0.5 bg-accent animate-pulse align-baseline" />}
                {m.cancelled && <span className="ml-2 text-xs text-yellow-400">[cancelled]</span>}
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
        return null;
      })}
      {Object.entries(pendingTools).map(([id, t]) => (
        <ToolRow key={id} name={t.name} pending elapsed={Date.now() - t.startedAt} />
      ))}
      <div ref={bottomRef} />
    </ScrollArea>
  );
}
