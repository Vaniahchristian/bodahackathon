"""Speech I/O: Whisper STT and gTTS with Luganda fallback."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from ekkubo.config import TTS_LANG_FALLBACK, TTS_LANG_PRIMARY, TTS_MIN_BYTES_PER_CHAR, WHISPER_MODEL

logger = logging.getLogger(__name__)

_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper

        logger.info("Loading Whisper model: %s", WHISPER_MODEL)
        _whisper_model = whisper.load_model(WHISPER_MODEL)
    return _whisper_model


def transcribe_audio(audio_path: str | Path) -> str:
    """Transcribe rider speech with Whisper."""
    model = _get_whisper()
    result = model.transcribe(str(audio_path), fp16=False)
    text = (result.get("text") or "").strip()
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
