import { useEffect } from "react";
import { useStore } from "../state/store";
import { Button } from "./ui/button";
import { fetchSessions } from "../lib/api";
import { textWs } from "../lib/ws";
import { Plus } from "lucide-react";

export function Sidebar() {
  const { sessions, sessionId, setSessions, setMessages, setSessionId, provider, model } = useStore();

  useEffect(() => {
    const load = () => fetchSessions().then(setSessions).catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [setSessions]);

  function newChat() {
    setMessages([]);
    setSessionId(null);
    textWs.close();
    textWs.connect({ sessionId: "new", provider, model });
  }

  function pick(id: string) {
    setMessages([]);
    setSessionId(id);
    textWs.close();
    textWs.connect({ sessionId: id, provider, model });
  }

  return (
    <aside className="w-[260px] border-r border-border flex flex-col bg-bg">
      <div className="p-3 border-b border-border">
        <Button onClick={newChat} className="w-full">
          <Plus size={14} className="mr-1" /> New chat
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {sessions.map((s) => (
          <button
            key={s.id}
            onClick={() => pick(s.id)}
            className={`block w-full text-left px-3 py-2 text-sm truncate transition-colors hover:bg-fg/[0.06] ${s.id === sessionId ? "bg-fg/[0.10]" : ""}`}
          >
            <div className="truncate">{s.title || s.id}</div>
            <div className="text-xs text-muted">{new Date(s.updated_at * 1000).toLocaleString()} · {s.message_count} msgs</div>
          </button>
        ))}
      </div>
    </aside>
  );
}
