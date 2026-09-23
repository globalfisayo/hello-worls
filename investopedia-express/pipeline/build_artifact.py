"""Bundle the app into one self-contained HTML file (data, prices and logos inlined).

Used for publishing a copy as a claude.ai Artifact, whose sandbox blocks all
external requests. Output: dist/express-tracker.html

To stay well under the artifact size limit the bundle packs daily adjusted
closes against one shared trading calendar and inlines 64px logos.
"""
from __future__ import annotations

import base64
import io
import json
import pathlib
import re
import sys

from common import ROOT, DATA, LOGOS, read_json


def small_logo(path: pathlib.Path, size: int = 64) -> str | None:
    if not path or not path.exists():
        return None
    try:
        from PIL import Image
        im = Image.open(path).convert("RGBA")
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
    except Exception:  # noqa: BLE001
        data = path.read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def main() -> int:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    app = read_json(DATA / "app.json")
    raw = {}
    for c in app["companies"]:
        if c.get("priceFile"):
            j = read_json(ROOT / c["priceFile"])
            if j:
                raw[c["t"]] = j
        # colour logo only (dark theme shows it on a white chip); 56px is plenty at card size
        c["logo"] = small_logo(ROOT / c["logo"], 56) if c.get("logo") else (small_logo(ROOT / c["logoMono"], 56) if c.get("logoMono") else None)
        c["logoMono"] = None
    for b, rec in (app.get("benchmarks") or {}).items():
        j = read_json(ROOT / rec["priceFile"])
        if j:
            raw[b] = j
        rec.pop("priceFile", None)

    calendar = sorted({d for j in raw.values() for d in j["d"]})
    index = {d: i for i, d in enumerate(calendar)}
    series = {}
    for t, j in raw.items():
        idx = [index[d] for d in j["d"]]
        rec = {"a": [round(x, 2) for x in j["a"]], "src": j.get("src"), "yf": j.get("yf")}
        if idx == list(range(idx[0], idx[0] + len(idx))):
            rec["d0"], rec["n"] = idx[0], len(idx)
        else:
            rec["i"] = idx
        series[t] = rec
    packed = {"calendar": calendar, "series": series}

    d3 = (ROOT / "vendor" / "d3.min.js").read_text(encoding="utf-8")
    inline = (
        "<script>window.__ARTIFACT__=true;window.__APP__=" + json.dumps(app, separators=(",", ":")).replace("</", "<\\/")
        + ";window.__PRICES__=" + json.dumps(packed, separators=(",", ":")).replace("</", "<\\/") + ";</script>\n"
        "<script>" + d3.replace("</script>", "<\\/script>") + "</script>"
    )
    html = html.replace('<script src="vendor/d3.min.js"></script>', inline)
    html = re.sub(r"^\s*<!doctype html>\s*<html[^>]*>\s*<head>\s*", "", html, flags=re.I)
    html = re.sub(r"\s*</head>\s*<body>\s*", "\n", html, count=1, flags=re.I)
    html = re.sub(r"\s*</body>\s*</html>\s*$", "\n", html, flags=re.I)
    html = re.sub(r'<meta charset="utf-8">\s*<meta name="viewport"[^>]*>\s*', "", html)
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    (out / "express-tracker.html").write_text(html, encoding="utf-8")
    print(f"dist/express-tracker.html: {len(html)/1e6:.2f} MB, {len(series)} price series, {len(app['companies'])} companies, calendar {len(calendar)} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
