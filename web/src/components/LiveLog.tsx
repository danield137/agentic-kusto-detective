import { useEffect, useRef, useState } from "react";
import type { SessionEvent, SessionSummary } from "../api";
import { streamSession } from "../api";

interface Props {
  sessionId: string;
  onDone: (summary?: SessionSummary) => void;
}

export default function LiveLog({ sessionId, onDone }: Props) {
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = streamSession(
      sessionId,
      (evt) => setEvents((prev) => [...prev, evt]),
      onDone
    );
    return close;
  }, [sessionId, onDone]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return (
    <div
      style={{
        background: "#1e1e2e",
        color: "#cdd6f4",
        borderRadius: 8,
        padding: 16,
        maxHeight: 400,
        overflowY: "auto",
        fontFamily: "monospace",
        fontSize: 13,
        lineHeight: 1.6,
      }}
    >
      <div style={{ color: "#89b4fa", marginBottom: 8 }}>
        🔴 Live — {sessionId}
      </div>
      {events.length === 0 && (
        <div style={{ color: "#6c7086" }}>Waiting for events…</div>
      )}
      {events.map((evt, i) => (
        <div key={i} style={{ borderBottom: "1px solid #313244", padding: "4px 0" }}>
          <span style={{ color: "#f9e2af" }}>{evt.type}</span>
          {evt.type === "error" && (
            <span style={{ color: "#f38ba8", marginLeft: 8 }}>
              {String(evt.error || "")}
            </span>
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
