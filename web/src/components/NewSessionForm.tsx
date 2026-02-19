import { useState } from "react";

interface Props {
  onSessionStarted: (sessionId: string) => void;
  disabled?: boolean;
}

const DEFAULT_URL = "https://detective.kusto.io/inbox/onboarding";

export default function NewSessionForm({ onSessionStarted, disabled }: Props) {
  const [url, setUrl] = useState(DEFAULT_URL);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim() || loading || disabled) return;

    setLoading(true);
    try {
      const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challenge_url: url.trim() }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      const data = await res.json();
      onSessionStarted(data.session_id);
    } catch (err) {
      console.error(err);
      alert("Failed to start session");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Challenge URL"
        disabled={loading || disabled}
        style={{
          flex: 1,
          padding: "8px 12px",
          borderRadius: 6,
          border: "1px solid #d1d5db",
          fontSize: 14,
        }}
      />
      <button
        type="submit"
        disabled={loading || disabled || !url.trim()}
        style={{
          padding: "8px 20px",
          borderRadius: 6,
          border: "none",
          background: loading || disabled ? "#94a3b8" : "#3b82f6",
          color: "#fff",
          fontWeight: 600,
          fontSize: 14,
          cursor: loading || disabled ? "not-allowed" : "pointer",
        }}
      >
        {loading ? "Starting…" : "▶ Start"}
      </button>
    </form>
  );
}
