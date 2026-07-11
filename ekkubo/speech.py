"""Speech I/O: Sunbird AI STT/TTS for Luganda + English, with gTTS/Whisper fallbacks."""

from __future__ import annotations

import logging
import mimetypes
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

from ekkubo.config import (
    OPENAI_API_KEY,
    SUNBIRD_API_KEY,
    SUNBIRD_API_URL,
    SUNBIRD_STT_LANGUAGE,
    SUNBIRD_TTS_LANGUAGE,
    SUNBIRD_TTS_MODEL,
    SUNBIRD_TTS_SPEAKER_ID,
    SUNBIRD_TTS_TEMPERATURE,
    SUNBIRD_TTS_VOICE,
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


_STT_MIME_OVERRIDES: dict[str, str] = {
    ".webm": "audio/webm",
    ".mp4": "audio/mp4",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".aac": "audio/aac",
}


def _audio_mime(path: Path) -> str:
    """MIME type for Sunbird STT — browsers label webm as video/webm, which Sunbird rejects."""
    override = _STT_MIME_OVERRIDES.get(path.suffix.lower())
    if override:
        return override
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed == "video/webm":
        return "audio/webm"
    return guessed or "application/octet-stream"


def normalize_audio_for_stt(audio_path: Path) -> Path:
    """Convert browser webm/ogg recordings to 16 kHz mono WAV for Sunbird STT."""
    if audio_path.suffix.lower() == ".wav":
        return audio_path
    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg not found; sending raw %s to STT", audio_path.suffix)
        return audio_path

    wav_path = audio_path.with_suffix(".wav")
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "wav",
            str(wav_path),
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")[-500:]
        logger.warning("ffmpeg conversion failed (%s): %s", audio_path.suffix, stderr)
        return audio_path
    return wav_path


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
    path = normalize_audio_for_stt(Path(audio_path))
    sunbird_error: Exception | None = None
    if SUNBIRD_API_KEY:
        try:
            return _sunbird_transcribe(path)
        except (SpeechError, requests.RequestException) as exc:
            sunbird_error = exc
            logger.warning("Sunbird STT failed, trying fallback: %s", exc)
    if OPENAI_API_KEY:
        try:
            return _whisper_transcribe(path)
        except requests.RequestException as exc:
            raise SpeechError(f"Whisper API request failed: {exc}") from exc
    if sunbird_error:
        raise SpeechError(str(sunbird_error)) from sunbird_error
    raise SpeechError("No speech API configured. Set SUNBIRD_API_KEY or OPENAI_API_KEY.")


_LUGANDA_ONES = {
    0: "tteeke",
    1: "emu",
    2: "bbiri",
    3: "ssatu",
    4: "nnya",
    5: "ttaano",
    6: "mukaaga",
    7: "musanvu",
    8: "munaana",
    9: "mwenda",
    10: "kkumi",
}
_LUGANDA_TENS = {
    20: "abiri",
    30: "asatu",
    40: "ana",
    50: "ataano",
    60: "nkaaga",
    70: "musanvu",
    80: "munaana",
    90: "kyenda",
}


def _number_to_luganda(n: int) -> str:
    if n <= 10:
        return _LUGANDA_ONES.get(n, str(n))
    if n < 20:
        return f"kkumi ne {_LUGANDA_ONES[n - 10]}"
    if n < 100:
        tens = (n // 10) * 10
        ones = n % 10
        tens_word = _LUGANDA_TENS.get(tens, str(tens))
        if ones == 0:
            return tens_word
        return f"{tens_word} ne {_LUGANDA_ONES[ones]}"
    if n < 1000:
        hundreds = n // 100
        remainder = n % 100
        hundred_word = "kikumi" if hundreds == 1 else f"{_LUGANDA_ONES[hundreds]} kikumi"
        if remainder == 0:
            return hundred_word
        return f"{hundred_word} ne {_number_to_luganda(remainder)}"
    return str(n)


def prepare_luganda_for_tts(text: str) -> str:
    """Shorten and normalize Luganda before TTS for clearer pronunciation."""
    cleaned = text.strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace(";", ".").replace("—", ", ")

    # One short sentence reads more naturally than a long translated paragraph.
    parts = [part.strip() for part in re.split(r"[.!?]", cleaned) if part.strip()]
    if parts:
        cleaned = parts[0]

    cleaned = re.sub(
        r"\b(\d{1,4})\s*(?:m|met(?:er|re)s?)\b",
        lambda match: f"mita {_number_to_luganda(int(match.group(1)))}",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bmita\s+(\d{1,4})\b",
        lambda match: f"mita {_number_to_luganda(int(match.group(1)))}",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(?<!\w)(\d{1,3})(?!\w)",
        lambda match: _number_to_luganda(int(match.group(1))),
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _download_sunbird_audio(audio_url: str, output_path: Path) -> Path:
    audio_resp = requests.get(audio_url, timeout=60)
    audio_resp.raise_for_status()
    output_path.write_bytes(audio_resp.content)
    logger.info("Sunbird TTS OK: %d bytes -> %s", len(audio_resp.content), output_path)
    return output_path


def _sunbird_synthesize_unified(text: str, output_path: Path) -> Path:
    payload: dict[str, str | float] = {
        "text": text,
        "model": SUNBIRD_TTS_MODEL,
        "voice": SUNBIRD_TTS_VOICE,
        "language": SUNBIRD_TTS_LANGUAGE,
    }
    if SUNBIRD_TTS_MODEL == "spark-tts":
        payload["response_mode"] = "url"
        payload["temperature"] = SUNBIRD_TTS_TEMPERATURE

    resp = requests.post(
        f"{SUNBIRD_API_URL}/tasks/audio/speech",
        headers=_sunbird_headers(json=True),
        json=payload,
        timeout=120,
    )
    if not resp.ok:
        raise SpeechError(f"Sunbird TTS failed ({resp.status_code}): {resp.text[:300]}")

    body = resp.json()
    audio_url = body.get("audio_url") or body.get("output", {}).get("audio_url")
    if not audio_url:
        raise SpeechError(f"Sunbird TTS missing audio_url: {resp.text[:300]}")
    return _download_sunbird_audio(audio_url, output_path)


def _sunbird_synthesize_legacy(text: str, output_path: Path) -> Path:
    resp = requests.post(
        f"{SUNBIRD_API_URL}/tasks/tts",
        headers=_sunbird_headers(json=True),
        json={
            "text": text,
            "speaker_id": SUNBIRD_TTS_SPEAKER_ID,
            "temperature": SUNBIRD_TTS_TEMPERATURE,
        },
        timeout=120,
    )
    if not resp.ok:
        raise SpeechError(f"Sunbird legacy TTS failed ({resp.status_code}): {resp.text[:300]}")

    audio_url = resp.json().get("output", {}).get("audio_url")
    if not audio_url:
        raise SpeechError(f"Sunbird legacy TTS missing audio_url: {resp.text[:300]}")
    return _download_sunbird_audio(audio_url, output_path)


def _sunbird_synthesize(text: str, output_path: Path) -> Path:
    prepared = prepare_luganda_for_tts(text)
    try:
        return _sunbird_synthesize_unified(prepared, output_path)
    except (SpeechError, requests.RequestException) as exc:
        logger.warning("Sunbird unified TTS failed, trying legacy endpoint: %s", exc)
        return _sunbird_synthesize_legacy(prepared, output_path)


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


def translate_batch_to_luganda(texts: list[str]) -> list[str]:
    """Translate multiple navigation lines in one Sunbird call when possible."""
    results = [""] * len(texts)
    pending: list[tuple[int, str]] = []
    for index, text in enumerate(texts):
        cleaned = text.strip()
        if cleaned:
            pending.append((index, cleaned))

    if not pending:
        return results

    if len(pending) == 1:
        index, cleaned = pending[0]
        results[index] = translate_to_luganda(cleaned)
        return results

    batch = "\n\n".join(text for _, text in pending)
    try:
        translated = translate_to_luganda(batch)
    except (SpeechError, requests.RequestException):
        for index, cleaned in pending:
            try:
                results[index] = translate_to_luganda(cleaned)
            except (SpeechError, requests.RequestException) as exc:
                logger.warning("Per-step Sunbird translate failed: %s", exc)
        return results

    parts = [part.strip() for part in translated.split("\n\n") if part.strip()]
    if len(parts) == len(pending):
        for (index, _), part in zip(pending, parts):
            results[index] = part
        return results

    logger.warning(
        "Batch translate split mismatch (%d parts for %d steps); retrying per step",
        len(parts),
        len(pending),
    )
    for index, cleaned in pending:
        try:
            results[index] = translate_to_luganda(cleaned)
        except (SpeechError, requests.RequestException) as exc:
            logger.warning("Per-step Sunbird translate failed: %s", exc)
    return results


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


def first_instruction_luganda(instructions: list[dict]) -> str:
    """Return the first step's Luganda instruction, prepared for TTS."""
    for item in instructions:
        lug = (item.get("instruction_luganda") or "").strip()
        if lug:
            return prepare_luganda_for_tts(lug)
    return ""


def concatenate_instructions_luganda(instructions: list[dict]) -> str:
    """Build one spoken script from route step Luganda instructions."""
    parts = [
        prepare_luganda_for_tts(i.get("instruction_luganda", ""))
        for i in instructions
        if i.get("instruction_luganda")
    ]
    return ". ".join(parts)
