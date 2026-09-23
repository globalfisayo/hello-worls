"""Download the Investopedia Express RSS feed and normalise every episode.

Writes:
  data-raw/feed.xml      – the raw feed as served by Megaphone
  data/episodes.json     – one record per episode, oldest first
"""
from __future__ import annotations

import datetime as dt
import email.utils
import re
import sys

import requests
from lxml import etree

from common import RAW, DATA, UA, ensure_dirs, strip_html, write_json

FEED_URL = "https://feeds.megaphone.fm/investopediaexpress"
NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "podcast": "https://podcastindex.org/namespace/1.0",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
}


def parse_duration(s: str | None) -> int | None:
    if not s:
        return None
    s = s.strip()
    if s.isdigit():
        return int(s)
    parts = [p for p in s.split(":") if p != ""]
    try:
        parts = [int(float(p)) for p in parts]
    except ValueError:
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs


def pub_date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    # Episodes are published in the morning US-Eastern time; convert so the
    # calendar date matches what listeners see.
    eastern = dt.timezone(dt.timedelta(hours=-5))
    return d.astimezone(eastern).date().isoformat()


def text(el, path):
    node = el.find(path, NS)
    if node is None or node.text is None:
        return None
    return node.text.strip()


def main() -> int:
    ensure_dirs()
    resp = requests.get(FEED_URL, timeout=90, headers={"User-Agent": UA})
    resp.raise_for_status()
    (RAW / "feed.xml").write_bytes(resp.content)

    root = etree.fromstring(resp.content)
    channel = root.find("channel")
    items = channel.findall("item")
    episodes = []
    for it in items:
        guid = text(it, "guid") or ""
        title = text(it, "title") or ""
        desc_html = text(it, "content:encoded") or text(it, "description") or ""
        summary = text(it, "itunes:summary") or ""
        enclosure = it.find("enclosure")
        transcripts = []
        for tr in it.findall("podcast:transcript", NS):
            transcripts.append({"url": tr.get("url"), "type": tr.get("type"), "language": tr.get("language")})
        image = it.find("itunes:image", NS)
        episodes.append(
            {
                "guid": guid,
                "title": title,
                "date": pub_date(text(it, "pubDate")),
                "pubDate": text(it, "pubDate"),
                "link": text(it, "link"),
                "audio": enclosure.get("url") if enclosure is not None else None,
                "duration": parse_duration(text(it, "itunes:duration")),
                "episode_number": text(it, "itunes:episode"),
                "season": text(it, "itunes:season"),
                "episode_type": text(it, "itunes:episodeType"),
                "description_html": desc_html,
                "description": strip_html(desc_html),
                "summary": strip_html(summary) if summary and strip_html(summary) != strip_html(desc_html) else "",
                "image": image.get("href") if image is not None else None,
                "transcripts": transcripts,
            }
        )

    episodes.sort(key=lambda e: (e["date"] or "", e["pubDate"] or ""))
    for i, e in enumerate(episodes, start=1):
        e["index"] = i
        e["id"] = f"ep{i:03d}"

    meta = {
        "feed": FEED_URL,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "podcast_title": text(channel, "title"),
        "episode_count": len(episodes),
        "first_date": episodes[0]["date"] if episodes else None,
        "last_date": episodes[-1]["date"] if episodes else None,
        "episodes_with_transcript_tag": sum(1 for e in episodes if e["transcripts"]),
    }
    write_json(DATA / "episodes.json", {"meta": meta, "episodes": episodes})
    print(f"Fetched {len(episodes)} episodes ({meta['first_date']} → {meta['last_date']}); "
          f"{meta['episodes_with_transcript_tag']} carry a transcript tag")
    return 0


if __name__ == "__main__":
    sys.exit(main())
