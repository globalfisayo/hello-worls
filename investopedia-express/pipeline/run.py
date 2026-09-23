"""Orchestrate the Investopedia Express data pipeline.

Modes:
  probe  – fetch the feed, then probe candidate transcript pages (saves raw HTML)
  full   – feed → transcripts → mentions → prices → logos → app index

Every stage is isolated so that one failure does not lose the others' output.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
import traceback


def run_stage(name: str, argv: list[str] | None = None) -> bool:
    started = time.time()
    print(f"\n=== stage: {name} ===", flush=True)
    try:
        mod = importlib.import_module(name)
        old = sys.argv
        sys.argv = [name] + (argv or [])
        try:
            rc = mod.main()
        finally:
            sys.argv = old
        ok = (rc or 0) == 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        ok = False
    print(f"=== {name}: {'ok' if ok else 'FAILED'} in {time.time() - started:.1f}s", flush=True)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="full", choices=["probe", "full", "feed", "extract", "prices", "logos", "index"])
    args = ap.parse_args()

    results: dict[str, bool] = {}
    if args.mode in ("probe", "full", "feed"):
        results["fetch_feed"] = run_stage("fetch_feed")
    if args.mode == "probe":
        results["probe_pages"] = run_stage("probe_pages")
    if args.mode in ("full",):
        results["fetch_transcripts"] = run_stage("fetch_transcripts")
    if args.mode in ("full", "extract"):
        results["extract"] = run_stage("extract")
    if args.mode in ("full", "prices"):
        results["fetch_prices"] = run_stage("fetch_prices")
    if args.mode in ("full", "logos"):
        results["fetch_logos"] = run_stage("fetch_logos")
    if args.mode in ("full", "index", "extract", "prices"):
        results["build_index"] = run_stage("build_index")

    print("\nSummary:")
    for k, v in results.items():
        print(f"  {k:18s} {'ok' if v else 'FAILED'}")
    # Never hard-fail the job: partial data is still committed for inspection.
    return 0


if __name__ == "__main__":
    sys.exit(main())
