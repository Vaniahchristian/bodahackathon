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

function logNav(event: string, detail?: unknown) {
  const ts = new Date().toISOString().slice(11, 23);
  if (detail === undefined) {
    console.log(`[Ekkubo ${ts}] ${event}`);
  } else {
    console.log(`[Ekkubo ${ts}] ${event}`, detail);
  }
}

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
  journey_speech_text: string | null;
  audio_url: string | null;
};

export default function Home() {
  const [origin, setOrigin] = useState("Makerere University, Kampala");
  const [destination, setDestination] = useState("");
  const [loading, setLoading] = useState(false);
  const [micBusy, setMicBusy] = useState(false);
  const [result, setResult] = useState<NavigateResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    logNav("app ready", { apiUrl: API_URL });
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    const payload = { origin, destination, generate_audio: false };
    const url = `${API_URL}/api/navigate`;
    const started = performance.now();
    const heartbeat = window.setInterval(() => {
      logNav("navigate still waiting", {
        elapsedMs: Math.round(performance.now() - started),
        url,
      });
    }, 5000);

    logNav("navigate started", { url, payload });

    try {
      logNav("navigate fetch sending");
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      logNav("navigate fetch returned", {
        elapsedMs: Math.round(performance.now() - started),
        ok: res.ok,
        status: res.status,
        statusText: res.statusText,
      });

      const raw = await res.text();
      logNav("navigate response body received", {
        elapsedMs: Math.round(performance.now() - started),
        bytes: raw.length,
        preview: raw.slice(0, 200),
      });

      let data: NavigateResponse;
      try {
        data = JSON.parse(raw) as NavigateResponse;
      } catch (parseErr) {
        logNav("navigate json parse failed", parseErr);
        throw new Error("Invalid JSON from navigation API");
      }

      logNav("navigate parsed", {
        elapsedMs: Math.round(performance.now() - started),
        status: data.status,
        message: data.message,
        stepCount: data.instructions?.length ?? 0,
        hasJourneySpeech: Boolean(data.journey_speech_text),
        hasAudioUrl: Boolean(data.audio_url),
      });

      if (!res.ok) throw new Error(data.message || "Navigation failed");
      setResult(data);
      logNav("navigate complete");
    } catch (err) {
      logNav("navigate failed", {
        elapsedMs: Math.round(performance.now() - started),
        error: err,
      });
      setError(err instanceof Error ? err.message : "Navigation failed");
    } finally {
      window.clearInterval(heartbeat);
      setLoading(false);
      logNav("navigate finished", { elapsedMs: Math.round(performance.now() - started) });
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

      {result.journey_speech_text && <JourneyAudio text={result.journey_speech_text} />}
      {!result.journey_speech_text && result.audio_url && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Full journey (Luganda)
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

function JourneyAudio({ text }: { text: string }) {
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadAudio() {
      const started = performance.now();
      logNav("journey audio started", { chars: text.length });
      setLoading(true);
      setAudioUrl(null);
      try {
        const res = await fetch(`${API_URL}/api/speak`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, journey: true }),
        });
        const data = await res.json();
        logNav("journey audio response", {
          elapsedMs: Math.round(performance.now() - started),
          ok: res.ok,
          status: res.status,
          audioUrl: data.audio_url,
        });
        if (!res.ok) throw new Error(data.detail || "Speech failed");
        if (!cancelled) setAudioUrl(`${API_URL}${data.audio_url}`);
      } catch (err) {
        logNav("journey audio failed", {
          elapsedMs: Math.round(performance.now() - started),
          error: err,
        });
        if (!cancelled) setAudioUrl(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadAudio();
    return () => {
      cancelled = true;
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, [text]);

  useEffect(() => {
    if (!audioUrl) return;
    const audio = new Audio(audioUrl);
    audioRef.current = audio;
    void audio.play().catch(() => undefined);
    return () => {
      audio.pause();
    };
  }, [audioUrl]);

  return (
    <div className="mt-4">
      <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Full journey (Luganda)
      </p>
      {loading && <p className="text-sm text-muted-foreground">Generating audio…</p>}
      {!loading && audioUrl && (
        <audio
          controls
          src={audioUrl}
          className="w-full"
          style={{ accentColor: "var(--color-accent)" }}
        />
      )}
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
