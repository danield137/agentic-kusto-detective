import { useCallback, useState } from "react";
import LiveLog from "./components/LiveLog";
import NewSessionForm from "./components/NewSessionForm";
import SessionsTable from "./components/SessionsTable";
import type { SessionSummary } from "./api";

function App() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  const handleSessionStarted = (sessionId: string) => {
    setActiveSessionId(sessionId);
  };

  const handleSessionDone = useCallback((_summary?: SessionSummary) => {
    setActiveSessionId(null);
    setRefreshKey((k) => k + 1);
  }, []);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>
        🔍 Kusto Detective Dashboard
      </h1>
      <p style={{ color: "#6b7280", marginBottom: 24, fontSize: 14 }}>
        Agent benchmark sessions for detective.kusto.io challenges
      </p>

      <div style={{ marginBottom: 24 }}>
        <NewSessionForm onSessionStarted={handleSessionStarted} disabled={!!activeSessionId} />
      </div>

      {activeSessionId && (
        <div style={{ marginBottom: 24 }}>
          <LiveLog sessionId={activeSessionId} onDone={handleSessionDone} />
        </div>
      )}

      <SessionsTable
        refreshKey={refreshKey}
        onResumeStarted={handleSessionStarted}
        activeSessionId={activeSessionId}
      />
    </div>
  );
}

export default App;
