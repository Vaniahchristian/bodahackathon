"use client";

import { useRef, useState } from "react";
import { Microphone, Stop } from "@phosphor-icons/react";

function logMic(event: string, detail?: unknown) {
  const ts = new Date().toISOString().slice(11, 23);
  if (detail === undefined) {
    console.log(`[Ekkubo mic ${ts}] ${event}`);
  } else {
    console.log(`[Ekkubo mic ${ts}] ${event}`, detail);
  }
}

export function RecordButton({
  apiUrl,
  onTranscribed,
  onError,
  onBusyChange,
}: {
  apiUrl: string;
  onTranscribed: (text: string) => void;
  onError: (message: string) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  async function transcribeBlob(blob: Blob) {
    const started = performance.now();
    logMic("transcribe started", { bytes: blob.size, type: blob.type });
    setTranscribing(true);
    onBusyChange(true);
    try {
      const form = new FormData();
      form.append("file", blob, "recording.webm");
      const res = await fetch(`${apiUrl}/api/transcribe`, { method: "POST", body: form });
      const data = await res.json();
      logMic("transcribe response", {
        elapsedMs: Math.round(performance.now() - started),
        ok: res.ok,
        status: res.status,
        text: data.text,
      });
      if (!res.ok) throw new Error(data.detail || "Transcription failed");
      onTranscribed(data.text);
    } catch (err) {
      logMic("transcribe failed", {
        elapsedMs: Math.round(performance.now() - started),
        error: err,
      });
      onError(err instanceof Error ? err.message : "Transcription failed");
    } finally {
      setTranscribing(false);
      onBusyChange(false);
    }
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        transcribeBlob(new Blob(chunksRef.current, { type: recorder.mimeType }));
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      onError("Microphone access denied or unavailable.");
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  return (
    <button
      type="button"
      onClick={recording ? stopRecording : startRecording}
      disabled={transcribing}
      aria-pressed={recording}
      aria-label={recording ? "Stop recording" : "Speak destination"}
      className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-border bg-background text-accent transition-[transform,background-color] duration-200 ease-out disabled:opacity-50 active:scale-[0.96] data-[recording=true]:bg-accent data-[recording=true]:text-accent-foreground"
      data-recording={recording}
      style={recording ? { animation: "pulse-ring 1.4s cubic-bezier(0.16,1,0.3,1) infinite" } : undefined}
    >
      {recording ? <Stop size={20} weight="fill" /> : <Microphone size={20} weight="bold" />}
    </button>
  );
}
