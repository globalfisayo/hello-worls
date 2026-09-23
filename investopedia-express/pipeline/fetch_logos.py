"""Fetch a logo for every mentioned company.

Two flavours are stored so the app can pick per theme:
  logos/<TICKER>.png       – colour logo (Google favicon service, 256px) – light theme
  logos/mono/<TICKER>.png  – white-on-transparent glyph from nvstly/icons – dark theme
"""
from __future__ import annotations

import sys
import time

import requests

from common import LOGOS, DATA, UA, ensure_dirs, read_json, write_json
import companies as C

NVSTLY = "https://raw.githubusercontent.com/nvstly/icons/main/ticker_icons/{}.png"
FAVICON = "https://www.google.com/s2/favicons?domain={}&sz=256"
CLEARBIT = "https://logo.clearbit.com/{}?size=256"


def get(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": UA})
        if r.status_code == 200 and r.content and len(r.content) > 300 and r.headers.get("content-type", "").startswith("image"):
            return r.content
    except Exception:  # noqa: BLE001
        pass
    return None


def main() -> int:
    ensure_dirs()
    (LOGOS / "mono").mkdir(parents=True, exist_ok=True)
    mentions = read_json(DATA / "mentions.json")
    if not mentions:
        print("mentions.json missing", file=sys.stderr)
        return 1
    info = {t: (n, o) for t, n, a, o in C.ENTRIES}
    report = read_json(DATA / "logos_meta.json", {}) or {}
    for ticker in sorted(mentions["companies"].keys()):
        name, opt = info.get(ticker, (ticker, {}))
        rec = report.get(ticker, {})
        base = ticker.replace(".", "_")
        colour_path = LOGOS / f"{base}.png"
        mono_path = LOGOS / "mono" / f"{base}.png"
        if not colour_path.exists():
            data = None
            domain = opt.get("domain")
            if domain:
                data = get(CLEARBIT.format(domain)) or get(FAVICON.format(domain))
                rec["colour"] = "clearbit" if data and len(data) > 0 else None
                if data is None:
                    rec["colour"] = None
            if data:
                colour_path.write_bytes(data)
                rec["colour"] = rec.get("colour") or "favicon"
        if not mono_path.exists():
            candidates = [ticker, ticker.replace("-", "."), ticker.replace("-", ""), ticker.split(".")[0]]
            data = None
            for c in candidates:
                data = get(NVSTLY.format(c))
                if data:
                    break
            if data:
                mono_path.write_bytes(data)
                rec["mono"] = "nvstly"
        rec["has_colour"] = colour_path.exists()
        rec["has_mono"] = mono_path.exists()
        report[ticker] = rec
        time.sleep(0.15)
    write_json(DATA / "logos_meta.json", report)
    print("logos: colour", sum(1 for r in report.values() if r.get("has_colour")), "mono",
          sum(1 for r in report.values() if r.get("has_mono")), "of", len(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
