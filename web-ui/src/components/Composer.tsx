import { useState } from "react";
import { Textarea } from "./ui/textarea";
import { Button } from "./ui/button";
import { useStore } from "../state/store";
import { textWs } from "../lib/ws";
import { voiceWs } from "../lib/voice";
import { Mic, Send, Square } from "lucide-react";

export function Composer() {
  const [text, setText] = useState("");
  const mode = useStore((s) => s.mode);
  const streaming = mode === "text-streaming";
  const inVoice = mode === "voice-active";

  function submit() {
    if (!text.trim()) return;
    useStore.getState().optimisticUser(text.trim());
    textWs.sendUser(text.trim());
    setText("");
  }

  function cancel() {
    textWs.cancel();
  }

  function toggleVoice() {
    if (inVoice) voiceWs.stop();
    else voiceWs.start(useStore.getState().sessionId ?? "last");
  }

  return (
    <div className="border-t border-border p-3">
      <div className="flex items-end gap-2 rounded-xl border border-border bg-bg/40 px-3 py-2 focus-within:ring-2 focus-within:ring-accent transition">
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
          className="flex-1 border-0 bg-transparent px-0 py-1 focus-visible:ring-0 leading-6"
        />
        <div className="flex items-center gap-1 pb-0.5 shrink-0">
          <Button
            variant={inVoice ? "danger" : "ghost"}
            size="icon"
            onClick={toggleVoice}
            title={inVoice ? "stop voice mode" : "start voice mode"}
            disabled={streaming}
          >
            <Mic size={16} />
          </Button>
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
      </div>
    </div>
  );
}
