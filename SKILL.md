---
name: ads-library-scraper
description: Scrape Facebook Ads Library — download all active video ads + metadata (copy, links, dates) from any advertiser page. Use when the user mentions Facebook ads library, competitor ads, ad spy, "baixar anuncios", "scrape ads", or pastes a facebook.com/ads/library URL.
---

# ads-library-scraper

One-shot tool: takes a page ID or Ads Library URL → outputs a folder with every active video ad + a `report.md` summary.

## Run

**Recommended (for repeated use — installs once, available globally):**

```bash
uv tool install git+https://github.com/lucasgrow/ads-library-scraper
ads-library-scraper <page_id_or_url>
```

To upgrade later: `uv tool upgrade ads-library-scraper`.

**One-shot (no install — uvx creates an ephemeral env):**

```bash
uvx --refresh --from git+https://github.com/lucasgrow/ads-library-scraper ads-library-scraper <page_id_or_url>
```

Use `--refresh` so uvx pulls the latest from `main` instead of a stale cached version.

**If `uv` is not installed yet:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"  # PATH not auto-reloaded in current shell
```

(`uv` will also install Python automatically if the host machine doesn't have it.) Chromium is auto-installed on first scrape (cached after, ~150 MB, one-time).

## Input

Either form works:

- Numeric page ID: `168788392993468`
- Full URL: `https://www.facebook.com/ads/library/?...&view_all_page_id=168788392993468` (the tool extracts `view_all_page_id`)

## Output

Always lands in `./fb-ads-<page_id>/`:

```
fb-ads-<page_id>/
├── report.md           ← READ THIS FIRST — page name, totals, top CTAs, per-ad copy
├── ads_metadata.json   ← structured (parse if you need fields)
├── video_00.mp4
├── video_01.mp4
└── ...
```

## After scraping

1. Read `report.md` — has the totals, top CTAs, top destination domains, and copy snippets.
2. If the user wants deeper analysis, parse `ads_metadata.json` — fields per ad:
   `index`, `ad_text`, `link_url`, `link_title` (CTA), `start_date`, `video_file`.
3. Tell the user how many ads were found, total size, and the output path.

## Useful flags

- `--scroll 10` → for pages with 100+ ads (default 5 only loads ~50)
- `--no-download` → metadata only, much faster
- `--country US` → change the country filter (default `BR`)
- `--output ./my-dir` → custom output folder

## What it CANNOT do

The Ads Library is a public transparency tool. It does **not** expose impressions, views, likes, engagement, spend, or targeting data. Don't promise the user metrics that don't exist.

## Troubleshooting

- **Too few ads found** → bump `--scroll` (e.g. `--scroll 15`).
- **Videos < 1 KB** → signed URLs expired during the run, just rerun.
- **Chromium fails to launch** → run `uvx --from git+https://github.com/lucasgrow/ads-library-scraper python -m playwright install chromium` once.
- **Page returns 0 ads** → check the page actually has *active* ads (the URL filter is `active_status=active`).
