import { useState } from "react";
import { Textarea } from "./ui/textarea";
import { Button } from "./ui/button";
import { useStore } from "../state/store";
import { textWs } from "../lib/ws";
import { Send, Square } from "lucide-react";

export function Composer() {
  const [text, setText] = useState("");
  const mode = useStore((s) => s.mode);
  const streaming = mode === "text-streaming";

  function submit() {
    if (!text.trim()) return;
    useStore.getState().optimisticUser(text.trim());
    textWs.sendUser(text.trim());
    setText("");
  }

  function cancel() {
    textWs.cancel();
  }

  return (
    <div className="border-t border-border p-3 flex items-end gap-2">
      <Textarea
        rows={2}
        placeholder={streaming ? "[streaming — press Esc to cancel]" : "Ask anything…"}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
          if (e.key === "Escape" && streaming) cancel();
        }}
        disabled={streaming}
      />
      {streaming ? (
        <Button variant="danger" size="icon" onClick={cancel} title="cancel">
          <Square size={16} />
        </Button>
      ) : (
        <Button size="icon" onClick={submit} disabled={!text.trim()} title="send">
          <Send size={16} />
        </Button>
      )}
    </div>
  );
}
