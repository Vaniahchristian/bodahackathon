"""Smoke test for hosted Whisper transcription — mocks the HTTP call, no real API key needed."""

from __future__ import annotations

import pytest

from ekkubo import speech


class _FakeResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def test_transcribe_audio_calls_hosted_api(monkeypatch, tmp_path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fake audio")

    captured = {}

    def fake_post(url, headers, files, data, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        return _FakeResponse({"text": "Kisaasi taxi stage"})

    monkeypatch.setattr(speech, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(speech.requests, "post", fake_post)

    text = speech.transcribe_audio(audio)

    assert text == "Kisaasi taxi stage"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["data"]["model"] == speech.WHISPER_MODEL


def test_transcribe_audio_requires_api_key(monkeypatch, tmp_path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fake audio")

    monkeypatch.setattr(speech, "OPENAI_API_KEY", "")

    with pytest.raises(speech.SpeechError):
        speech.transcribe_audio(audio)
