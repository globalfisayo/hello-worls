"""Download daily closing prices for every company that is mentioned at least once.

Primary source: Yahoo Finance via yfinance (batch download).
Fallback      : Stooq CSV endpoint (works for many delisted US tickers too).
Output        : data/prices/<TICKER>.json  {"t":..., "yf":..., "src":..., "d":[dates], "c":[closes], "a":[adj closes]}
                data/prices_meta.json
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sys
import time

import pandas as pd
import requests

from common import DATA, UA, ensure_dirs, read_json, write_json
import companies as C

START = "2020-06-01"
BENCHMARKS = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq Composite"}


def yf_symbol(ticker: str) -> str:
    for t, name, aliases, opt in C.ENTRIES:
        if t == ticker:
            return opt.get("yf", ticker)
    return ticker


def file_key(ticker: str) -> str:
    return ticker.replace("^", "IDX_").replace(".", "_")


def series_to_payload(ticker: str, yf_sym: str, src: str, df: pd.DataFrame) -> dict:
    df = df.dropna(subset=["Close"]).copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[df.index >= pd.Timestamp(START)]
    adj = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
    return {
        "t": ticker,
        "yf": yf_sym,
        "src": src,
        "d": [d.strftime("%Y-%m-%d") for d in df.index],
        "c": [round(float(x), 4) for x in df["Close"]],
        "a": [round(float(x), 4) for x in adj],
    }


def fetch_stooq(ticker: str) -> pd.DataFrame | None:
    sym = ticker.lower().replace("-", ".")
    if "." not in sym:
        sym = f"{sym}.us"
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": UA})
        if r.status_code != 200 or "Date" not in r.text[:100]:
            return None
        df = pd.read_csv(io.StringIO(r.text))
        if df.empty or "Close" not in df.columns:
            return None
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        return df
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ensure_dirs()
    mentions = read_json(DATA / "mentions.json")
    if not mentions:
        print("mentions.json missing – run extract first", file=sys.stderr)
        return 1
    tickers = sorted(mentions["companies"].keys())
    wanted = {t: yf_symbol(t) for t in tickers}
    for b in BENCHMARKS:
        wanted[b] = b
    print(f"Fetching prices for {len(wanted)} symbols since {START}")

    import yfinance as yf

    out_dir = DATA / "prices"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = read_json(DATA / "prices_meta.json", {}) or {}
    results = meta.get("symbols", {})
    syms = sorted(set(wanted.values()))
    got: dict[str, pd.DataFrame] = {}
    # Batch download in chunks; yfinance returns a column MultiIndex per ticker.
    chunk = 40
    for i in range(0, len(syms), chunk):
        batch = syms[i:i + chunk]
        for attempt in range(3):
            try:
                df = yf.download(batch, start=START, auto_adjust=False, group_by="ticker", threads=True, progress=False)
                break
            except Exception as exc:  # noqa: BLE001
                print("yfinance batch error:", exc)
                time.sleep(5 * (attempt + 1))
                df = None
        if df is None or df.empty:
            continue
        for s in batch:
            try:
                sub = df[s] if isinstance(df.columns, pd.MultiIndex) else df
            except KeyError:
                continue
            if sub is None or sub.dropna(subset=["Close"]).empty:
                continue
            got[s] = sub
        time.sleep(1)

    # Second chance for symbols the batch download skipped (rate limits, odd symbols).
    for sym in syms:
        if sym in got and not got[sym].dropna(subset=["Close"]).empty:
            continue
        for attempt in range(2):
            try:
                h = yf.Ticker(sym).history(start=START, auto_adjust=False)
                if h is not None and not h.empty and "Close" in h.columns:
                    if "Adj Close" not in h.columns:
                        h["Adj Close"] = h["Close"]
                    got[sym] = h
                    break
            except Exception as exc:  # noqa: BLE001
                print(f"{sym}: single fetch error: {exc}")
            time.sleep(2)

    ok, fallback, failed = 0, 0, []
    for ticker, sym in wanted.items():
        df = got.get(sym)
        src = "yahoo"
        if df is None or df.dropna(subset=["Close"]).empty:
            df = fetch_stooq(sym if not sym.startswith("^") else ticker)
            src = "stooq"
            if df is None:
                failed.append(ticker)
                results[ticker] = {"status": "missing", "yf": sym}
                continue
            fallback += 1
        else:
            ok += 1
        payload = series_to_payload(ticker, sym, src, df)
        write_json(out_dir / f"{file_key(ticker)}.json", payload, compact=True)
        results[ticker] = {"status": "ok", "src": src, "yf": sym, "first": payload["d"][0] if payload["d"] else None,
                           "last": payload["d"][-1] if payload["d"] else None, "n": len(payload["d"])}
    meta = {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "start": START,
        "symbols": results,
        "benchmarks": BENCHMARKS,
    }
    write_json(DATA / "prices_meta.json", meta)
    print(f"prices: yahoo={ok} stooq={fallback} missing={len(failed)} {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
