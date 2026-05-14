import { useStore } from "../state/store";

type HelloOpts = { sessionId: "new" | "last" | string; provider: string; model: string | null };

export class TextWS {
  private ws: WebSocket | null = null;
  private opts: HelloOpts | null = null;
  private retries = 0;

  connect(opts: HelloOpts) {
    this.opts = opts;
    this.open();
  }

  private open() {
    const ws = new WebSocket(`ws://${location.host.replace(":5173", ":8000")}/ws/text`);
    this.ws = ws;
    ws.onopen = () => {
      this.retries = 0;
      ws.send(JSON.stringify({
        type: "hello",
        session_id: this.opts!.sessionId,
        provider: this.opts!.provider,
        model: this.opts!.model,
      }));
    };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        useStore.getState().handleServerEvent(msg);
      } catch {
        // ignore non-JSON
      }
    };
    ws.onclose = () => this.scheduleReconnect();
    ws.onerror = () => { /* onclose handles cleanup */ };
  }

  private scheduleReconnect() {
    if (this.retries >= 5) return;
    const delay = Math.min(250 * 2 ** this.retries, 10_000);
    this.retries += 1;
    setTimeout(() => this.open(), delay);
  }

  sendUser(content: string) {
    this.ws?.send(JSON.stringify({ type: "user", content }));
  }

  cancel() {
    this.ws?.send(JSON.stringify({ type: "cancel" }));
  }

  updateSettings(provider?: string, model?: string | null) {
    this.ws?.send(JSON.stringify({ type: "update_settings", provider, model }));
  }

  close() {
    this.retries = 99;  // disable reconnect
    this.ws?.close();
  }
}

export const textWs = new TextWS();
