import { useEffect, useRef } from "react";
import { TopBar } from "./components/TopBar";
import { Sidebar } from "./components/Sidebar";
import { MessageList } from "./components/MessageList";
import { Composer } from "./components/Composer";
import { VoiceBar } from "./components/VoiceBar";
import { useStore } from "./state/store";
import { textWs } from "./lib/ws";
import * as tts from "./lib/tts";

export default function App() {
  const provider = useStore((s) => s.provider);
  const model = useStore((s) => s.model);
  const ttsEnabled = useStore((s) => s.ttsEnabled);
  const lastTextRef = useRef("");

  // Connect text WS once on mount; resume the most recent session if any.
  useEffect(() => {
    textWs.connect({ sessionId: "last", provider, model });
    return () => textWs.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Wire TTS: subscribe to streaming text_delta via the store.
  useEffect(() => {
    if (!ttsEnabled) {
      lastTextRef.current = "";
      return;
    }
    const unsub = useStore.subscribe((state) => {
      const last = state.messages[state.messages.length - 1];
      if (!last || last.role !== "assistant") return;
      const prevText = lastTextRef.current;
      const delta = last.content.slice(prevText.length);
      if (delta) tts.feedDelta(delta);
      lastTextRef.current = last.content;
      if (!last.streaming) {
        tts.flush();
        lastTextRef.current = "";
      }
    });
    return () => { unsub(); tts.cancel(); lastTextRef.current = ""; };
  }, [ttsEnabled]);

  return (
    <div className="h-full flex flex-col">
      <TopBar />
      <div className="flex-1 flex min-h-0">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <MessageList />
          <VoiceBar />
          <Composer />
        </div>
      </div>
    </div>
  );
}
