"""Playwright-based extraction of ads from a Facebook Ads Library page.

Captures all ad types: video, image, carousel, and text-only.
Uses Library ID text as the universal anchor (present on every ad card).
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright


# Embedded JS evaluated in the page context. Walks every ad card by anchoring
# on "Library ID" text (every ad has one, in any language) and extracts the
# fields we care about regardless of media type.
_EXTRACT_JS = r"""
(() => {
    // Words that ONLY appear inside an ad card. We use these to distinguish
    // ad cards from page-level UI containers.
    const CARD_MARKER = /(?:Library ID|ID biblioteca|Identificativo|ID de la biblioteca|Identifiant de la bibliothèque|Bibliothek-ID|ID-bibliothèque|Identifizierungsnummer|Identyfikator biblioteki|Kütüphane Kimliği|كتبة)/i;

    // Date prefix used to detect when the ad started running. Multilingual.
    const DATE_PATTERN = /(?:Started running on|Began running on|Iniziato il|Pubblicata il|Empezó a publicarse el|Se publicó el|Começou a veicular em|Diffusion lancée le|Läuft seit|Start uitgezonden op|Yayınlanmaya başlama tarihi)\s*[:]?\s*(.+?)(?:\n|$)/i;

    // Find every element that contains the card marker (Library ID etc.).
    // The marker lives in the AD CARD HEADER — a small metadata block at the
    // top of each ad. We then walk UP from each header to find the full ad
    // card container (which also contains the ad body / copy).
    const allDivs = document.querySelectorAll('div');
    const markerElements = [];
    for (const div of allDivs) {
        const text = div.innerText || '';
        if (CARD_MARKER.test(text)) markerElements.push(div);
    }
    const markerHits = markerElements.length;

    // Walk up from each marker element looking for an ancestor sized like a
    // full ad card (enough text to include the body, not the whole page).
    const TARGET_MIN = 250;
    const TARGET_MAX = 12000;
    const candidateSet = new Set();
    for (const m of markerElements) {
        let current = m;
        for (let i = 0; i < 18; i++) {
            if (!current) break;
            const text = current.innerText || '';
            if (text.length > TARGET_MAX) break;
            if (text.length >= TARGET_MIN) {
                candidateSet.add(current);
                break;
            }
            current = current.parentElement;
        }
    }
    const candidates = [...candidateSet];

    // Keep only the OUTERMOST per ad — no candidate that's contained inside
    // another candidate. (Different markers in the same ad converge on the
    // same card, but if we picked the smallest we'd miss carousels where
    // the body is in a sibling subtree.)
    const cards = candidates.filter(c =>
        !candidates.some(o => o !== c && o.contains(c))
    );

    // Diagnostics
    const _diag = {
        markerHits,
        candidates: candidates.length,
        cards: cards.length,
        totalDivs: allDivs.length,
    };

    const ads = cards.map((card, i) => {
        const text = card.innerText || '';

        // --- Start date ---
        const dateMatch = DATE_PATTERN.exec(text);
        const startDate = dateMatch ? dateMatch[1].trim() : '';

        // --- Outbound link + CTA ---
        let linkUrl = '';
        let linkTitle = '';
        const anchors = card.querySelectorAll('a[href*="l.facebook.com"]');
        for (const a of anchors) {
            if (a.href && !a.href.includes('ads/library')) {
                linkUrl = a.href;
                const lines = (a.innerText || '')
                    .split('\n')
                    .map(s => s.trim())
                    .filter(Boolean);
                linkTitle = lines.length ? lines[lines.length - 1] : '';
                break;
            }
        }

        // --- Media detection ---
        const videos = card.querySelectorAll('video');
        const hasVideo = videos.length > 0;
        const videoUrl = hasVideo
            ? (videos[0].src || (videos[0].querySelector('source') || {}).src || '')
            : '';

        const imageUrls = [...card.querySelectorAll('img')]
            .map(img => img.src)
            .filter(src => src && (src.includes('scontent') || src.includes('fbcdn')))
            .filter(src => !src.includes('emoji') && !src.includes('static.xx'));

        let mediaType;
        if (hasVideo) mediaType = 'video';
        else if (imageUrls.length > 1) mediaType = 'carousel';
        else if (imageUrls.length === 1) mediaType = 'image';
        else mediaType = 'text';

        // --- Ad copy / headline ---
        // Strip metadata lines (status, dates, library ID, platforms).
        // What remains is usually: primary text, headline, description.
        const noiseRegex = /^(Active|Inactive|Attivo|Inattivo|Activa|Inactivo|Ativo|Inativo|Activo|Aktiv|Library ID|ID biblioteca|Identificativo|ID de la biblioteca|Identifiant|Bibliothek-ID|Started running|Began running|Iniziato il|Pubblicata il|Empezó a publicarse|Se publicó el|Começou a veicular|Diffusion lancée|Läuft seit|Platforms|Piattaforme|Plataformas|Plateformes|Plattformen|Sponsored|Sponsorizzato|Patrocinado|Commandité|Gesponsert|See ad details|Vedi dettagli|See summary details|Vedi i dettagli|See more|Ver mais|Ver más|Voir plus|Mehr anzeigen|This ad has multiple versions|EU transparency|Trasparenza UE|Transparencia UE|Open Dropdown|Apri menu|Low impression count|Impressions|Impressioni|Languages|Lingue|Idiomas)$/i;

        const lines = text
            .split('\n')
            .map(s => s.trim())
            .filter(s => s.length > 0);

        // Keep lines that look like ad content (>= 30 chars OR >= 8 chars but not noise)
        const contentLines = lines.filter(line => {
            if (noiseRegex.test(line)) return false;
            if (/^\d{1,2}\/\d{1,2}\/\d{2,4}/.test(line)) return false;
            if (/^\d{10,}$/.test(line)) return false; // bare library ID number
            if (line.length < 8) return false;
            return true;
        });

        // Filter out the advertiser name itself (appears at top of every card)
        const advertiserNameLine = contentLines[0] && contentLines[0].length < 50 ? contentLines[0] : '';
        const cleanLines = contentLines.filter(l => l !== advertiserNameLine || contentLines.indexOf(l) > 1);

        // Keep the full joined cleaned text up to 8000 chars (full ad).
        const adText = cleanLines.join('\n').substring(0, 8000);

        // Try to identify the headline specifically — usually the line right
        // before the CTA button or the line with the link title.
        let headline = '';
        if (linkTitle) {
            const idx = contentLines.findIndex(l => l === linkTitle);
            if (idx > 0) {
                // The line right before the CTA is often the headline
                headline = contentLines[idx - 1];
            }
        }
        if (!headline) {
            // Fallback: shortest line >= 15 chars and <= 100 chars (typical headline length)
            const headlineCandidates = contentLines.filter(l => l.length >= 15 && l.length <= 100);
            headline = headlineCandidates[0] || '';
        }

        return {
            index: i,
            adText,
            headline,
            linkUrl,
            linkTitle,
            startDate,
            mediaType,
            videoUrl,
            imageUrls: imageUrls.slice(0, 10),
        };
    });

    // --- Page name ---
    let pageName = '';
    const profileLinks = document.querySelectorAll(
        'a[href*="facebook.com/"]:not([href*="l.facebook.com"]):not([href*="/ads/library"])'
    );
    for (const a of profileLinks) {
        const t = (a.innerText || '').trim();
        if (t && t.length < 80 && !/^https?:/i.test(t)) {
            pageName = t;
            break;
        }
    }
    if (!pageName) {
        const og = document.querySelector('meta[property="og:title"]');
        pageName = og ? (og.getAttribute('content') || '') : '';
    }
    if (!pageName) pageName = (document.querySelector('h1') || {}).innerText || 'Unknown';

    return { pageName, totalAds: ads.length, ads, _diag };
})()
"""


@dataclass
class Ad:
    index: int
    ad_text: str
    headline: str
    link_url: str
    link_title: str
    start_date: str
    media_type: str  # video / image / carousel / text
    video_url: str = ""
    image_urls: list[str] = field(default_factory=list)


@dataclass
class ScrapeResult:
    page_id: str
    page_name: str
    url: str
    ads: list[Ad] = field(default_factory=list)


def scrape(
    url: str,
    page_id: str,
    scroll_count: int = 5,
    headless: bool = True,
    on_progress=None,
) -> ScrapeResult:
    """Open the Ads Library page, scroll to load ads, and extract each ad's data."""

    def progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()

        progress("loading page")
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(3)

        page_name = page.evaluate(
            "(() => { const h = document.querySelector('h1'); return h ? h.innerText : 'Unknown'; })()"
        )
        progress(f"page: {page_name}")

        progress(f"scrolling up to {scroll_count}x to load ads")
        last_height = 0
        for i in range(scroll_count):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)
            page.evaluate(
                """
                document.querySelectorAll('div[role="button"]').forEach(b => {
                    const t = b.innerText || '';
                    if (t.includes('Ver mais') || t.includes('See more') ||
                        t.includes('Vedi di più') || t.includes('Mostra altro') ||
                        t.includes('Ver más') || t.includes('Voir plus')) b.click();
                });
                """
            )
            new_height = page.evaluate("document.body.scrollHeight")
            progress(f"  scroll {i + 1}/{scroll_count} (height: {new_height})")
            if new_height == last_height and i > 2:
                progress(f"  no more content loading, stopping early")
                break
            last_height = new_height

        time.sleep(3)
        progress("extracting ad data")
        data = page.evaluate(_EXTRACT_JS)
        diag = data.get("_diag", {})
        progress(f"diagnostics: {diag}")
        browser.close()

    ads = [
        Ad(
            index=a["index"],
            ad_text=a["adText"],
            headline=a.get("headline", ""),
            link_url=a["linkUrl"],
            link_title=a["linkTitle"],
            start_date=a["startDate"],
            media_type=a.get("mediaType", "unknown"),
            video_url=a.get("videoUrl", ""),
            image_urls=a.get("imageUrls", []),
        )
        for a in data["ads"]
    ]
    return ScrapeResult(
        page_id=page_id,
        page_name=data["pageName"],
        url=url,
        ads=ads,
    )
