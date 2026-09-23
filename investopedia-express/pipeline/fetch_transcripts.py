"""Fetch full-text transcripts for each episode when a source is available.

Writes data/transcripts/<episode id>.txt and data/transcripts_index.json.
The source list is filled in once the probe run identifies a working provider.
"""
from __future__ import annotations

import sys

from common import DATA, read_json, write_json


def main() -> int:
    idx = read_json(DATA / "transcripts_index.json", {"sources": {}, "episodes": {}}) or {}
    print(f"transcripts on disk: {len(idx.get('episodes', {}))}")
    write_json(DATA / "transcripts_index.json", idx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
