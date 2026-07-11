"""Write Kaggle KGAT token to the CLI access_token file (no token printed)."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / ".kaggle_token"
KAGGLE_DIR = Path.home() / ".kaggle"
ACCESS_TOKEN = KAGGLE_DIR / "access_token"


def main() -> int:
    if not TOKEN_FILE.exists():
        print("Missing .kaggle_token", file=sys.stderr)
        return 1

    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token.startswith("KGAT_"):
        print("Invalid token format in .kaggle_token", file=sys.stderr)
        return 1

    KAGGLE_DIR.mkdir(parents=True, exist_ok=True)
    ACCESS_TOKEN.write_text(token + "\n", encoding="utf-8")
    print(f"Wrote {ACCESS_TOKEN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
