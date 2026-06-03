"""Fetch full job descriptions for listings that only have a title + URL.

Runs fetches concurrently (capped at MAX_CONCURRENT) using the lightweight
`scrapling extract get` command — no browser needed for individual job pages.
Falls back gracefully: if a fetch fails the job is kept with empty description.
"""
import asyncio
import logging
import re
from bs4 import BeautifulSoup

from app.models.job import JobListing
from app.scrapers.fetcher import _run_scrapling   # reuse the CLI runner

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 8        # parallel fetches at once
MAX_DESC_CHARS = 4000     # cap description length passed to scorer

# ── Per-ATS description selectors ─────────────────────────────────────────────
# Tried in order; first non-empty match wins.
_SELECTORS: dict[str, list[str]] = {
    "greenhouse": [
        "#content #app_body",
        "#content .section",
        "#app_body",
        ".job-post__description",
    ],
    "lever": [
        "div.content",
        "div.posting-content",
        ".posting-description",
    ],
    "ashby": [
        "div[class*='posting']",
        "div[class*='jobContent']",
        "div[class*='content']",
        "main",
    ],
    "workday": [
        "div[data-automation-id='jobPostingDescription']",
        "div[class*='job-description']",
        "main",
    ],
    "avature": [
        ".article__body",
        "div[class*='job-detail']",
        "main",
    ],
    "oracle_hcm": [
        "div[data-automation-id='richTextDescription']",
        "div[class*='job-description']",
        "main",
    ],
    # generic fallback used for all other ATS values
    "generic": [
        "main",
        "article",
        "div[class*='description']",
        "div[class*='content']",
        "div[class*='job-detail']",
        "div[class*='posting']",
        "section",
        "body",
    ],
}

_NOISE_RE = re.compile(
    r"(apply now|share this job|back to jobs|equal opportunity|"
    r"we are an equal|eeo|accessibility|cookie|privacy policy)",
    re.I,
)


def _extract_description(html: str, ats: str) -> str:
    """Extract the job description text from a detail page HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise elements
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        tag.decompose()

    selectors = _SELECTORS.get(ats, []) + _SELECTORS["generic"]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator=" ", strip=True)
            # Basic quality check: must be substantive
            if len(text) > 150 and not _NOISE_RE.search(text[:100]):
                return text[:MAX_DESC_CHARS]

    return ""


async def _fetch_description(job: JobListing, ats: str, semaphore: asyncio.Semaphore) -> JobListing:
    """Fetch and attach a description to one JobListing. Returns the (possibly enriched) job."""
    async with semaphore:
        try:
            html = await _run_scrapling("get", job.url, ai_targeted=False)
            if not html:
                # Escalate to browser fetch for JS-rendered detail pages
                html = await _run_scrapling("fetch", job.url, ai_targeted=True)
            description = _extract_description(html, ats)
            if description:
                logger.debug("Enriched '%s' (%d chars)", job.title[:40], len(description))
                return JobListing(
                    title=job.title,
                    description=description,
                    location=job.location,
                    url=job.url,
                )
        except Exception as exc:
            logger.warning("Could not fetch description for %s: %s", job.url, exc)
        return job   # return original if fetch failed


async def enrich_descriptions(jobs: list[JobListing], ats: str) -> list[JobListing]:
    """
    Fetch full descriptions for jobs whose description is empty or very short.
    Preserves order. Capped at MAX_CONCURRENT parallel requests.
    """
    needs_fetch = [j for j in jobs if len(j.description.strip()) < 100]
    has_desc    = {j.url: j for j in jobs if len(j.description.strip()) >= 100}

    if not needs_fetch:
        logger.info("All %d jobs already have descriptions — skipping enrichment", len(jobs))
        return jobs

    logger.info(
        "Enriching %d/%d jobs without descriptions (ATS=%s, concurrency=%d)",
        len(needs_fetch), len(jobs), ats, MAX_CONCURRENT,
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [_fetch_description(j, ats, semaphore) for j in needs_fetch]
    enriched = await asyncio.gather(*tasks)

    # Rebuild list preserving original order
    enriched_map = {j.url: j for j in enriched}
    return [
        enriched_map.get(j.url) or has_desc.get(j.url) or j
        for j in jobs
    ]
