"""Discover the careers page from any company URL.

Strategy:
  1. If the URL already looks like a careers/jobs page, return it as-is.
  2. Probe common canonical paths on the same domain.
  3. Fetch the homepage and look for career-related anchor links.
"""
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

_CAREERS_PATTERNS = re.compile(
    r"\b(careers?|jobs?|work[-_]with[-_]us|join[-_]us|join[-_]our[-_]team|"
    r"opportunities|openings?|hiring|we[-_]are[-_]hiring|apply)\b",
    re.I,
)

# Already a careers-like URL — skip discovery
_ALREADY_CAREERS = re.compile(
    r"/(careers?|jobs?|openings?|work[-_]with[-_]us|join|hiring|opportunities)",
    re.I,
)

# Common careers page paths to probe
_COMMON_PATHS = [
    "/careers",
    "/jobs",
    "/work-with-us",
    "/join-us",
    "/about/careers",
    "/company/careers",
    "/company/jobs",
    "/en/careers",
    "/en/jobs",
]

# Known ATS subdomain patterns — if the URL is already one of these, it IS the board
_ATS_DOMAINS = re.compile(
    r"(boards\.greenhouse\.io|jobs\.lever\.co|ashbyhq\.com|"
    r"myworkdayjobs\.com|avature\.net|jobvite\.com|smartrecruiters\.com|"
    r"lever\.co|breezy\.hr|workable\.com)",
    re.I,
)


def _normalize_url(url: str) -> str:
    """Normalize URL by adding scheme if missing.
    
    Examples:
        'example.com' → 'https://example.com'
        'https://example.com' → 'https://example.com' (unchanged)
        '//example.com' → 'https://example.com'
    """
    url = url.strip()
    # Already has a scheme
    if "://" in url:
        return url
    # Protocol-relative URL
    if url.startswith("//"):
        return f"https:{url}"
    # No scheme — add https
    return f"https://{url}"


async def find_careers_url(url: str) -> str:
    """Return the best careers URL for the given company URL."""
    # Normalize URL first
    url = _normalize_url(url)
    
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")
    
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Already pointing at an ATS board or a careers-looking path
    if _ATS_DOMAINS.search(url) or _ALREADY_CAREERS.search(parsed.path):
        logger.info("URL already looks like a careers page: %s", url)
        return url

    # Probe common paths with a lightweight HEAD/GET check
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            for path in _COMMON_PATHS:
                candidate = urljoin(base, path)
                try:
                    resp = await client.head(candidate)
                    if resp.status_code < 400:
                        logger.info("Found careers page via path probe: %s", candidate)
                        return str(resp.url)  # follow any redirect
                except Exception:
                    continue

            # Fallback: fetch homepage and scan links
            try:
                resp = await client.get(base, timeout=15)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                candidates: list[tuple[int, str]] = []

                for a in soup.find_all("a", href=True):
                    href: str = a["href"]
                    text: str = a.get_text(strip=True)
                    combined = href + " " + text

                    if not _CAREERS_PATTERNS.search(combined):
                        continue

                    # Resolve relative URLs
                    full = href if href.startswith("http") else urljoin(base, href)
                    # Score: prefer links that stay on the same domain
                    score = 2 if urlparse(full).netloc == parsed.netloc else 1
                    # Bonus for exact /careers or /jobs
                    if re.search(r"/(careers?|jobs?)/?$", full, re.I):
                        score += 2
                    candidates.append((score, full))

                if candidates:
                    best = sorted(candidates, key=lambda x: -x[0])[0][1]
                    logger.info("Found careers page via homepage link scan: %s", best)
                    return best
            except Exception as exc:
                logger.warning("Homepage scan failed for %s: %s", base, exc)
    except Exception as exc:
        logger.warning("Error fetching homepage for %s: %s", base, exc)

    # Nothing found — return the normalized careers URL
    logger.warning("Could not discover careers page for %s, using base URL", base)
    return base
