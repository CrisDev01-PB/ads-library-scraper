import re
from urllib.parse import parse_qs, urlparse


def extract_page_id(input_str: str) -> str:
    """Extract page_id from a Facebook Ads Library URL or raw numeric ID."""
    s = input_str.strip()
    if s.isdigit():
        return s
    qs = parse_qs(urlparse(s).query)
    if "view_all_page_id" in qs:
        return qs["view_all_page_id"][0]
    match = re.search(r"(\d{10,})", s)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract page_id from: {input_str!r}")


def build_library_url(page_id: str, country: str = "BR") -> str:
    return (
        "https://www.facebook.com/ads/library/"
        f"?active_status=active&ad_type=all&country={country}"
        "&is_targeted_country=false&media_type=all"
        "&search_type=page&sort_data[direction]=desc"
        "&sort_data[mode]=total_impressions"
        f"&view_all_page_id={page_id}"
    )
