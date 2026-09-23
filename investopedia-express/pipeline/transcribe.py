"""Transcribe episode audio with faster-whisper (CPU). Designed to run as a
sharded GitHub Actions matrix: each shard handles episodes where
index % shards == shard.

Output per episode (in --out):
  <id>.txt   plain text, one segment per line
  <id>.json  {"id","model","audio_seconds","elapsed","segments":[[start,end,text],...]}
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (X11; Linux x86_64) investopedia-express-tracker"


def download(url: str, dest: pathlib.Path) -> None:
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": UA}, allow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 16):
                fh.write(chunk)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--only-missing", default="true")
    ap.add_argument("--out", default="out/transcripts")
    args = ap.parse_args()

    eps = json.load(open(ROOT / "data" / "episodes.json", encoding="utf-8"))["episodes"]
    existing = ROOT / "data" / "transcripts"
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    todo = [e for e in eps if (e["index"] - 1) % args.shards == args.shard and e.get("audio")]
    if args.only_missing.lower() == "true":
        todo = [e for e in todo if not (existing / f"{e['id']}.txt").exists()]
    if args.limit:
        todo = todo[: args.limit]
    print(f"shard {args.shard}/{args.shards}: {len(todo)} episodes, model {args.model}", flush=True)
    if not todo:
        return 0

    from faster_whisper import WhisperModel

    threads = os.cpu_count() or 4
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=threads)
    total_audio = 0.0
    started = time.time()
    for e in todo:
        t0 = time.time()
        with tempfile.TemporaryDirectory() as td:
            audio = pathlib.Path(td) / "ep.mp3"
            try:
                download(e["audio"], audio)
            except Exception as exc:  # noqa: BLE001
                print(f"{e['id']}: download failed: {exc}", flush=True)
                continue
            try:
                segments, info = model.transcribe(str(audio), beam_size=1, language="en", vad_filter=True,
                                                  condition_on_previous_text=False)
                segs = []
                for s in segments:
                    text = s.text.strip()
                    if text:
                        segs.append([round(s.start, 2), round(s.end, 2), text])
            except Exception as exc:  # noqa: BLE001
                print(f"{e['id']}: transcription failed: {exc}", flush=True)
                continue
        elapsed = time.time() - t0
        total_audio += info.duration or 0
        (out / f"{e['id']}.txt").write_text("\n".join(s[2] for s in segs) + "\n", encoding="utf-8")
        json.dump({"id": e["id"], "model": args.model, "audio_seconds": round(info.duration or 0, 1),
                   "elapsed": round(elapsed, 1), "segments": segs},
                  open(out / f"{e['id']}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(f"{e['id']} {e['date']} {info.duration/60:.1f} min audio → {len(segs)} segments in {elapsed/60:.1f} min "
              f"({(info.duration or 1)/max(elapsed,1):.1f}x realtime)", flush=True)
    print(f"done: {total_audio/3600:.1f} h audio in {(time.time()-started)/60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
