import { useStore } from "../state/store";
import { PCMPlayer, startCapture, type AudioCapture } from "./audio";

export class VoiceWS {
  private ws: WebSocket | null = null;
  private capture: AudioCapture | null = null;
  private player: PCMPlayer | null = null;

  async start(sessionId: string | "new" | "last", voice = "alloy") {
    const wsUrl = `ws://${location.host.replace(":5173", ":8000")}/ws/voice`;
    this.ws = new WebSocket(wsUrl);
    this.ws.binaryType = "arraybuffer";
    this.player = new PCMPlayer(24000);

    this.ws.onopen = async () => {
      this.ws!.send(JSON.stringify({ type: "hello", session_id: sessionId, voice }));
      this.capture = await startCapture((buf) => {
        if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(buf);
      });
    };

    this.ws.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) {
        this.player?.play(e.data);
        return;
      }
      try {
        const msg = JSON.parse(e.data);
        this.handleEvent(msg);
      } catch {
        // ignore non-JSON text frames
      }
    };

    this.ws.onclose = () => this.cleanup();
    this.ws.onerror = () => this.cleanup();

    useStore.getState().setMode("voice-active");
  }

  private handleEvent(msg: any) {
    const store = useStore.getState();
    switch (msg.type) {
      case "session_started":
        store.setSessionId(msg.session_id);
        break;
      case "speech_started":
        // User started speaking — barge in: clear playback
        this.player?.clear();
        break;
      case "transcript_user_done":
        store.setMessages([
          ...store.messages,
          { id: crypto.randomUUID(), role: "user", content: msg.text, voice: true },
        ]);
        break;
      case "transcript_assistant_done":
        store.setMessages([
          ...store.messages,
          { id: crypto.randomUUID(), role: "assistant", content: msg.text, voice: true },
        ]);
        break;
      case "tool_use_start":
      case "tool_use_end":
      case "tool_result":
        store.handleServerEvent(msg);
        break;
      case "turn_end":
        // Voice mode does not flip to idle on turn_end — the conversation continues.
        break;
      case "error":
        console.error("voice error:", msg.message);
        break;
    }
  }

  cancel() {
    this.ws?.send(JSON.stringify({ type: "cancel" }));
    this.player?.clear();
  }

  stop() {
    this.ws?.send(JSON.stringify({ type: "stop" }));
    this.cleanup();
  }

  private cleanup() {
    this.capture?.stop();
    this.capture = null;
    this.player?.close();
    this.player = null;
    this.ws?.close();
    this.ws = null;
    useStore.getState().setMode("idle");
  }

  get analyser() {
    return this.capture?.analyser ?? null;
  }
}

export const voiceWs = new VoiceWS();
