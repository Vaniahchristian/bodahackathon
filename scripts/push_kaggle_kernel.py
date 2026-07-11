"""Push Ekkubo notebook to Kaggle using KAGGLE_API_TOKEN (no token printed)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE_DIR = ROOT / "kaggle"
TOKEN_FILE = ROOT / ".kaggle_token"


def main() -> int:
    if not TOKEN_FILE.exists():
        print("Missing .kaggle_token file", file=sys.stderr)
        return 1

    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token.startswith("KGAT_"):
        print("Invalid Kaggle token format in .kaggle_token", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["KAGGLE_API_TOKEN"] = token

    subprocess.check_call(
        [sys.executable, str(ROOT / "scripts" / "setup_kaggle_auth.py")],
        env=env,
        cwd=str(ROOT),
    )
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "kaggle"], env=env)

    # Resolve username for kernel-metadata id
    from kaggle import KaggleApi

    api = KaggleApi()
    api.authenticate()
    username = api.get_config_value("username")
    if not username:
        # KGAT-only auth: fetch via API
        import requests

        resp = requests.get(
            "https://www.kaggle.com/api/v1/account/profile",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        username = resp.json().get("userName") or resp.json().get("username")

    meta_path = KAGGLE_DIR / "kernel-metadata.json"
    import json

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    slug = "ekkubo-eyes-free-boda-navigation"
    meta["id"] = f"{username}/{slug}"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Pushing notebook as {meta['id']} ...")
    subprocess.check_call(
        [sys.executable, "-m", "kaggle", "kernels", "push", "-p", str(KAGGLE_DIR)],
        env=env,
        cwd=str(ROOT),
    )

    print(f"https://www.kaggle.com/code/{username}/{slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
