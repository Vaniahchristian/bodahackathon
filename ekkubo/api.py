"""FastAPI wrapper around the navigation pipeline — backend for a JS frontend."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ekkubo.pipeline import navigate
from ekkubo.speech import SpeechError, transcribe_audio

app = FastAPI(title="Ekkubo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # ponytail: Next.js dev origin only, add prod domain on deploy
    allow_methods=["*"],
    allow_headers=["*"],
)


class NavigateRequest(BaseModel):
    origin: str
    destination: str
    generate_audio: bool = True


@app.post("/api/navigate")
def navigate_endpoint(req: NavigateRequest) -> dict:
    result = navigate(req.origin, req.destination, generate_audio=req.generate_audio)
    return {
        "status": result.status.value,
        "message": result.message,
        "clarifying_question": result.clarifying_question,
        "origin": asdict(result.origin) if result.origin else None,
        "destination": asdict(result.destination) if result.destination else None,
        "route": asdict(result.route) if result.route else None,
        "instructions": result.instructions,
        "audio_url": f"/api/audio/{Path(result.audio_path).name}" if result.audio_path else None,
    }


@app.post("/api/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "audio").suffix or ".wav"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with open(fd, "wb") as out:
            shutil.copyfileobj(file.file, out)
        text = transcribe_audio(tmp_path)
    except SpeechError as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return {"text": text}


@app.get("/api/audio/{filename}")
def get_audio(filename: str) -> FileResponse:
    path = Path(tempfile.gettempdir()) / filename
    if not path.exists():
        raise HTTPException(404, "Audio not found")
    return FileResponse(path, media_type="audio/mpeg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
