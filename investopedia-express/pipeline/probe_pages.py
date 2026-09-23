"""Probe where transcripts for the show might live. Saves raw HTML for
inspection plus a JSON report. Only run on demand (mode=probe)."""
from __future__ import annotations

import json
import re
import subprocess
import sys

import requests

from common import RAW, DATA, UA, ensure_dirs, read_json, write_json, strip_html

CANDIDATES = [
    "https://rephonic.com/episodes/a7xye-the-investopedia-express-with-caleb-silver-t",
    "https://rephonic.com/episodes/mfg6d-the-investopedia-express-with-caleb-silver-t",
    "https://rephonic.com/podcasts/the-investopedia-express/episodes",
    "https://www.podchaser.com/podcasts/the-investopedia-express-with-1416947/episodes/what-might-topple-the-private-308376370",
    "https://www.podchaser.com/podcasts/the-investopedia-express-with-1416947/episodes/what-might-topple-the-private-308376370/transcript",
    "https://www.podchaser.com/podcasts/the-investopedia-express-with-1416947/episodes/recent",
    "https://podcasts.musixmatch.com/podcast/the-investopedia-express-with-caleb-silver-01hhx5xpzrz6r3vgfd2xkvwq3s",
    "https://app.podscribe.ai/series/1529322197",
]


def fetch(url: str, timeout: int = 60):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        return r.status_code, r.text, r.url
    except Exception as exc:  # noqa: BLE001
        return None, str(exc), url


def interesting_links(body: str, limit: int = 60):
    links = re.findall(r'(?:href|src|url)=["\']([^"\']+)["\']', body or "")
    links += re.findall(r'"(https?://[^"]+)"', body or "")
    keep = []
    for l in links:
        ll = l.lower()
        if ("investopedia" in ll or "transcript" in ll or "caleb" in ll) and l not in keep:
            keep.append(l)
        if len(keep) >= limit:
            break
    return keep


def sitemap_grep(url: str, needle: str = "investopedia", max_children: int = 40):
    """Follow a sitemap index one level down and return matching <loc> URLs."""
    status, body, _ = fetch(url)
    if status != 200:
        return {"status": status, "matches": []}
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
    matches = [l for l in locs if needle in l.lower()]
    children = [l for l in locs if l.endswith(".xml") or "sitemap" in l.lower()]
    for child in children[:max_children]:
        st, b, _ = fetch(child)
        if st == 200:
            matches += [l for l in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", b) if needle in l.lower()]
    return {"status": status, "locs": len(locs), "children": len(children), "matches": matches[:200]}


def youtube_probe():
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yt-dlp", "youtube-transcript-api"], check=False, timeout=300)
        out = subprocess.run(["yt-dlp", "--flat-playlist", "-j", "--no-warnings",
                              "ytsearch30:Investopedia Express Caleb Silver podcast"],
                             capture_output=True, text=True, timeout=300)
        items = []
        for line in out.stdout.splitlines():
            try:
                j = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            items.append({"title": j.get("title"), "duration": j.get("duration"), "channel": j.get("channel") or j.get("uploader"),
                          "url": j.get("url") or j.get("webpage_url"), "id": j.get("id")})
        return {"count": len(items), "items": items, "stderr": out.stderr[-500:]}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def main() -> int:
    ensure_dirs()
    out = RAW / "probe"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.html"):
        old.unlink()
    report = {"pages": [], "sitemaps": {}, "youtube": None}
    for n, u in enumerate(CANDIDATES):
        if u.endswith("sitemap.xml"):
            report["sitemaps"][u] = sitemap_grep(u)
            print("sitemap", u, json.dumps(report["sitemaps"][u])[:300])
            continue
        status, body, final = fetch(u)
        fname = out / f"page{n:02d}.html"
        fname.write_text(body or "", encoding="utf-8")
        low = (body or "").lower()
        idx = low.find("transcript")
        rec = {
            "url": u, "final_url": final, "status": status, "length": len(body or ""),
            "transcript_word_count": low.count("transcript"),
            "transcript_context": (body or "")[max(0, idx - 200): idx + 300] if idx >= 0 else None,
            "text_length": len(strip_html(body)) if body else 0,
            "links": interesting_links(body or ""),
            "file": str(fname.relative_to(RAW.parent)),
        }
        report["pages"].append(rec)
        print(json.dumps({k: rec[k] for k in ("url", "status", "length", "transcript_word_count", "text_length")}), "links:", len(rec["links"]))
    report["youtube"] = "skipped"
    write_json(RAW / "probe_report.json", report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
