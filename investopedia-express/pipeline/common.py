"""Shared helpers for the Investopedia Express data pipeline."""
from __future__ import annotations

import json
import pathlib
import re
import html as htmllib

ROOT = pathlib.Path(__file__).resolve().parent.parent  # investopedia-express/
DATA = ROOT / "data"
RAW = ROOT / "data-raw"
LOGOS = ROOT / "logos"
PIPE = ROOT / "pipeline"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def ensure_dirs() -> None:
    for d in (DATA, RAW, LOGOS):
        d.mkdir(parents=True, exist_ok=True)


def read_json(path: pathlib.Path, default=None):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: pathlib.Path, obj, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if compact:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|li|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmllib.unescape(s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def slugify(s: str, maxlen: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    return s[:maxlen].rstrip("-") or "episode"


_BOILER = [
    r"Learn more about your ad choices\.?\s*Visit\s*(?:podcastchoices|megaphone)\.\S*",
    r"Subscribe to Value Add by Investopedia on Substack:?\s*\S*",
    r"See omnystudio\.com/listener for privacy information\.?",
    r"Hosted on Acast\. See acast\.com/privacy for more information\.?",
    r"See acast\.com/privacy for privacy and opt-out information\.?",
    r"Want The Express every day\? Sign up for the daily morning newsletter at Investopedia\.com\.?",
]


def clean_description(text: str) -> str:
    """Strip ad/boilerplate lines, show-note link dumps and bare URLs."""
    if not text:
        return ""
    for pat in _BOILER:
        text = re.sub(pat, " ", text, flags=re.I)
    # "LINKS FOR SHOW NOTES: http..." style sections – drop from the marker to the end
    text = re.sub(r"(?is)\b(?:links?\s+for\s+show\s+notes|show\s+notes\s+links?|links?)\s*:?\s*(?=(?:https?://|www\.|[a-z0-9.-]+\.(?:com|org|net|co)/))[\s\S]*$", " ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"(?i)\s*\blinks?(?:\s+(?:mentioned|referenced|for\s+show\s+notes))?\s*:?\s*$", "", text)
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip(" \n-–—")
