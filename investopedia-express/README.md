# Express Tracker

Every public company mentioned on **The Investopedia Express with Caleb Silver**, plotted
against its stock price with a marker on every episode date it came up.

Live app (once merged to `master`): `https://globalfisayo.github.io/hello-worls/investopedia-express/`

## What you get

- **Companies view** – one card per company with logo, sector, mention count, price sparkline
  with mention dots, and the return since the show first mentioned it. Hover a card for the
  first/latest mention and the latest quote.
- **Detail drawer** – zoomable, pannable price chart (wheel/pinch, drag, brush strip,
  double-click to reset) with an orange marker on every episode date. Hover the line for a
  crosshair readout; hover a marker for the episode, the quote from the show, and what the
  stock did in the following 30 days. Switch to *vs S&P 500 (indexed)* to compare on one axis.
  Every mention is listed underneath with "play from" buttons that start the episode audio
  at the moment the company is named.
- **Episodes view** – the whole back-catalogue, newest first, with company chips per episode.
- **Table view** – the accessible twin of the cards.
- Light/dark theme, search, sector filter, date-range presets, ETF toggle, phone-friendly.

## How the data is built

Everything lives in `pipeline/` and runs on GitHub Actions (`.github/workflows/`):

| Step | Script | Source |
|---|---|---|
| Episode list | `fetch_feed.py` | the show's public RSS feed (Megaphone) |
| Transcripts | `transcribe.py` (workflow `investopedia-transcribe.yml`) | episode audio transcribed with `faster-whisper` (`small.en`) in a 20-shard matrix |
| Company mentions | `extract.py` + `companies.py` | dictionary matching over title, show notes and transcript; ambiguous names (Target, Gap, Block…) need a stock-market cue word nearby; `overrides.json` for manual fixes |
| Prices | `fetch_prices.py` | Yahoo Finance daily closes via `yfinance`, Stooq fallback |
| Logos | `fetch_logos.py` | company favicons/Clearbit (colour) and `nvstly/icons` (mono, for dark theme) |
| App bundle | `build_index.py` | `data/app.json` + `data/prices/*.json` |

`investopedia-data.yml` refreshes everything every Monday (after the new episode drops) and
on demand; `investopedia-transcribe.yml` transcribes any episode that does not have a
transcript yet. Both commit their output back to the branch.

Run locally: `cd pipeline && pip install -r requirements.txt && python run.py --mode full`,
then serve the folder with any static server (`python -m http.server`).

## Caveats

- Mentions are found by name matching, not by reading. Sponsor reads and guests' employers
  count as mentions (they are, after all, public companies named on the show).
- Whisper occasionally mis-hears names; the dictionary includes the common variants.
- A few delisted tickers (Twitter, SVB, WeWork…) have no price history in the free feeds and
  appear without a chart.
- Not investment advice.
