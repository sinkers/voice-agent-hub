import { FormEvent, useState } from "react";

export default function Verify() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code") ?? "";

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, name, email }),
      });
      if (res.ok) {
        setDone(true);
      } else {
        const data = await res.json();
        setError(data.detail ?? "Failed to approve connection.");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>Connect Voice Agent</h1>
      {done ? (
        <p style={styles.success}>
          You are now connected. You can close this tab.
        </p>
      ) : (
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
          {error && <p style={styles.error}>{error}</p>}
        </>
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
  success: { color: "green", fontWeight: "bold", fontSize: "1.1rem" },
  error: { color: "red", marginTop: 12 },
};
