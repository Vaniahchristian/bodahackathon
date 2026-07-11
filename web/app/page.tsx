"use client";

import { useEffect, useRef, useState } from "react";
import {
  ChatCircleDots,
  NavigationArrow,
  SpeakerHigh,
  WarningCircle,
} from "@phosphor-icons/react";
import { RecordButton } from "./record-button";

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
  const [micBusy, setMicBusy] = useState(false);
  const [result, setResult] = useState<NavigateResponse | null>(null);
  const [error, setError] = useState("");

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
    <main className="mx-auto min-h-dvh max-w-6xl px-5 py-10 md:px-10 md:py-14">
      <header className="mb-10 flex items-center gap-3 md:mb-14">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <NavigationArrow size={18} weight="fill" />
        </span>
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Ekkubo</h1>
          <p className="text-sm text-muted-foreground">Eyes-free boda navigation for Kampala</p>
        </div>
      </header>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,22rem)_1fr] lg:gap-16">
        <section aria-label="Plan your route">
          <p className="mb-5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Plan your route
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">Starting point</span>
              <input
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
                required
                className="rounded-xl border border-border bg-background px-3.5 py-3 text-sm outline-none transition-colors focus:border-accent"
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">Destination</span>
              <div className="flex gap-2">
                <input
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  placeholder="e.g. Kisaasi, Kampala"
                  required
                  className="min-w-0 flex-1 rounded-xl border border-border bg-background px-3.5 py-3 text-sm outline-none transition-colors focus:border-accent"
                />
                <RecordButton
                  apiUrl={API_URL}
                  onTranscribed={setDestination}
                  onError={setError}
                  onBusyChange={setMicBusy}
                />
              </div>
              {micBusy && <span className="text-xs text-muted-foreground">Transcribing…</span>}
            </label>

            <button
              type="submit"
              disabled={loading}
              className="mt-1 rounded-xl bg-accent px-4 py-3.5 text-sm font-medium tracking-tight text-accent-foreground transition-[transform,opacity] duration-150 ease-out active:scale-[0.98] disabled:opacity-50"
            >
              {loading ? "Finding route…" : "Get directions"}
            </button>
          </form>
        </section>

        <section aria-label="Route results" className="min-w-0">
          {!result && !loading && !error && <EmptyState />}
          {loading && <LoadingState />}

          {error && (
            <StatusBlock icon={<WarningCircle size={20} weight="bold" />} tone="error" title="Something went wrong">
              {error}
            </StatusBlock>
          )}

          {result?.status === "clarify" && (
            <StatusBlock icon={<ChatCircleDots size={20} weight="bold" />} tone="accent" title="Need a bit more detail">
              {result.clarifying_question}
            </StatusBlock>
          )}

          {result?.status === "done" && <ResultView result={result} />}
        </section>
      </div>
    </main>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col gap-2 border-t border-border pt-6 text-sm text-muted-foreground">
      <NavigationArrow size={22} weight="light" className="text-muted-foreground/70" />
      <p>Your route will appear here, with spoken Luganda directions once you search.</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex flex-col gap-3 border-t border-border pt-6">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-14 animate-pulse rounded-lg bg-muted"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}

function StatusBlock({
  icon,
  tone,
  title,
  children,
}: {
  icon: React.ReactNode;
  tone: "error" | "accent";
  title: string;
  children: React.ReactNode;
}) {
  const toneClass = tone === "error" ? "border-error bg-error-soft text-error" : "border-accent bg-accent-soft text-accent";
  return (
    <div className={`flex gap-3 rounded-xl border-t-2 p-4 ${toneClass}`} style={{ animation: "rise-in 0.35s cubic-bezier(0.16,1,0.3,1)" }}>
      <div className="mt-0.5 shrink-0">{icon}</div>
      <div className="text-sm text-foreground">
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 text-muted-foreground">{children}</p>
      </div>
    </div>
  );
}

function ResultView({ result }: { result: NavigateResponse }) {
  return (
    <div className="border-t border-border pt-6" style={{ animation: "rise-in 0.4s cubic-bezier(0.16,1,0.3,1)" }}>
      <p className="text-sm text-muted-foreground">{result.message}</p>

      {result.audio_url && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Next direction (Luganda)
          </p>
          <audio
            controls
            autoPlay
            src={`${API_URL}${result.audio_url}`}
            className="w-full"
            style={{ accentColor: "var(--color-accent)" }}
          />
        </div>
      )}

      <ol className="mt-6 divide-y divide-border">
        {result.instructions.map((step, i) => (
          <li key={i} className="flex gap-4 py-4">
            <span className="w-14 shrink-0 font-mono text-xs text-muted-foreground">
              {step.distance_m != null ? `${step.distance_m} m` : ""}
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-medium">{step.chosen_landmark || "No landmark, follow the road"}</p>
              <p className="mt-0.5 text-sm text-accent">{step.instruction_luganda}</p>
              <p className="mt-0.5 text-sm text-muted-foreground">{step.instruction_english}</p>
            </div>
            {step.instruction_luganda && (
              <SpeakButton text={step.instruction_luganda} />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function SpeakButton({ text }: { text: string }) {
  const [busy, setBusy] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, []);

  async function handleSpeak() {
    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/api/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Speech failed");

      audioRef.current?.pause();
      const audio = new Audio(`${API_URL}${data.audio_url}`);
      audioRef.current = audio;
      await audio.play();
    } catch {
      // Keep the step list usable even if one TTS request fails.
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleSpeak}
      disabled={busy}
      aria-label="Play Luganda direction"
      className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
    >
      <SpeakerHigh size={16} weight="fill" />
    </button>
  );
}
