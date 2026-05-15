import { create } from "zustand";

export type Mode = "idle" | "text-streaming" | "voice-active";

export type Message = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolCalls?: { id: string; name: string; args: any }[];
  toolResults?: { id: string; name: string; content: any; isError: boolean }[];
  voice?: boolean;
  cancelled?: boolean;
  streaming?: boolean;
};

export type Session = { id: string; title: string; updated_at: number; message_count: number };

type ServerEvent =
  | { type: "session_started"; session_id: string; created: boolean; resumed_turns?: number; messages?: Message[] }
  | { type: "user_echo"; content: string; ts?: number }
  | { type: "text_delta"; text: string }
  | { type: "tool_use_start"; id: string; name: string }
  | { type: "tool_use_end"; id: string; name: string; args: any }
  | { type: "tool_result"; id: string; name: string; content: any; is_error: boolean }
  | { type: "turn_end"; reason: "stop" | "tool_use" | "cancelled" | "error" }
  | { type: "error"; message: string; transient?: boolean }
  | { type: string; [k: string]: any };

interface Store {
  provider: "anthropic" | "openai" | "gemini";
  model: string | null;
  ttsEnabled: boolean;
  voiceName: "alloy" | "verse" | "shimmer";

  mode: Mode;
  sessionId: string | null;
  messages: Message[];
  sessions: Session[];
  pendingTools: Record<string, { name: string; startedAt: number }>;

  setProvider: (p: Store["provider"]) => void;
  setModel: (m: string | null) => void;
  toggleTts: () => void;
  setSessions: (s: Session[]) => void;
  setSessionId: (id: string | null) => void;
  setMode: (m: Mode) => void;
  setMessages: (m: Message[]) => void;

  handleServerEvent: (ev: ServerEvent) => void;
  optimisticUser: (content: string) => void;
  beginTurn: () => void;
  endTurn: (cancelled?: boolean) => void;
}

export const useStore = create<Store>((set, get) => ({
  provider: "gemini",
  model: null,
  ttsEnabled: false,
  voiceName: "alloy",

  mode: "idle",
  sessionId: null,
  messages: [],
  sessions: [],
  pendingTools: {},

  setProvider: (provider) => set({ provider }),
  setModel: (model) => set({ model }),
  toggleTts: () => set((s) => ({ ttsEnabled: !s.ttsEnabled })),
  setSessions: (sessions) => set({ sessions }),
  setSessionId: (sessionId) => set({ sessionId }),
  setMode: (mode) => set({ mode }),
  setMessages: (messages) => set({ messages }),

  optimisticUser: (content) =>
    set((s) => ({
      messages: [
        ...s.messages,
        { id: crypto.randomUUID(), role: "user", content },
      ],
      mode: "text-streaming",
    })),

  beginTurn: () => set({ mode: "text-streaming" }),

  endTurn: (cancelled = false) =>
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant" && msgs[i].streaming) {
          msgs[i] = { ...msgs[i], streaming: false, cancelled };
          break;
        }
      }
      return { messages: msgs, mode: "idle" };
    }),

  handleServerEvent: (ev) => {
    const state = get();
    switch (ev.type) {
      case "session_started":
        set({
          sessionId: ev.session_id,
          messages: Array.isArray(ev.messages) ? ev.messages : [],
        });
        return;
      case "user_echo":
        return;
      case "text_delta": {
        const msgs = [...state.messages];
        const last = msgs[msgs.length - 1];
        if (last && last.role === "assistant" && last.streaming) {
          msgs[msgs.length - 1] = { ...last, content: last.content + ev.text };
        } else {
          msgs.push({
            id: crypto.randomUUID(),
            role: "assistant",
            content: ev.text,
            streaming: true,
          });
        }
        set({ messages: msgs });
        return;
      }
      case "tool_use_start":
        set({ pendingTools: { ...state.pendingTools, [ev.id]: { name: ev.name, startedAt: Date.now() } } });
        return;
      case "tool_use_end":
        return;
      case "tool_result": {
        const { [ev.id]: _, ...rest } = state.pendingTools;
        const msgs = [...state.messages];
        msgs.push({
          id: ev.id,
          role: "tool",
          content: "",
          toolResults: [{ id: ev.id, name: ev.name, content: ev.content, isError: ev.is_error }],
        });
        set({ pendingTools: rest, messages: msgs });
        return;
      }
      case "turn_end":
        get().endTurn(ev.reason === "cancelled");
        return;
      case "error":
        if (!ev.transient) set({ mode: "idle" });
        return;
    }
  },
}));
