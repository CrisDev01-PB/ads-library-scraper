"""CLI entry point — wires url -> scrape -> download -> report into a single command."""

import argparse
import subprocess
import sys
from pathlib import Path

from ads_library_scraper.download import download_videos
from ads_library_scraper.report import write_metadata, write_report
from ads_library_scraper.scrape import scrape
from ads_library_scraper.url import build_library_url, extract_page_id


def _ensure_chromium() -> None:
    """Auto-install Playwright's Chromium on first run if missing.

    Browsers cache at ~/.cache/ms-playwright on Linux/Mac, so this runs once
    per machine even though `uvx` envs are ephemeral.
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return
    except Exception as e:
        msg = str(e).lower()
        if "executable doesn't exist" not in msg and "browsertype.launch" not in msg:
            raise
    print("⏳ First run — installing Chromium for Playwright (one-time, ~150 MB)...", file=sys.stderr)
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ads-library-scraper",
        description="Scrape Facebook Ads Library — videos + metadata + report from any advertiser page.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Page ID (e.g. 168788392993468) or full Ads Library URL",
    )
    parser.add_argument("--url", help="Full Ads Library URL (overrides --input, e.g. for keyword search)")
    parser.add_argument("--country", default="BR", help="Country filter (default: BR)")
    parser.add_argument("--scroll", "-s", type=int, default=5, help="Scrolls to load more ads (default: 5)")
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=8,
        help="Parallel video downloads (default: 8)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output dir (default: ./fb-ads-<page_id>)",
    )
    parser.add_argument("--no-download", action="store_true", help="Skip video downloads, only metadata + report")
    parser.add_argument("--headed", action="store_true", help="Show the browser window (debug)")
    args = parser.parse_args(argv)

    if args.url:
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(args.url).query)
        page_id = qs.get("view_all_page_id", ["search"])[0]
        url = args.url
    elif args.input:
        page_id = extract_page_id(args.input)
        url = build_library_url(page_id, country=args.country)
    else:
        parser.error("Provide a page_id / URL as positional arg, or use --url")
        return 2

    out_dir = args.output or Path.cwd() / f"fb-ads-{page_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 page_id={page_id}")
    print(f"📁 output={out_dir}")
    print(f"🌐 url={url}")
    print()

    _ensure_chromium()

    result = scrape(
        url=url,
        page_id=page_id,
        scroll_count=args.scroll,
        headless=not args.headed,
        on_progress=lambda m: print(f"  {m}"),
    )
    media_counts = {}
    for a in result.ads:
        media_counts[a.media_type] = media_counts.get(a.media_type, 0) + 1
    media_summary = ", ".join(f"{n} {t}" for t, n in media_counts.items())
    print(f"✅ found {len(result.ads)} active ads ({media_summary})")

    meta_path = write_metadata(result, out_dir)
    print(f"💾 {meta_path.name}")

    downloaded = 0
    total_bytes = 0
    video_ads = [a for a in result.ads if a.media_type == "video" and a.video_url]
    if not args.no_download and video_ads:
        jobs = [
            (a.index, a.video_url, out_dir / f"video_{a.index:02d}.mp4")
            for a in video_ads
        ]
        print(f"⬇️  downloading {len(jobs)} videos ({args.concurrency} parallel)...")

        def _on_done(r) -> None:
            tag = "✅" if r.ok else "❌"
            mb = r.bytes / (1024 * 1024)
            extra = f" ({r.error})" if not r.ok and r.error else ""
            print(f"  {tag} video_{r.index:02d}.mp4  {mb:.1f}MB{extra}")

        results = download_videos(jobs, concurrency=args.concurrency, on_done=_on_done)
        downloaded = sum(1 for r in results if r.ok)
        total_bytes = sum(r.bytes for r in results if r.ok)

    report_path = write_report(result, out_dir, downloaded, total_bytes)
    print(f"📋 {report_path.name}")

    print()
    print("=" * 50)
    print(f"📊 {len(result.ads)} ads from '{result.page_name}' ({media_summary})")
    if not args.no_download and video_ads:
        print(f"🎬 {downloaded}/{len(video_ads)} videos ({total_bytes / (1024 * 1024):.1f} MB)")
    print(f"📁 {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
