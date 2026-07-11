"""Speech I/O: hosted Whisper STT (OpenAI API) and gTTS with Luganda fallback."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import requests

from ekkubo.config import (
    OPENAI_API_KEY,
    TTS_LANG_FALLBACK,
    TTS_LANG_PRIMARY,
    TTS_MIN_BYTES_PER_CHAR,
    WHISPER_API_URL,
    WHISPER_MODEL,
)

logger = logging.getLogger(__name__)


class SpeechError(Exception):
    """Raised when hosted Whisper transcription fails."""


def transcribe_audio(audio_path: str | Path) -> str:
    """Transcribe rider speech via the hosted Whisper API (no local model/torch)."""
    if not OPENAI_API_KEY:
        raise SpeechError(
            "OPENAI_API_KEY not set. Get one at https://platform.openai.com/api-keys"
        )

    path = Path(audio_path)
    try:
        with open(path, "rb") as f:
            resp = requests.post(
                WHISPER_API_URL,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": (path.name, f)},
                data={"model": WHISPER_MODEL},
                timeout=60,
            )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise SpeechError(f"Whisper API request failed: {exc}") from exc

    text = (resp.json().get("text") or "").strip()
    logger.info("Whisper transcription: %r", text)
    return text


def synthesize_speech(text: str, output_path: str | Path | None = None) -> Path:
    """
    Generate spoken audio with gTTS (Luganda primary, English fallback per phrase).

    Returns path to MP3 file.
    """
    from gtts import gTTS

    if not text.strip():
        raise ValueError("Cannot synthesize empty text")

    if output_path is None:
        fd, tmp = tempfile.mkstemp(suffix=".mp3")
        import os

        os.close(fd)
        output_path = Path(tmp)
    else:
        output_path = Path(output_path)

    lang = TTS_LANG_PRIMARY
    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(str(output_path))
        size = output_path.stat().st_size
        min_expected = int(len(text) * TTS_MIN_BYTES_PER_CHAR)
        if size < min_expected:
            raise RuntimeError(
                f"gTTS output suspiciously small ({size} bytes for {len(text)} chars)"
            )
        logger.info("gTTS (%s) OK: %d bytes", lang, size)
    except Exception as exc:
        logger.warning("gTTS %s failed (%s), falling back to %s", lang, exc, TTS_LANG_FALLBACK)
        tts = gTTS(text=text, lang=TTS_LANG_FALLBACK)
        tts.save(str(output_path))

    return output_path


def concatenate_instructions_luganda(instructions: list[dict]) -> str:
    """Build one spoken script from route step Luganda instructions."""
    parts = [i.get("instruction_luganda", "") for i in instructions if i.get("instruction_luganda")]
    return ". ".join(parts)
