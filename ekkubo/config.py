"""Shared configuration for Ekkubo navigation pipeline."""

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_PROJECT_ROOT / ".env")
    except ImportError:
        pass


_load_dotenv()

# --- App identity (required by Nominatim usage policy) ---
APP_NAME = "Ekkubo"
APP_VERSION = "1.0"
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (Kaggle Hackathon; eyes-free boda navigation, Kampala)"

# --- OpenStreetMap endpoints ---
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Kampala bounding box to bias geocoding (south, north, west, east)
KAMPALA_VIEWBOX = (0.25, 0.38, 32.45, 32.75)
KAMPALA_CENTER = (0.3476, 32.5825)

# --- Rate limits ---
NOMINATIM_MIN_INTERVAL_S = 1.0  # max 1 req/sec per Nominatim policy
OVERPASS_MIN_INTERVAL_S = 1.0

# --- Caching ---
CACHE_DIR = Path(os.environ.get("EKKUBO_CACHE_DIR", Path.home() / ".ekkubo_cache"))
CACHE_DB_PATH = CACHE_DIR / "ekkubo_cache.db"
GEOCODE_TTL_S = 7 * 24 * 3600  # 7 days
POI_TTL_S = 24 * 3600  # 1 day

# Coordinate rounding for cache keys (~11 m precision at equator)
COORD_ROUND_DIGITS = 4
POI_SEARCH_RADIUS_M = 100

# --- Gemma 4 via Google Generative Language API ---
# Set GEMINI_API_KEY or GOOGLE_API_KEY in environment / Kaggle secrets.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
GEMMA_MODEL = os.environ.get("EKKUBO_GEMMA_MODEL", "gemma-4-31b-it")
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMMA_MODEL}:generateContent"
)

# --- Speech ---
WHISPER_MODEL = os.environ.get("EKKUBO_WHISPER_MODEL", "base")
TTS_LANG_PRIMARY = "lg"
TTS_LANG_FALLBACK = "en"

# Minimum expected TTS bytes per character (heuristic for broken output)
TTS_MIN_BYTES_PER_CHAR = 0.5
