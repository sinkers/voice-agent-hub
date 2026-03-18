import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

type Stage = "form" | "waiting" | "connected" | "error";

export default function Verify() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code") ?? "";

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [stage, setStage] = useState<Stage>("form");
  const [formError, setFormError] = useState("");
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll until the agent picks up the token
  const startPolling = useCallback(() => {
    const deadline = Date.now() + 5 * 60 * 1000; // 5 min
    pollRef.current = setInterval(async () => {
      if (Date.now() > deadline) {
        clearInterval(pollRef.current!);
        setStage("error");
        return;
      }
      try {
        const res = await fetch(`/auth/device/token?code=${encodeURIComponent(code)}`);
        if (!res.ok) { clearInterval(pollRef.current!); setStage("error"); return; }
        const data = await res.json();
        // Token present = agent has collected it
        if (data.token) {
          clearInterval(pollRef.current!);
          setStage("connected");
        }
      } catch {
        // network blip — keep polling
      }
    }, 2000);
  }, [code]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    setLoading(true);
    try {
      const res = await fetch("/auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, name, email }),
      });
      if (res.ok) {
        setStage("waiting");
        startPolling();
      } else {
        const data = await res.json();
        setFormError(data.detail ?? "Failed to approve connection.");
      }
    } catch {
      setFormError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>Connect Voice Agent</h1>

      {stage === "form" && (
        <>
          <p style={styles.label}>Your device code:</p>
          <div style={styles.code}>{code || "—"}</div>
          <p style={styles.label}>Enter your details to approve this connection:</p>
          <form onSubmit={handleSubmit} style={styles.form}>
            <input
              style={styles.input}
              type="text"
              placeholder="Your name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <input
              style={styles.input}
              type="email"
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <button style={styles.button} type="submit" disabled={loading}>
              {loading ? "Approving…" : "Approve Connection"}
            </button>
          </form>
          {formError && <p style={styles.error}>{formError}</p>}
        </>
      )}

      {stage === "waiting" && (
        <div style={styles.waiting}>
          <div style={styles.spinner} />
          <p>Waiting for agent to connect…</p>
          <p style={styles.hint}>This usually takes a few seconds.</p>
        </div>
      )}

      {stage === "connected" && (
        <p style={styles.success}>
          ✅ Agent connected. You can close this tab.
        </p>
      )}

      {stage === "error" && (
        <p style={styles.error}>
          Agent did not connect in time. Please restart the agent and try again.
        </p>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    fontFamily: "system-ui, sans-serif",
    maxWidth: 480,
    margin: "80px auto",
    padding: "0 20px",
  },
  title: { fontSize: "1.5rem" },
  label: { marginBottom: 4 },
  code: {
    fontSize: "2rem",
    fontWeight: "bold",
    letterSpacing: "0.2em",
    background: "#f0f0f0",
    padding: "12px 24px",
    borderRadius: 8,
    display: "inline-block",
    margin: "16px 0",
    wordBreak: "break-all",
  },
  form: { display: "flex", flexDirection: "column", gap: 8, marginTop: 12 },
  input: {
    padding: "10px",
    fontSize: "1rem",
    border: "1px solid #ccc",
    borderRadius: 6,
  },
  button: {
    padding: "12px",
    background: "#2563eb",
    color: "white",
    fontSize: "1rem",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
  },
  waiting: { textAlign: "center", marginTop: 32, color: "#555" },
  spinner: {
    width: 40,
    height: 40,
    border: "4px solid #e5e7eb",
    borderTop: "4px solid #2563eb",
    borderRadius: "50%",
    animation: "spin 1s linear infinite",
    margin: "0 auto 16px",
  },
  hint: { fontSize: "0.85rem", color: "#888" },
  success: { color: "green", fontWeight: "bold", fontSize: "1.1rem" },
  error: { color: "red", marginTop: 12 },
};
