"""Generate ads_metadata.json + report.md from a ScrapeResult."""

import json
import time
from collections import Counter
from pathlib import Path

from ads_library_scraper.scrape import ScrapeResult


def write_metadata(result: ScrapeResult, out_dir: Path) -> Path:
    payload = {
        "page_id": result.page_id,
        "page_name": result.page_name,
        "url": result.url,
        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_ads": len(result.ads),
        "ads": [
            {
                "index": a.index,
                "media_type": a.media_type,
                "headline": a.headline,
                "ad_text": a.ad_text,
                "link_url": a.link_url,
                "link_title": a.link_title,
                "start_date": a.start_date,
                "library_id": a.library_id,
                "library_url": a.library_url,
                "video_url": a.video_url,
                "image_urls": a.image_urls,
            }
            for a in result.ads
        ],
    }
    path = out_dir / "ads_metadata.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def write_report(result: ScrapeResult, out_dir: Path, downloaded: int, total_bytes: int) -> Path:
    ctas = Counter(a.link_title for a in result.ads if a.link_title)
    domains = Counter(
        a.link_url.split("/")[2] for a in result.ads if a.link_url and "://" in a.link_url
    )
    media_breakdown = Counter(a.media_type for a in result.ads)

    lines = [
        f"# Ads Library report — {result.page_name}",
        "",
        f"- **Page ID:** `{result.page_id}`",
        f"- **Page name:** {result.page_name}",
        f"- **Scraped at:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Source URL:** {result.url}",
        f"- **Active ads found:** {len(result.ads)}",
    ]
    if media_breakdown:
        breakdown = ", ".join(f"{n} {t}" for t, n in media_breakdown.most_common())
        lines.append(f"- **Media mix:** {breakdown}")
    if downloaded or total_bytes:
        lines.append(
            f"- **Videos downloaded:** {downloaded} ({total_bytes / (1024 * 1024):.1f} MB)"
        )

    lines += ["", "## Top CTAs", ""]
    if ctas:
        for cta, count in ctas.most_common(5):
            lines.append(f"- `{cta}` × {count}")
    else:
        lines.append("_(none captured)_")

    lines += ["", "## Top destination domains", ""]
    if domains:
        for dom, count in domains.most_common(5):
            lines.append(f"- `{dom}` × {count}")
    else:
        lines.append("_(none captured)_")

    lines += ["", "## Ads", ""]
    for a in result.ads:
        copy = (a.ad_text or "").strip()
        lines.append(f"### Ad #{a.index + 1} — {a.media_type}")
        if a.start_date:
            lines.append(f"- **Started:** {a.start_date}")
        if a.library_id:
            lines.append(f"- **Library ID:** `{a.library_id}`")
            lines.append(f"- **Single ad URL:** {a.library_url}")
        if a.headline:
            lines.append(f"- **Headline:** {a.headline}")
        if a.link_title:
            lines.append(f"- **CTA button:** {a.link_title}")
        if a.link_url:
            lines.append(f"- **Destination link:** {a.link_url}")
        if copy:
            lines.append("- **Copy:**")
            lines.append("")
            lines.append("```")
            lines.append(copy)
            lines.append("```")
        lines.append("")

    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
