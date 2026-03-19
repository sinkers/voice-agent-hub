import {
  ControlBar,
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  useTrackVolume,
  useTracks,
  useMediaDeviceSelect,
} from "@livekit/components-react";
import { useRoomContext } from "@livekit/components-react";
import { Track } from "livekit-client";

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
      console.error("[Call] No agent_id provided in URL");
      setError("No agent_id provided in URL.");
      return;
    }
    console.log("[Call] Initiating connection for agent:", agentId);
    setAgentState("connecting");
    setError("");
    try {
      const res = await fetch("/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId }),
      });
      console.log("[Call] Connect response status:", res.status);
      if (!res.ok) {
        const data = await res.json();
        console.error("[Call] Connection failed:", data);
        throw new Error(data.detail ?? "Failed to connect");
      }
      const data: ConnectResult = await res.json();
      console.log("[Call] Connection successful:", {
        room: data.room_name,
        agent: data.agent,
        url: data.url,
      });
      setConnectResult(data);
    } catch (err) {
      console.error("[Call] Connection error:", err);
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
      onDisconnected={() => {
        console.log("[Call] Disconnected from room");
        setConnectResult(null);
      }}
      onConnected={() => {
        console.log("[Call] Connected to LiveKit room:", connectResult.room_name);
      }}
    >
      <RoomAudioRenderer />
      <MicPublisher />
      <ControlBar controls={{ microphone: true, camera: false, screenShare: false, leave: false }} />
      <MicrophoneSelector />
      <AgentUI
        agentName={connectResult.agent}
        state={agentState}
        onStateChange={setAgentState}
      />
    </LiveKitRoom>
  );
}

/** Explicitly enable the local microphone once inside the LiveKit room. */
function MicPublisher() {
  const room = useRoomContext();
  useEffect(() => {
    console.log("[MicPublisher] Enabling microphone...");
    room.localParticipant.setMicrophoneEnabled(true)
      .then(() => {
        console.log("[MicPublisher] Microphone enabled successfully");
      })
      .catch((err: Error) => {
        console.error("[MicPublisher] Failed to enable microphone:", err);
      });
  }, [room]);
  return null;
}

/** Microphone selector component - shows available mics and allows switching */
function MicrophoneSelector() {
  const {
    devices: audioDevices,
    activeDeviceId: selectedDevice,
    setActiveMediaDevice: setActiveDevice,
  } = useMediaDeviceSelect({ kind: "audioinput" });

  const handleDeviceChange = async (deviceId: string) => {
    console.log("[MicSelector] Switching microphone to:", deviceId);
    try {
      await setActiveDevice(deviceId);
      console.log("[MicSelector] Microphone switched successfully");
    } catch (err) {
      console.error("[MicSelector] Failed to switch microphone:", err);
    }
  };

  // Log available devices
  useEffect(() => {
    if (audioDevices.length > 0) {
      console.log("[MicSelector] Available microphones:", audioDevices.length, audioDevices.map((d) => d.label));
      console.log("[MicSelector] Active microphone:", selectedDevice);
    }
  }, [audioDevices, selectedDevice]);

  // Only show selector if multiple mics available
  if (audioDevices.length <= 1) {
    if (audioDevices.length === 1) {
      console.log("[MicSelector] Only one microphone available, hiding selector");
    }
    return null;
  }

  const currentDevice = audioDevices.find((d) => d.deviceId === selectedDevice);

  return (
    <div style={styles.micSelector}>
      <label style={styles.micLabel}>
        🎤 Microphone: <strong>{currentDevice?.label || "Default"}</strong>
      </label>
      <select
        style={styles.micDropdown}
        value={selectedDevice || ""}
        onChange={(e) => handleDeviceChange(e.target.value)}
      >
        {audioDevices.map((device) => (
          <option key={device.deviceId} value={device.deviceId}>
            {device.label || `Microphone ${device.deviceId.slice(0, 8)}`}
          </option>
        ))}
      </select>
    </div>
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
    const newState = map[vaState] ?? "listening";
    console.log("[AgentUI] Agent state changed:", vaState, "->", newState);
    onStateChange(newState);
  }, [vaState, onStateChange]);

  const color = STATE_COLORS[state];
  const label = STATE_LABELS[state];

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>{agentName}</h1>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
        <div
          style={{
            ...styles.badge,
            background: color,
          }}
        >
          <span style={styles.dot} />
          {label}
        </div>
        {state === "listening" && <AudioLevelIndicator />}
      </div>
      <p style={{ color: "#94a3b8", marginTop: 24, fontSize: "0.9rem" }}>
        {state === "listening" && "Speak now…"}
        {state === "thinking" && "Processing your request…"}
        {state === "speaking" && "Agent is responding…"}
      </p>
    </div>
  );
}

/** Audio level indicator - shows real-time mic input level */
function AudioLevelIndicator() {
  const tracks = useTracks([{ source: Track.Source.Microphone, withPlaceholder: false }]);
  const micTrackRef = tracks.find((t) => t.source === Track.Source.Microphone);

  // Only pass track if it's not a placeholder
  const trackForVolume = micTrackRef && 'publication' in micTrackRef && micTrackRef.publication
    ? micTrackRef
    : undefined;
  const volume = useTrackVolume(trackForVolume);

  useEffect(() => {
    if (volume > 0.1) {
      console.log("[AudioLevel] Volume detected:", volume.toFixed(2));
    }
  }, [volume]);

  // Don't show if no mic track
  if (!micTrackRef || !trackForVolume) {
    return null;
  }

  // Create 5 bars with height based on volume
  const bars = Array.from({ length: 5 }, (_, i) => {
    const threshold = (i + 1) * 0.2;
    const isActive = volume >= threshold;
    return (
      <div
        key={i}
        style={{
          width: 4,
          height: 8 + i * 4,
          background: isActive ? "#22c55e" : "#334155",
          borderRadius: 2,
          transition: "background 0.1s ease",
        }}
      />
    );
  });

  return (
    <div style={styles.audioLevel} title={`Microphone level: ${Math.round(volume * 100)}%`}>
      {bars}
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
  audioLevel: {
    display: "flex",
    gap: 3,
    alignItems: "flex-end",
    height: 24,
    padding: "0 8px",
  },
  micSelector: {
    position: "fixed",
    top: 20,
    right: 20,
    background: "rgba(15, 23, 42, 0.9)",
    padding: "12px 16px",
    borderRadius: 8,
    border: "1px solid #334155",
    display: "flex",
    flexDirection: "column",
    gap: 8,
    minWidth: 250,
  },
  micLabel: {
    fontSize: "0.9rem",
    color: "#94a3b8",
  },
  micDropdown: {
    padding: "8px 12px",
    fontSize: "0.9rem",
    background: "#1e293b",
    color: "white",
    border: "1px solid #475569",
    borderRadius: 6,
    cursor: "pointer",
  },
};
