"""Assemble the compact app bundle: data/app.json

Contains episodes (with mention tickers), companies (metadata + mention list +
weekly sparkline) and a manifest. Per-ticker daily prices stay in data/prices/.
"""
from __future__ import annotations

import datetime as dt
import sys

from common import DATA, LOGOS, read_json, write_json, clean_description
import companies as C


def weekly(payload: dict, max_points: int = 100):
    """Downsample daily closes to weekly (last close of each ISO week)."""
    if not payload:
        return []
    d, a = payload["d"], payload["a"]
    out = []
    last_key = None
    for i, day in enumerate(d):
        y, m, dd = day.split("-")
        key = dt.date(int(y), int(m), int(dd)).isocalendar()[:2]
        if key != last_key:
            out.append([day, round(a[i], 2)])
            last_key = key
        else:
            out[-1] = [day, round(a[i], 2)]
    if len(out) > max_points:
        step = len(out) / max_points
        out = [out[int(i * step)] for i in range(max_points)]
    return out


def main() -> int:
    eps_doc = read_json(DATA / "episodes.json")
    mentions = read_json(DATA / "mentions.json")
    prices_meta = read_json(DATA / "prices_meta.json", {}) or {}
    logos_meta = read_json(DATA / "logos_meta.json", {}) or {}
    if not eps_doc or not mentions:
        print("missing inputs", file=sys.stderr)
        return 1
    info = {t: (n, o) for t, n, a, o in C.ENTRIES}
    ep_mentions = {e["id"]: e for e in mentions["episodes"]}

    episodes = []
    for e in eps_doc["episodes"]:
        m = ep_mentions.get(e["id"], {"mentions": [], "has_transcript": False})
        episodes.append({
            "id": e["id"], "n": e["index"], "date": e["date"], "title": e["title"],
            "description": clean_description(e["description"]), "duration": e["duration"], "audio": e["audio"],
            "link": e["link"], "hasTranscript": m.get("has_transcript", False),
            "mentions": [{"t": r["ticker"], "n": r["count"], "src": r["sources"], "times": r.get("times", [])[:4]} for r in m["mentions"]],
        })

    companies = []
    for ticker, mlist in mentions["companies"].items():
        name, opt = info.get(ticker, (ticker, {}))
        pm = prices_meta.get("symbols", {}).get(ticker, {})
        base = ticker.replace(".", "_")
        pfile = DATA / "prices" / f"{base.replace('^', 'IDX_')}.json"
        payload = read_json(pfile) if pfile.exists() else None
        spark = weekly(payload) if payload else []
        first_price = payload["d"][0] if payload and payload["d"] else None
        last_price = payload["d"][-1] if payload and payload["d"] else None
        change = None
        since_first = None
        if payload and len(payload["a"]) > 1 and payload["a"][0]:
            change = round((payload["a"][-1] / payload["a"][0] - 1) * 100, 1)
            first_mention = mlist[0]["date"] if mlist else None
            if first_mention:
                import bisect
                i = bisect.bisect_left(payload["d"], first_mention)
                if i < len(payload["a"]) and payload["a"][i]:
                    since_first = round((payload["a"][-1] / payload["a"][i] - 1) * 100, 1)
        lm = logos_meta.get(ticker, {})
        companies.append({
            "t": ticker, "name": name, "sector": opt.get("sector", "Other"), "country": opt.get("country", "US"),
            "etf": bool(opt.get("etf")), "delisted": opt.get("delisted"), "domain": opt.get("domain"),
            "logo": f"logos/{base}.png" if lm.get("has_colour") else None,
            "logoMono": f"logos/mono/{base}.png" if lm.get("has_mono") else None,
            "priceFile": f"data/prices/{base.replace('^', 'IDX_')}.json" if payload else None,
            "priceSource": pm.get("src"), "firstPrice": first_price, "lastPrice": last_price,
            "changePct": change, "sinceFirstPct": since_first, "spark": spark,
            "mentions": [{"ep": m["episode"], "date": m["date"], "n": m["count"], "src": m["sources"], "snippet": m["snippet"][:170], "times": m.get("times", [])[:8]} for m in mlist],
            "mentionCount": len(mlist),
        })
    companies.sort(key=lambda c: (-c["mentionCount"], c["name"]))

    benchmarks = {}
    for b, label in (prices_meta.get("benchmarks") or {}).items():
        pfile = DATA / "prices" / f"{b.replace('^', 'IDX_')}.json"
        payload = read_json(pfile) if pfile.exists() else None
        if payload:
            benchmarks[b] = {"label": label, "priceFile": f"data/prices/{b.replace('^', 'IDX_')}.json", "spark": weekly(payload)}

    app = {
        "meta": {
            "podcast": eps_doc["meta"].get("podcast_title"),
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "feedFetchedAt": eps_doc["meta"].get("fetched_at"),
            "episodeCount": len(episodes),
            "firstDate": eps_doc["meta"].get("first_date"),
            "lastDate": eps_doc["meta"].get("last_date"),
            "companyCount": len(companies),
            "mentionCount": mentions["summary"]["total_mentions"],
            "episodesWithTranscript": mentions["summary"]["episodes_with_transcript"],
            "episodesWithMentions": mentions["summary"]["episodes_with_mentions"],
            "pricesFetchedAt": prices_meta.get("fetched_at"),
        },
        "episodes": episodes,
        "companies": companies,
        "benchmarks": benchmarks,
    }
    write_json(DATA / "app.json", app, compact=True)
    print(f"app.json: {len(episodes)} episodes, {len(companies)} companies, {len(benchmarks)} benchmarks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
