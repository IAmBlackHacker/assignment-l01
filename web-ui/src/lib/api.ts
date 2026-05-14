import type { Session } from "../state/store";

export async function fetchSessions(): Promise<Session[]> {
  const r = await fetch("/api/sessions");
  if (!r.ok) throw new Error(`sessions: ${r.status}`);
  return r.json();
}
