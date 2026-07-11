"""Build Kaggle notebook JSON for Ekkubo upload via MCP save_notebook."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EKKUBO = ROOT / "ekkubo"

FILES = [
    "__init__.py",
    "config.py",
    "cache.py",
    "geocoding.py",
    "routing.py",
    "landmarks.py",
    "gemma_nav.py",
    "speech.py",
    "pipeline.py",
    "app.py",
]


def cell_md(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.splitlines(keepends=True) or [source],
    }


def cell_code(source: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "source": source.splitlines(keepends=True) or [source],
        "outputs": [],
        "execution_count": None,
    }


def main() -> None:
    write_files_code = [
        "from pathlib import Path",
        "import os",
        "",
        "ROOT = Path('/kaggle/working')",
        "pkg = ROOT / 'ekkubo'",
        "pkg.mkdir(parents=True, exist_ok=True)",
        "(ROOT / 'ekkubo' / '__init__.py').write_text('\"\"\"Ekkubo navigation.\"\"\"\\n', encoding='utf-8')",
        "PLACEHOLDER_FILES",
        "for name, content in FILES.items():",
        "    path = pkg / name",
        "    path.write_text(content, encoding='utf-8')",
        "    print('wrote', path)",
        "",
        "import sys",
        "if str(ROOT) not in sys.path:",
        "    sys.path.insert(0, str(ROOT))",
    ]

    files_dict = {}
    for name in FILES:
        if name == "__init__.py":
            files_dict[name] = '"""Ekkubo navigation."""\n'
        else:
            files_dict[name] = (EKKUBO / name).read_text(encoding="utf-8")

    idx = write_files_code.index("PLACEHOLDER_FILES")
    write_files_code[idx] = f"FILES = {json.dumps(files_dict)}"

    smoke_test = '''
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
sys.path.insert(0, "/kaggle/working")


def _ensure_gemini_key() -> bool:
    """Load GEMINI_API_KEY from env or Kaggle Secrets. Returns True if set."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        print("GEMINI_API_KEY: loaded from environment")
        return True
    try:
        from kaggle_secrets import UserSecretsClient

        os.environ["GEMINI_API_KEY"] = UserSecretsClient().get_secret("GEMINI_API_KEY")
        print("GEMINI_API_KEY: loaded from Kaggle Secrets")
        return True
    except Exception as exc:
        print("WARNING: could not load GEMINI_API_KEY:", type(exc).__name__, exc)
        print(
            "Saved-version runs need the secret toggled ON *before* Save Version. "
            "For full Gemma output: Edit session → Secrets ON → Run All."
        )
        return False


has_key = _ensure_gemini_key()

from ekkubo.pipeline import navigate, PipelineStatus

statuses = []

def on_status(s):
    statuses.append(s)
    print("status:", s)

print("Running live pipeline: Makerere -> Kisaasi")
result = navigate(
    "Makerere University, Kampala",
    "Kisaasi, Kampala",
    on_status=on_status,
    generate_audio=has_key,
)

print("\\n=== RESULT ===")
print("status:", result.status)
print("message:", result.message)
for i, step in enumerate(result.instructions[:5], 1):
    print(f"\\nStep {i} ({step.get('distance_m')}m)")
    print("  landmark:", step.get("chosen_landmark"))
    print("  LG:", step.get("instruction_luganda"))
    print("  EN:", step.get("instruction_english"))
if len(result.instructions) > 5:
    print(f"... +{len(result.instructions) - 5} more steps")
if result.audio_path:
    print("\\nAudio:", result.audio_path)
'''

    gradio_cell = '''
import os
import sys

sys.path.insert(0, "/kaggle/working")

# Batch/saved-version runs cannot host Gradio — interactive Edit session only.
if os.environ.get("KAGGLE_KERNEL_RUN_TYPE", "").lower() == "batch":
    print("Skipping Gradio (batch run). Open Edit session and run this cell for the UI demo.")
else:
    from ekkubo.app import build_app

    app = build_app()
    app.launch(server_name="0.0.0.0", server_port=7860, debug=True, share=False)
'''

    cells = [
        cell_md(
            "# Ekkubo — Eyes-Free Boda Navigation (Kampala)\n\n"
            "Live OSM pipeline + Gemma 4 landmark disambiguation.\n\n"
            "**Setup:** Add-ons → Secrets → `GEMINI_API_KEY` (Google AI Studio) → **toggle ON**.\n\n"
            "**Important:** Toggle the secret ON *before* saving a version. Saved-version "
            "batch runs cannot read secrets added afterward. For the Gradio UI, use "
            "**Edit** session and run the last cell manually.\n"
        ),
        cell_code("!pip install -q requests gradio gTTS python-dotenv"),
        cell_code("\n".join(write_files_code)),
        cell_code(smoke_test.strip()),
        cell_md("## Interactive demo (run cell below manually — Gradio blocks the kernel)"),
        cell_code(gradio_cell.strip()),
    ]

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "cells": cells,
    }

    out = ROOT / "kaggle" / "ekkubo-notebook.ipynb"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(nb), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
