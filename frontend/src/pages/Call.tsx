import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
} from "@livekit/components-react";
import { useCallback, useEffect, useState } from "react";

type AgentState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";

const STATE_LABELS: Record<AgentState, string> = {
  idle: "Idle",
  connecting: "Connecting…",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  error: "Error",
};

const STATE_COLORS: Record<AgentState, string> = {
  idle: "#94a3b8",
  connecting: "#f59e0b",
  listening: "#22c55e",
  thinking: "#3b82f6",
  speaking: "#a855f7",
  error: "#ef4444",
};

interface ConnectResult {
  token: string;
  url: string;
  room_name: string;
  agent: string;
}

export default function Call() {
  const params = new URLSearchParams(window.location.search);
  const agentId = params.get("agent_id") ?? "";

  const [connectResult, setConnectResult] = useState<ConnectResult | null>(null);
  const [agentState, setAgentState] = useState<AgentState>("idle");
  const [error, setError] = useState("");

  const connect = useCallback(async () => {
    if (!agentId) {
      setError("No agent_id provided in URL.");
      return;
    }
    setAgentState("connecting");
    setError("");
    try {
      const res = await fetch("/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? "Failed to connect");
      }
      const data: ConnectResult = await res.json();
      setConnectResult(data);
    } catch (err) {
      setAgentState("error");
      setError(err instanceof Error ? err.message : "Connection failed");
    }
  }, [agentId]);

  // Auto-connect when agent_id param is present
  useEffect(() => {
    if (agentId) {
      connect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!connectResult) {
    return (
      <div style={styles.container}>
        <h1 style={styles.title}>Voice Agent</h1>
        {agentState === "error" ? (
          <p style={styles.error}>{error}</p>
        ) : agentState === "connecting" ? (
          <p style={{ color: "#f59e0b" }}>Connecting…</p>
        ) : (
          <button style={styles.button} onClick={connect}>
            Connect
          </button>
        )}
      </div>
    );
  }

  return (
    <LiveKitRoom
      serverUrl={connectResult.url}
      token={connectResult.token}
      connect
      audio
      video={false}
      onDisconnected={() => setConnectResult(null)}
    >
      <RoomAudioRenderer />
      <AgentUI
        agentName={connectResult.agent}
        state={agentState}
        onStateChange={setAgentState}
      />
    </LiveKitRoom>
  );
}

function AgentUI({
  agentName,
  state,
  onStateChange,
}: {
  agentName: string;
  state: AgentState;
  onStateChange: (s: AgentState) => void;
}) {
  const { state: vaState } = useVoiceAssistant();

  useEffect(() => {
    if (!vaState) return;
    const map: Record<string, AgentState> = {
      listening: "listening",
      thinking: "thinking",
      speaking: "speaking",
    };
    onStateChange(map[vaState] ?? "listening");
  }, [vaState, onStateChange]);

  const color = STATE_COLORS[state];
  const label = STATE_LABELS[state];

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>{agentName}</h1>
      <div
        style={{
          ...styles.badge,
          background: color,
        }}
      >
        <span style={styles.dot} />
        {label}
      </div>
      <p style={{ color: "#94a3b8", marginTop: 24, fontSize: "0.9rem" }}>
        {state === "listening" && "Speak now…"}
        {state === "thinking" && "Processing your request…"}
        {state === "speaking" && "Agent is responding…"}
      </p>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    fontFamily: "system-ui, sans-serif",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    minHeight: "100vh",
    background: "#0f172a",
    color: "white",
    padding: 20,
  },
  title: {
    fontSize: "2rem",
    marginBottom: 32,
    fontWeight: 600,
  },
  badge: {
    display: "inline-flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 24px",
    borderRadius: 999,
    fontSize: "1.1rem",
    fontWeight: 600,
    color: "white",
    transition: "background 0.3s ease",
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: "50%",
    background: "rgba(255,255,255,0.8)",
    display: "inline-block",
  },
  button: {
    padding: "14px 40px",
    background: "#2563eb",
    color: "white",
    fontSize: "1.1rem",
    border: "none",
    borderRadius: 8,
    cursor: "pointer",
  },
  error: { color: "#ef4444", fontSize: "1rem" },
};
