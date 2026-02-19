export interface SessionSummary {
  session_id: string;
  log_file: string;
  status: string;
  challenge_url: string | null;
  started_at: string | null;
  agent_messages: number;
  tool_calls: number;
  wall_clock_s: number | null;
  tool_time_s: number | null;
  llm_time_s: number | null;
}

export interface SessionEvent {
  type: string;
  [key: string]: unknown;
}

const API_BASE = "/api";

export async function fetchSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) throw new Error(`Failed to fetch sessions: ${res.status}`);
  return res.json();
}

export async function startSession(challengeUrl: string): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ challenge_url: challengeUrl }),
  });
  if (!res.ok) throw new Error(`Failed to start session: ${res.status}`);
  return res.json();
}

export async function resumeSession(sessionId: string): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/resume`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to resume session: ${res.status}`);
  return res.json();
}

export function streamSession(
  sessionId: string,
  onEvent: (event: SessionEvent) => void,
  onDone: (summary?: SessionSummary) => void
): () => void {
  const es = new EventSource(`${API_BASE}/sessions/${sessionId}/stream`);

  es.addEventListener("summary", (e) => {
    const summary = JSON.parse(e.data) as SessionSummary;
    onDone(summary);
    es.close();
  });

  es.addEventListener("done", () => {
    onDone();
    es.close();
  });

  es.addEventListener("error", () => {
    onDone();
    es.close();
  });

  // Catch all other event types
  es.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {
      onEvent({ type: "raw", data: e.data });
    }
  };

  // Also listen for named event types from the agent
  for (const etype of [
    "assistant.message",
    "assistant.message_delta",
    "session.idle",
  ]) {
    es.addEventListener(etype, (e) => {
      try {
        onEvent(JSON.parse(e.data));
      } catch {
        onEvent({ type: etype, data: e.data });
      }
    });
  }

  return () => es.close();
}
