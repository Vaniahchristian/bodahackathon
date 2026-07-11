"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Instruction = {
  distance_m?: number;
  chosen_landmark?: string | null;
  instruction_english?: string;
  instruction_luganda?: string;
};

type NavigateResponse = {
  status: string;
  message: string;
  clarifying_question: string | null;
  instructions: Instruction[];
  audio_url: string | null;
};

export default function Home() {
  const [origin, setOrigin] = useState("Makerere University, Kampala");
  const [destination, setDestination] = useState("");
  const [loading, setLoading] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [result, setResult] = useState<NavigateResponse | null>(null);
  const [error, setError] = useState("");

  async function handleMicChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setTranscribing(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_URL}/api/transcribe`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Transcription failed");
      setDestination(data.text);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Transcription failed");
    } finally {
      setTranscribing(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/api/navigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin, destination, generate_audio: true }),
      });
      const data: NavigateResponse = await res.json();
      if (!res.ok) throw new Error(data.message || "Navigation failed");
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Navigation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: 24, fontFamily: "sans-serif" }}>
      <h1>Ekkubo</h1>
      <p>Eyes-free boda navigation for Kampala.</p>

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label>
          Starting point
          <input value={origin} onChange={(e) => setOrigin(e.target.value)} required />
        </label>

        <label>
          Destination
          <input
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="e.g. Kisaasi, Kampala"
            required
          />
        </label>

        <label>
          Or speak destination
          <input type="file" accept="audio/*" capture onChange={handleMicChange} disabled={transcribing} />
        </label>
        {transcribing && <p>Transcribing…</p>}

        <button type="submit" disabled={loading}>
          {loading ? "Finding route…" : "Get directions"}
        </button>
      </form>

      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {result?.status === "clarify" && (
        <p>
          <strong>Need clarification:</strong> {result.clarifying_question}
        </p>
      )}

      {result?.status === "done" && (
        <section>
          <p>{result.message}</p>
          <ol>
            {result.instructions.map((step, i) => (
              <li key={i}>
                <strong>{step.chosen_landmark || "(no landmark)"}</strong> — {step.instruction_english}
                <br />
                <em>{step.instruction_luganda}</em>
              </li>
            ))}
          </ol>
          {result.audio_url && <audio controls src={`${API_URL}${result.audio_url}`} />}
        </section>
      )}
    </main>
  );
}
