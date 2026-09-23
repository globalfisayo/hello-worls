"""Find public-company mentions in every episode.

Input : data/episodes.json (+ data/transcripts/*.txt when available)
        pipeline/companies.py (dictionary), pipeline/overrides.json (manual fixes)
Output: data/mentions.json
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from collections import defaultdict

from common import DATA, PIPE, read_json, write_json, clean_description
import companies as C

BOILERPLATE = [
    r"Learn more about your ad choices\.?\s*Visit\s*(podcastchoices|megaphone)\.\S*",
    r"Subscribe to Value Add by Investopedia on Substack:?\s*\S*",
    r"See omnystudio\.com/listener for privacy information\.?",
    r"Hosted on Acast\. See acast\.com/privacy for more information\.?",
]

CUE_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in C.CUE_WORDS) + r")\b", re.I)
EXCL_RE = [re.compile(p) for p in C.EXCLUDE_PATTERNS]


def clean(text: str) -> str:
    return clean_description(text)


def compile_aliases():
    """Build one alternation regex for every alias plus a lookup table.

    Returns (regex, table) where table maps the literal alias text to a list of
    (ticker, ambiguous, valid_from, valid_until) tuples.
    """
    table = {}
    for ticker, name, aliases, opt in C.ENTRIES:
        if not aliases:
            continue
        for raw in aliases.split("|"):
            raw = raw.strip()
            if not raw:
                continue
            ambiguous = raw.startswith("?")
            if ambiguous:
                raw = raw[1:]
            valid_from = valid_until = None
            if "<" in raw:
                raw, valid_until = raw.split("<", 1)
            if "@" in raw:
                raw, valid_from = raw.split("@", 1)
            table.setdefault(raw, []).append((ticker, ambiguous, valid_from, valid_until))
    # Longest first so "Bank of America" wins over "America"; one pass over the text.
    alts = sorted(table, key=len, reverse=True)
    pattern = r"(?<![A-Za-z0-9])(" + "|".join(re.escape(a) for a in alts) + r")(?:'s)?(?![A-Za-z0-9])"
    return re.compile(pattern), table


ALIAS_RE, ALIAS_TABLE = compile_aliases()


def excluded(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 30): end + 40]
    return any(r.search(window) for r in EXCL_RE)


def has_cue(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 90): end + 90]
    return bool(CUE_RE.search(window))


def snippet(text: str, start: int, end: int, width: int = 110) -> str:
    a = max(0, start - width)
    b = min(len(text), end + width)
    s = text[a:b].replace("\n", " ")
    if a > 0:
        s = "…" + s
    if b < len(text):
        s = s + "…"
    return s.strip()


def scan(text: str, date: str, source: str):
    """Yield (ticker, alias, start, end, source) for every accepted match."""
    found = []
    for m in ALIAS_RE.finditer(text):
        alias = m.group(1)
        s, e = m.start(), m.end()
        if excluded(text, s, e):
            continue
        for ticker, ambiguous, valid_from, valid_until in ALIAS_TABLE[alias]:
            if valid_from and date < valid_from:
                continue
            if valid_until and date >= valid_until:
                continue
            if ambiguous and not has_cue(text, s, e):
                continue
            found.append((ticker, alias, s, e, source))
    return found


def main() -> int:
    eps_doc = read_json(DATA / "episodes.json")
    if not eps_doc:
        print("episodes.json missing", file=sys.stderr)
        return 1
    overrides = read_json(PIPE / "overrides.json", {}) or {}
    add_over = overrides.get("add", {})       # {episode_id: [ticker, ...]}
    drop_over = overrides.get("drop", {})     # {episode_id: [ticker, ...]} or {"*": [...]}
    global_drop = set(drop_over.get("*", []))

    tdir = DATA / "transcripts"
    per_episode = []
    by_ticker = defaultdict(list)
    stats = defaultdict(int)
    for ep in eps_doc["episodes"]:
        eid, date = ep["id"], ep["date"] or "1970-01-01"
        title = clean(ep["title"])
        desc = clean(ep["description"])
        transcript = ""
        seg_starts = []   # (char offset, seconds) for mapping matches back to audio time
        tfile = tdir / f"{eid}.txt"
        jfile = tdir / f"{eid}.json"
        if jfile.exists():
            try:
                segs = read_json(jfile).get("segments", [])
                parts = []
                pos = 0
                for st, en, txt in segs:
                    txt = txt.replace("\n", " ").strip()
                    seg_starts.append((pos, st))
                    parts.append(txt)
                    pos += len(txt) + 1
                transcript = "\n".join(parts)
            except Exception:  # noqa: BLE001
                transcript = ""
        if not transcript and tfile.exists():
            transcript = tfile.read_text(encoding="utf-8")
        transcript = transcript.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
        matches = []
        for src, text in (("title", title), ("description", desc), ("transcript", transcript)):
            if not text:
                continue
            for ticker, alias, s, e, source in scan(text, date, src):
                rec = {"ticker": ticker, "alias": alias, "source": source, "snippet": snippet(text, s, e)}
                if src == "transcript" and seg_starts:
                    import bisect
                    k = bisect.bisect_right([o for o, _ in seg_starts], s) - 1
                    rec["t"] = seg_starts[max(k, 0)][1]
                matches.append(rec)
        # manual fixes
        for t in add_over.get(eid, []):
            matches.append({"ticker": t, "alias": "(manual)", "source": "manual", "snippet": title})
        dropset = global_drop | set(drop_over.get(eid, []))
        matches = [m for m in matches if m["ticker"] not in dropset]

        # collapse to one record per ticker, keep the best snippet (title > description > transcript)
        order = {"title": 0, "description": 1, "manual": 1, "transcript": 2}
        grouped = {}
        for m in sorted(matches, key=lambda m: order[m["source"]]):
            g = grouped.setdefault(m["ticker"], {"ticker": m["ticker"], "count": 0, "sources": set(), "snippets": [], "aliases": set(), "times": []})
            g["count"] += 1
            g["sources"].add(m["source"])
            g["aliases"].add(m["alias"])
            if "t" in m:
                g["times"].append(m["t"])
            if len(g["snippets"]) < 3 and m["snippet"] not in g["snippets"]:
                g["snippets"].append(m["snippet"])
        recs = []
        for t, g in grouped.items():
            rec = {
                "ticker": t,
                "count": g["count"],
                "sources": sorted(g["sources"], key=lambda s: order[s]),
                "aliases": sorted(g["aliases"]),
                "snippets": g["snippets"],
                "times": sorted(g["times"])[:12],
            }
            recs.append(rec)
            by_ticker[t].append({"episode": eid, "date": ep["date"], "title": ep["title"], "count": g["count"],
                                 "sources": rec["sources"], "snippet": g["snippets"][0] if g["snippets"] else "",
                                 "times": rec["times"]})
            stats[t] += 1
        per_episode.append({"id": eid, "date": ep["date"], "title": ep["title"], "has_transcript": bool(transcript),
                            "mentions": sorted(recs, key=lambda r: (-r["count"], r["ticker"]))})

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "episodes": per_episode,
        "companies": {t: sorted(v, key=lambda m: m["date"]) for t, v in by_ticker.items()},
        "summary": {
            "episodes": len(per_episode),
            "episodes_with_transcript": sum(1 for e in per_episode if e["has_transcript"]),
            "episodes_with_mentions": sum(1 for e in per_episode if e["mentions"]),
            "companies": len(by_ticker),
            "total_mentions": sum(len(v) for v in by_ticker.values()),
        },
    }
    write_json(DATA / "mentions.json", out)
    top = sorted(stats.items(), key=lambda kv: -kv[1])[:25]
    print("episodes:", out["summary"]["episodes"], "with transcript:", out["summary"]["episodes_with_transcript"],
          "with mentions:", out["summary"]["episodes_with_mentions"], "companies:", out["summary"]["companies"],
          "mentions:", out["summary"]["total_mentions"])
    print("top:", ", ".join(f"{t}={n}" for t, n in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
