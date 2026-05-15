import { useEffect } from "react";
import { TopBar } from "./components/TopBar";
import { Sidebar } from "./components/Sidebar";
import { MessageList } from "./components/MessageList";
import { Composer } from "./components/Composer";
import { VoiceBar } from "./components/VoiceBar";
import { useStore } from "./state/store";
import { textWs } from "./lib/ws";

export default function App() {
  const provider = useStore((s) => s.provider);
  const model = useStore((s) => s.model);

  // Connect text WS once on mount; resume the most recent session if any.
  useEffect(() => {
    textWs.connect({ sessionId: "last", provider, model });
    return () => textWs.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
