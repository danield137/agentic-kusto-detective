import { useEffect, useState } from "react";
import type { SessionSummary } from "../api";
import { fetchSessions } from "../api";

function fmt(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(0);
  return `${m}m ${s}s`;
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    completed: "#22c55e",
    running: "#3b82f6",
    incomplete: "#f59e0b",
    unknown: "#94a3b8",
  };
  const color = colors[status] || colors.unknown;
  return (
    <span
      style={{
        background: color,
        color: "#fff",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {status}
    </span>
  );
}

interface Props {
  refreshKey: number;
  onResumeStarted?: (sessionId: string) => void;
  activeSessionId?: string | null;
}

export default function SessionsTable({ refreshKey, onResumeStarted, activeSessionId }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchSessions()
      .then(setSessions)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [refreshKey]);

  if (loading) return <p>Loading sessions…</p>;
  if (sessions.length === 0) return <p>No sessions yet. Start one!</p>;

  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr>
          {[
            "Session ID",
            "Status",
            "Challenge",
            "Messages",
            "Tool Calls",
            "Wall Clock",
            "Tool Time",
            "LLM Time",
            "",
          ].map((h) => (
            <th
              key={h}
              style={{
                textAlign: "left",
                padding: "8px 12px",
                borderBottom: "2px solid #e5e7eb",
                fontSize: 13,
                color: "#6b7280",
              }}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sessions.map((session) => (
          <tr key={session.session_id} style={{ borderBottom: "1px solid #f3f4f6" }}>
            <td style={{ padding: "8px 12px", fontFamily: "monospace", fontSize: 13 }}>
              {session.session_id.replace("session_", "")}
            </td>
            <td style={{ padding: "8px 12px" }}>{statusBadge(session.status)}</td>
            <td
              style={{
                padding: "8px 12px",
                maxWidth: 250,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                fontSize: 13,
              }}
              title={session.challenge_url || ""}
            >
              {session.challenge_url || "—"}
            </td>
            <td style={{ padding: "8px 12px", textAlign: "right" }}>{session.agent_messages}</td>
            <td style={{ padding: "8px 12px", textAlign: "right" }}>{session.tool_calls}</td>
            <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace" }}>
              {fmt(session.wall_clock_s)}
            </td>
            <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace" }}>
              {fmt(session.tool_time_s)}
            </td>
            <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace" }}>
              {fmt(session.llm_time_s)}
            </td>
            <td style={{ padding: "8px 12px" }}>
              {(session.status === "incomplete" || session.status === "failed") && onResumeStarted && (
                <button
                  disabled={!!activeSessionId}
                  onClick={async () => {
                    try {
                      const res = await fetch(`/api/sessions/${session.session_id}/resume`, { method: "POST" });
                      if (!res.ok) throw new Error(`${res.status}`);
                      const data = await res.json();
                      onResumeStarted(data.session_id);
                    } catch (err) {
                      console.error(err);
                      alert("Failed to resume session");
                    }
                  }}
                  style={{
                    padding: "4px 12px",
                    borderRadius: 4,
                    border: "none",
                    background: activeSessionId ? "#94a3b8" : "#f59e0b",
                    color: "#fff",
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: activeSessionId ? "not-allowed" : "pointer",
                  }}
                >
                  ▶ Resume
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
