#!/usr/bin/env python3
"""Verify a generated 64×64 POC skin without loading model weights."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from app.validation import validate_classic_skin


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: scripts/verify-artifact.py path/to/skin.png", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    with Image.open(path) as image:
        result = validate_classic_skin(image)
    print(f"{path.name}: {result.status}")
    for warning in result.warnings:
        print(f"- {warning}")
    return 0 if result.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
