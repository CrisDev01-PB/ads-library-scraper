# ads-library-scraper

Scrape ads from any Facebook/Meta Ad Library page. Pulls full ad copy, headlines, CTAs, links, and start dates from every active ad on a page. Optionally downloads and transcribes video ads using mlx-whisper.

No Meta API. No identity verification. No region locks. Works for EU users.

## What you get

- **Per-ad data**: copy text (up to 8000 chars), headline, CTA button label, outbound link, start date, media type (video / image / carousel / text)
- **Video transcripts**: downloads videos and transcribes with mlx-whisper (Apple Silicon, fast)
- **Multi-page batch**: feed it 1 or 50 page IDs, get one combined markdown swipe file

## Install

Requires [uv](https://docs.astral.sh/uv/). If you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

**Install globally:**

```bash
uv tool install git+https://github.com/CrisDev01-PB/ads-library-scraper
```

This puts `ads-library-scraper` and `ads-library-batch` on your PATH. To update: `uv tool upgrade ads-library-scraper`.

**Or one-shot, no install:**

```bash
uvx --from git+https://github.com/CrisDev01-PB/ads-library-scraper \
    ads-library-batch 581718728356117 --output ~/swipe.md
```

For transcription, also install `mlx-whisper` (macOS Apple Silicon only):

```bash
pip install mlx-whisper
```

## Two commands

### `ads-library-scraper` — single page, fast

```bash
ads-library-scraper 581718728356117 --no-download
```

Output: `fb-ads-581718728356117/report.md` + `ads_metadata.json`.

### `ads-library-batch` — multi-page, optional transcripts, single output file

```bash
ads-library-batch 581718728356117 583184871545751 239824379214213 \
    --output ~/swipe.md
```

With transcripts:

```bash
ads-library-batch 581718728356117 583184871545751 \
    --output ~/swipe.md \
    --transcribe \
    --max-videos-per-page 5
```

`--max-videos-per-page` caps how many videos to download + transcribe per page (default: no cap, do all).

## Page IDs

Pass either:
- The raw page ID (numeric, e.g. `581718728356117`)
- A full Ads Library URL — the script extracts the `view_all_page_id` from it

To find a page ID: open the brand's Ad Library URL — it ends with `view_all_page_id=...`.

## How it works

1. Opens the Ads Library page in headless Chromium (Playwright)
2. Scrolls until no new content loads
3. Walks the DOM to find each ad card by anchoring on the "Library ID" text (multilingual)
4. Extracts copy, headline, CTA, link, date, media type for each ad
5. (If `--transcribe`) downloads videos in parallel via httpx, then runs mlx-whisper per file
6. Writes everything into a structured markdown file

## What it CAN'T extract

The Ads Library is a public transparency tool, not analytics — so impressions, views, likes, targeting, and engagement data are **not available** through any public scraper. If a tool claims otherwise, it's lying.

## Limitations

- **Apple Silicon only for transcription** (uses `mlx-whisper`). For Linux/Intel, swap with `openai-whisper` and adjust `batch.py`.
- **The "headline" field is heuristic** — Meta ads don't have a structured headline for every format. Output may sometimes be a body-text line rather than a true headline.
- **Some ads may be missed** if their card has very short text or unusual structure. Batch typically catches 85-95% of what's visible in the browser.
- **Long batch runs can hit Meta rate limits.** No backoff implemented. If you scrape 50+ pages back-to-back, expect some pages to time out — re-run them solo.

## Credits

Forked from [lucasgrow/ads-library-scraper](https://github.com/lucasgrow/ads-library-scraper). Multi-page batch + Whisper transcription added by Cristiano Sanna.

## License

MIT
