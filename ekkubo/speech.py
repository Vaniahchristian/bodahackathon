"""Speech I/O: Sunbird AI STT/TTS for Luganda + English, with gTTS/Whisper fallbacks."""

from __future__ import annotations

import logging
import mimetypes
import tempfile
from pathlib import Path

import requests

from ekkubo.config import (
    OPENAI_API_KEY,
    SUNBIRD_API_KEY,
    SUNBIRD_API_URL,
    SUNBIRD_STT_LANGUAGE,
    SUNBIRD_TTS_SPEAKER_ID,
    TTS_LANG_FALLBACK,
    TTS_LANG_PRIMARY,
    TTS_MIN_BYTES_PER_CHAR,
    WHISPER_API_URL,
    WHISPER_MODEL,
)

logger = logging.getLogger(__name__)


class SpeechError(Exception):
    """Raised when speech transcription or synthesis fails."""


def _sunbird_headers(*, json: bool = False) -> dict[str, str]:
    if not SUNBIRD_API_KEY:
        raise SpeechError("SUNBIRD_API_KEY not set")
    headers = {"Authorization": f"Bearer {SUNBIRD_API_KEY}"}
    if json:
        headers["Content-Type"] = "application/json"
    return headers


def _audio_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _sunbird_transcribe(audio_path: Path) -> str:
    with audio_path.open("rb") as f:
        resp = requests.post(
            f"{SUNBIRD_API_URL}/tasks/stt",
            headers=_sunbird_headers(),
            files={"audio": (audio_path.name, f, _audio_mime(audio_path))},
            data={
                "language": SUNBIRD_STT_LANGUAGE,
                "adapter": SUNBIRD_STT_LANGUAGE,
                "recognise_speakers": "false",
                "whisper": "true",
            },
            timeout=180,
        )
    if not resp.ok:
        raise SpeechError(f"Sunbird STT failed ({resp.status_code}): {resp.text[:300]}")
    text = (resp.json().get("audio_transcription") or "").strip()
    if not text:
        raise SpeechError("Sunbird STT returned empty transcription")
    logger.info("Sunbird STT: %r", text)
    return text


def _whisper_transcribe(audio_path: Path) -> str:
    if not OPENAI_API_KEY:
        raise SpeechError(
            "No speech API configured. Set SUNBIRD_API_KEY or OPENAI_API_KEY."
        )
    with audio_path.open("rb") as f:
        resp = requests.post(
            WHISPER_API_URL,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (audio_path.name, f)},
            data={"model": WHISPER_MODEL},
            timeout=60,
        )
    resp.raise_for_status()
    text = (resp.json().get("text") or "").strip()
    logger.info("Whisper STT: %r", text)
    return text


def transcribe_audio(audio_path: str | Path) -> str:
    """Transcribe rider speech — Sunbird (Luganda) first, Whisper fallback."""
    path = Path(audio_path)
    if SUNBIRD_API_KEY:
        try:
            return _sunbird_transcribe(path)
        except (SpeechError, requests.RequestException) as exc:
            logger.warning("Sunbird STT failed, trying fallback: %s", exc)
    try:
        return _whisper_transcribe(path)
    except requests.RequestException as exc:
        raise SpeechError(f"Whisper API request failed: {exc}") from exc


def _sunbird_synthesize(text: str, output_path: Path) -> Path:
    resp = requests.post(
        f"{SUNBIRD_API_URL}/tasks/tts",
        headers=_sunbird_headers(json=True),
        json={
            "text": text,
            "speaker_id": SUNBIRD_TTS_SPEAKER_ID,
            "temperature": 0.7,
        },
        timeout=120,
    )
    if not resp.ok:
        raise SpeechError(f"Sunbird TTS failed ({resp.status_code}): {resp.text[:300]}")

    audio_url = resp.json().get("output", {}).get("audio_url")
    if not audio_url:
        raise SpeechError(f"Sunbird TTS missing audio_url: {resp.text[:300]}")

    audio_resp = requests.get(audio_url, timeout=60)
    audio_resp.raise_for_status()
    output_path.write_bytes(audio_resp.content)
    logger.info("Sunbird TTS OK: %d bytes -> %s", len(audio_resp.content), output_path)
    return output_path


def _gtts_synthesize(text: str, output_path: Path) -> Path:
    from gtts import gTTS

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


def synthesize_speech(text: str, output_path: str | Path | None = None) -> Path:
    """Generate spoken Luganda audio — Sunbird TTS first, gTTS fallback."""
    if not text.strip():
        raise ValueError("Cannot synthesize empty text")

    if output_path is None:
        fd, tmp = tempfile.mkstemp(suffix=".mp3")
        import os

        os.close(fd)
        output_path = Path(tmp)
    else:
        output_path = Path(output_path)

    if SUNBIRD_API_KEY:
        try:
            return _sunbird_synthesize(text, output_path)
        except (SpeechError, requests.RequestException) as exc:
            logger.warning("Sunbird TTS failed, using gTTS: %s", exc)

    return _gtts_synthesize(text, output_path)


def translate_to_luganda(text: str, *, source_language: str = "eng", target_language: str = "lug") -> str:
    """Translate navigation text to natural Luganda via Sunbird NLLB."""
    cleaned = text.strip()
    if not cleaned:
        raise SpeechError("Cannot translate empty text")
    if not SUNBIRD_API_KEY:
        raise SpeechError("SUNBIRD_API_KEY not set for translation")

    resp = requests.post(
        f"{SUNBIRD_API_URL}/tasks/translate",
        headers={**_sunbird_headers(json=True), "accept": "application/json"},
        json={
            "source_language": source_language,
            "target_language": target_language,
            "text": cleaned,
        },
        timeout=120,
    )
    if not resp.ok:
        raise SpeechError(f"Sunbird translate failed ({resp.status_code}): {resp.text[:300]}")

    translated = (resp.json().get("output") or {}).get("translated_text", "").strip()
    if not translated:
        raise SpeechError(f"Sunbird translate returned empty text: {resp.text[:300]}")
    logger.info("Sunbird translate: %r -> %r", cleaned, translated)
    return translated


def concatenate_instructions_luganda(instructions: list[dict]) -> str:
    """Build one spoken script from route step Luganda instructions."""
    parts = [i.get("instruction_luganda", "") for i in instructions if i.get("instruction_luganda")]
    return ". ".join(parts)
