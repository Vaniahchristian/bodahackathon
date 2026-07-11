"""Upload Ekkubo notebook to Kaggle via MCP save_notebook."""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parent.parent / "kaggle" / "ekkubo-notebook.ipynb"


def main() -> None:
    text = NOTEBOOK.read_text(encoding="utf-8")
    payload = {
        "request": {
            "newTitle": "Ekkubo - Eyes-Free Boda Navigation",
            "text": text,
            "language": "python",
            "kernelType": "notebook",
            "isPrivate": True,
            "enableInternet": True,
            "enableGpu": False,
            "kernelExecutionType": "SaveAndRunAll",
            "hasNewTitle": True,
            "hasText": True,
            "hasLanguage": True,
            "hasKernelType": True,
            "hasIsPrivate": True,
            "hasEnableInternet": True,
            "hasEnableGpu": True,
            "hasKernelExecutionType": True,
        }
    }
    out = Path(__file__).resolve().parent / "kaggle_save_payload.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    print(out, "bytes:", out.stat().st_size)


if __name__ == "__main__":
    main()
