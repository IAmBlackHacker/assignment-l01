import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "./store";

beforeEach(() => {
  useStore.setState({
    mode: "idle",
    messages: [],
    pendingTools: {},
    sessionId: null,
  });
});

describe("store: text-mode events", () => {
  it("text_delta accumulates into a streaming assistant message", () => {
    const s = useStore.getState();
    s.optimisticUser("hi");
    s.handleServerEvent({ type: "text_delta", text: "hello" });
    s.handleServerEvent({ type: "text_delta", text: " world" });
    const state = useStore.getState();
    expect(state.messages.length).toBe(2);
    expect(state.messages[1].role).toBe("assistant");
    expect(state.messages[1].content).toBe("hello world");
    expect(state.messages[1].streaming).toBe(true);
  });

  it("tool_use events move through pendingTools and resolve", () => {
    const s = useStore.getState();
    s.handleServerEvent({ type: "tool_use_start", id: "t1", name: "weather" });
    expect(useStore.getState().pendingTools["t1"]).toBeTruthy();
    s.handleServerEvent({ type: "tool_use_end", id: "t1", name: "weather", args: {} });
    s.handleServerEvent({
      type: "tool_result", id: "t1", name: "weather",
      content: { temp_c: 12 }, is_error: false,
    });
    const state = useStore.getState();
    expect(state.pendingTools["t1"]).toBeUndefined();
    const toolMsg = state.messages.find((m) => m.role === "tool");
    expect(toolMsg?.toolResults?.[0].content).toEqual({ temp_c: 12 });
  });

  it("cancel marks the streaming assistant message cancelled", () => {
    const s = useStore.getState();
    s.optimisticUser("hi");
    s.handleServerEvent({ type: "text_delta", text: "partial" });
    s.handleServerEvent({ type: "turn_end", reason: "cancelled" });
    const state = useStore.getState();
    const last = state.messages[state.messages.length - 1];
    expect(last.role).toBe("assistant");
    expect(last.cancelled).toBe(true);
    expect(last.streaming).toBe(false);
    expect(state.mode).toBe("idle");
  });
});
