from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from studymate.cli import main  # noqa: E402


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if "--config" not in arguments:
        arguments = ["--config", str(PROJECT_ROOT / "config" / "docs_sources.json"), *arguments]
    if "--knowledge" not in arguments:
        arguments = ["--knowledge", str(PROJECT_ROOT / "knowledge"), *arguments]
    sys.argv = [sys.argv[0], "update-docs", *arguments]
    raise SystemExit(main())
