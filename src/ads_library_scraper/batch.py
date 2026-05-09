"""Batch orchestrator: scrape multiple Ads Library pages, optionally
download + transcribe videos, and emit one combined markdown file."""
import argparse
import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

from ads_library_scraper.scrape import scrape
from ads_library_scraper.url import build_library_url, extract_page_id


def _has_mlx_whisper() -> bool:
    return shutil.which("mlx_whisper") is not None


async def _download_one(client, url, out_path):
    try:
        async with client.stream("GET", url, timeout=180) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                async for chunk in r.aiter_bytes(64 * 1024):
                    f.write(chunk)
        return out_path.stat().st_size
    except Exception as e:
        return f"ERR: {e}"


async def _download_batch(jobs, concurrency=8):
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def bounded(url, path):
            async with sem:
                return await _download_one(client, url, path)
        tasks = [bounded(url, path) for url, path in jobs]
        return await asyncio.gather(*tasks)


def _transcribe(mp4_path, model="mlx-community/whisper-large-v3-turbo"):
    txt_path = mp4_path.with_suffix(".txt")
    result = subprocess.run(
        [
            "mlx_whisper",
            str(mp4_path),
            "--output-dir", str(mp4_path.parent),
            "--output-format", "txt",
            "--model", model,
            "--verbose", "False",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8").strip()
    return f"(transcribe failed: {result.stderr[-200:].strip()})"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ads-library-batch",
        description="Scrape multiple Ads Library pages into one combined markdown file. Optionally transcribe video ads.",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more page IDs or full Ads Library URLs",
    )
    parser.add_argument("--country", default="ALL", help="Country filter (default: ALL)")
    parser.add_argument("--scroll", type=int, default=30, help="Scrolls per page (default: 30)")
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="Download + transcribe video ads with mlx-whisper",
    )
    parser.add_argument(
        "--max-videos-per-page",
        type=int,
        default=None,
        help="Cap videos transcribed per page (default: no cap)",
    )
    parser.add_argument(
        "--whisper-model",
        default="mlx-community/whisper-large-v3-turbo",
        help="mlx-whisper model id (default: large-v3-turbo)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output markdown file path",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("/tmp/ads-library-batch"),
        help="Workdir for video downloads (default: /tmp/ads-library-batch)",
    )
    args = parser.parse_args(argv)

    if args.transcribe and not _has_mlx_whisper():
        print("❌ --transcribe requested but mlx_whisper not on PATH. Install it: pip install mlx-whisper", file=sys.stderr)
        return 2

    page_ids = [extract_page_id(s) for s in args.inputs]
    args.workdir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def log(msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    # ---- Phase 1: scrape all pages ----
    log(f"=== Scraping {len(page_ids)} pages ===")
    all_pages = []
    for idx, pid in enumerate(page_ids, 1):
        log(f"[{idx}/{len(page_ids)}] page {pid}...")
        try:
            result = scrape(
                url=build_library_url(pid, country=args.country),
                page_id=pid,
                scroll_count=args.scroll,
                headless=True,
                on_progress=lambda m: None,
            )
            log(f"  → '{result.page_name}': {len(result.ads)} ads")
            all_pages.append((pid, result))
        except Exception as e:
            log(f"  ❌ scrape failed: {e}")
            all_pages.append((pid, None))

    # ---- Phase 2: download videos (if --transcribe) ----
    download_jobs = []  # (page_idx, ad_idx, url, out_path)
    if args.transcribe:
        log("\n=== Phase 2: downloading videos ===")
        for page_idx, (pid, result) in enumerate(all_pages):
            if result is None:
                continue
            page_dir = args.workdir / pid
            page_dir.mkdir(exist_ok=True)
            videos_for_page = 0
            for ad_idx, ad in enumerate(result.ads):
                if ad.media_type == "video" and ad.video_url:
                    if args.max_videos_per_page and videos_for_page >= args.max_videos_per_page:
                        break
                    mp4 = page_dir / f"video_{ad_idx:03d}.mp4"
                    download_jobs.append((page_idx, ad_idx, ad.video_url, mp4))
                    videos_for_page += 1
        log(f"Total videos to download: {len(download_jobs)}")
        if download_jobs:
            paths = [(url, mp4) for _, _, url, mp4 in download_jobs]
            sizes = asyncio.run(_download_batch(paths))
            ok = sum(1 for s in sizes if isinstance(s, int))
            log(f"Downloaded {ok}/{len(download_jobs)}")

    # ---- Phase 3: transcribe ----
    transcripts = {}
    if args.transcribe and download_jobs:
        log(f"\n=== Phase 3: transcribing {len(download_jobs)} videos ===")
        for n, (page_idx, ad_idx, _url, mp4) in enumerate(download_jobs, 1):
            if not mp4.exists() or mp4.stat().st_size < 1000:
                transcripts[(page_idx, ad_idx)] = "(download failed or empty)"
                continue
            log(f"  [{n}/{len(download_jobs)}] {mp4.parent.name} / ad {ad_idx}")
            try:
                transcripts[(page_idx, ad_idx)] = _transcribe(mp4, model=args.whisper_model)
            except subprocess.TimeoutExpired:
                transcripts[(page_idx, ad_idx)] = "(transcribe timed out)"
            except Exception as e:
                transcripts[(page_idx, ad_idx)] = f"(transcribe error: {e})"

    # ---- Phase 4: write combined markdown ----
    log("\n=== Phase 4: writing combined markdown ===")
    lines = []
    lines.append(f"# Combined Ads Library swipe — {len(page_ids)} pages")
    lines.append("")
    lines.append(f"- **Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
    total_ads = sum(len(r.ads) for _, r in all_pages if r is not None)
    lines.append(f"- **Total ads:** {total_ads}")
    if args.transcribe:
        lines.append(f"- **Videos transcribed:** {sum(1 for v in transcripts.values() if v and not v.startswith('('))}")
    lines.append("")
    lines.append("## Pages covered")
    lines.append("")
    for pid, result in all_pages:
        if result is None:
            lines.append(f"- ❌ `{pid}` — scrape failed")
        else:
            n_video = sum(1 for a in result.ads if a.media_type == "video")
            lines.append(f"- `{pid}` — **{result.page_name}** — {len(result.ads)} ads ({n_video} video)")
    lines.append("")

    for page_idx, (pid, result) in enumerate(all_pages):
        if result is None:
            continue
        lines.append("---")
        lines.append("")
        lines.append(f"# Page: {result.page_name}")
        lines.append("")
        lines.append(f"- **Page ID:** `{pid}`")
        lines.append(f"- **Total ads:** {len(result.ads)}")
        lines.append(f"- **Source URL:** {build_library_url(pid, country=args.country)}")
        lines.append("")

        for ad_idx, ad in enumerate(result.ads):
            lines.append(f"## {result.page_name} — Ad #{ad_idx + 1} ({ad.media_type})")
            lines.append("")
            if ad.start_date:
                lines.append(f"- **Started:** {ad.start_date}")
            if ad.headline:
                lines.append(f"- **Headline:** {ad.headline}")
            if ad.link_title:
                lines.append(f"- **CTA:** {ad.link_title}")
            if ad.link_url:
                lines.append(f"- **Link:** {ad.link_url}")
            lines.append("")

            if ad.ad_text:
                lines.append("### On-card copy")
                lines.append("```")
                lines.append(ad.ad_text)
                lines.append("```")
                lines.append("")

            if args.transcribe and ad.media_type == "video":
                t = transcripts.get((page_idx, ad_idx), "(not transcribed)")
                lines.append("### Spoken transcript")
                lines.append("```")
                lines.append(t)
                lines.append("```")
                lines.append("")

    args.output.write_text("\n".join(lines), encoding="utf-8")
    log(f"\n✅ Wrote {args.output} ({args.output.stat().st_size:,} bytes)")

    # Final summary line — easy for Claude/scripts to parse
    media_totals = {}
    for _, result in all_pages:
        if result is None:
            continue
        for ad in result.ads:
            media_totals[ad.media_type] = media_totals.get(ad.media_type, 0) + 1
    media_str = " ".join(f"{k}={v}" for k, v in sorted(media_totals.items()))
    failed = sum(1 for _, r in all_pages if r is None)
    transcribed = sum(1 for v in transcripts.values() if v and not v.startswith("("))
    print(
        f"SUMMARY: pages={len(page_ids)} pages_failed={failed} "
        f"total_ads={total_ads} {media_str} "
        f"transcribed={transcribed} output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
