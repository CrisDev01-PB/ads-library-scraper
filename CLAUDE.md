# ads-library-scraper — repo conventions

Notes for Claude / future maintainers working **on** this codebase. End-users / agents using the tool should read `README.md` and `SKILL.md`.

## Design rules

- **Single-shot CLI.** One command does discover + report + download. Don't add interactive prompts, sub-commands, or dashboards.
- **Defaults assume "do everything."** No required flags. Override flags exist (`--no-download`, `--scroll`, etc.) but the bare command must Just Work.
- **Output structure is a stable contract.** Agents read `report.md` and parse `ads_metadata.json`. Don't rename, restructure, or change field names without bumping the version.
- **No new dependencies without a clear reason.** The runtime stack is `playwright` + `httpx`, period. Argparse is stdlib on purpose.

## Code layout

```
src/ads_library_scraper/
├── url.py        # extract page_id from URL / build Ads Library URL
├── scrape.py     # Playwright-driven extraction (the brittle bit)
├── download.py   # httpx async parallel downloads
├── report.py     # ads_metadata.json + report.md writers
└── cli.py        # argparse + auto-install Chromium + glue
```

If FB changes the Ads Library DOM, the breakage will surface in `scrape.py:_EXTRACT_JS`. That's the only file that talks to Facebook's actual page structure.

## Smoke test before pushing

There are no automated tests yet — the moving parts (Playwright DOM walk, FB URL signing, video download) are real-world dependent. Run this before pushing anything that touches `scrape.py`, `download.py`, or `cli.py`:

```bash
uv run ads-library-scraper 168788392993468 --scroll 1 -o /tmp/smoke
```

A passing run looks like:

- ✅ found ≥ 20 active video ads
- 📊 page name resolved to a real advertiser (not "Unknown" / "Biblioteca de Anúncios")
- All videos > 1 KB and total size > 50 MB
- `report.md` shows a "Top CTAs" block with short button-text values (`Saiba mais`, `Cadastre-se`), not multi-line copy

## Known untested paths

- **First-time Chromium install via `_ensure_chromium`** — on a fresh machine where `~/Library/Caches/ms-playwright` doesn't exist yet, the auto-install branch should trigger. This was never exercised end-to-end during initial development (Chromium was already cached). If a user reports "browser not found" errors, look here first.
- **Windows** — never tested. Playwright supports it, but the cache paths and shell quoting conventions differ.

## When FB breaks the scraper

The DOM walk in `scrape.py:_EXTRACT_JS` makes assumptions about:

- A `<video>` element exists per ad card
- The advertiser name appears in an `<a>` linking to `facebook.com/<id>` (not `l.facebook.com`, not `/ads/library`)
- The destination link uses `l.facebook.com` redirector
- Date copy starts with "Começou a veicular em" (PT) or "Started running on" (EN)

If extraction returns 0 ads or empty fields, run with `--headed` to see the actual page, then update the JS accordingly.

## Commit style

Follow the existing log: short imperative subject, then a body paragraph explaining the *why* and any non-obvious behavior change. No commit message footer signatures.
