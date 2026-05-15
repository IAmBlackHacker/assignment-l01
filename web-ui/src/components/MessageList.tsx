import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore, type Message } from "../state/store";
import { ToolRow } from "./ToolRow";
import { ScrollArea } from "./ui/scroll-area";

type Block =
  | { kind: "user"; message: Message }
  | { kind: "error"; message: Message }
  | { kind: "assistant"; messages: Message[]; voice: boolean };

function groupMessages(messages: Message[]): Block[] {
  const blocks: Block[] = [];
  for (const m of messages) {
    if (m.role === "user") {
      blocks.push({ kind: "user", message: m });
    } else if (m.role === "error") {
      blocks.push({ kind: "error", message: m });
    } else {
      const last = blocks[blocks.length - 1];
      if (last && last.kind === "assistant") {
        last.messages.push(m);
        if (m.voice) last.voice = true;
      } else {
        blocks.push({ kind: "assistant", messages: [m], voice: !!m.voice });
      }
    }
  }
  return blocks;
}

export function MessageList() {
  const { messages, pendingTools } = useStore();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, pendingTools]);

  const blocks = groupMessages(messages);
  const pendingEntries = Object.entries(pendingTools);
  const attachPendingToLast =
    pendingEntries.length > 0 &&
    blocks.length > 0 &&
    blocks[blocks.length - 1].kind === "assistant";

  return (
    <ScrollArea className="flex-1 px-6 py-4 space-y-4">
      {blocks.map((block, blockIdx) => {
        if (block.kind === "user") {
          const m = block.message;
          return (
            <div key={m.id} className="space-y-1">
              <div className="text-xs text-accent font-medium">You {m.voice && "🎤"}</div>
              <div className="whitespace-pre-wrap">{m.content}</div>
            </div>
          );
        }
        if (block.kind === "error") {
          const m = block.message;
          return (
            <div key={m.id} className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-700">
              <span className="font-mono text-xs mr-2">[error]</span>
              {m.content}
            </div>
          );
        }
        const isLastBlock = blockIdx === blocks.length - 1;
        return (
          <div key={`assistant-${block.messages[0].id}`} className="space-y-2">
            <div className="text-xs text-muted font-medium">Assistant {block.voice && "🔊"}</div>
            {block.messages.map((m) => {
              if (m.role === "assistant") {
                if (!m.content && !m.streaming) return null;
                return (
                  <div key={m.id} className="prose prose-sm max-w-none prose-pre:my-2 prose-pre:bg-surface prose-pre:text-fg prose-pre:border prose-pre:border-border prose-code:before:content-none prose-code:after:content-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {m.content}
                    </ReactMarkdown>
                    {m.streaming && <span className="inline-block w-2 h-4 ml-0.5 bg-accent animate-pulse align-baseline" />}
                    {m.cancelled && <span className="ml-2 text-xs text-yellow-600">[cancelled]</span>}
                  </div>
                );
              }
              if (m.role === "tool" && m.toolResults) {
                return (
                  <div key={m.id} className="space-y-1">
                    {m.toolResults.map((r) => (
                      <ToolRow key={r.id} name={r.name} pending={false} result={r.content} isError={r.isError} />
                    ))}
                  </div>
                );
              }
              return null;
            })}
            {attachPendingToLast && isLastBlock && pendingEntries.map(([id, t]) => (
              <ToolRow key={id} name={t.name} pending elapsed={Date.now() - t.startedAt} />
            ))}
          </div>
        );
      })}
      {!attachPendingToLast && pendingEntries.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-muted font-medium">Assistant</div>
          {pendingEntries.map(([id, t]) => (
            <ToolRow key={id} name={t.name} pending elapsed={Date.now() - t.startedAt} />
          ))}
        </div>
      )}
      <div ref={bottomRef} />
    </ScrollArea>
  );
}
