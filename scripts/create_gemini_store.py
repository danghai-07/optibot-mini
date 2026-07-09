"""Create a Gemini File Search store and print its resource name for .env."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Set GEMINI_API_KEY in .env", file=sys.stderr)
        return 1

    display_name = os.getenv("GEMINI_STORE_DISPLAY_NAME", "optibot-mini")
    client = genai.Client(api_key=api_key)
    store = client.file_search_stores.create(
        config={
            "display_name": display_name,
            "embedding_model": "models/gemini-embedding-001",
        }
    )
    print(store.name)
    print(f"\nAdd to .env:\nGEMINI_FILE_SEARCH_STORE={store.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
