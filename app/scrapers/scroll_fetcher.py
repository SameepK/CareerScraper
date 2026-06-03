"""Scroll-based fetcher for infinite-scroll job boards (e.g. Oracle HCM).

Uses Scrapling's DynamicFetcher with a page_action that scrolls until no
new job tiles appear, collecting the full rendered HTML.
"""
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

_JOB_TILE_SELECTOR = "div.job-tile"
_MAX_SCROLL_ROUNDS = 30       # safety cap (~750 jobs at 25/scroll)
_SCROLL_PAUSE_MS   = 3500     # wait after each scroll for XHR to complete


def _make_scroll_action(tile_selector: str) -> Callable:
    """Return an async page_action that scrolls until no new tiles appear."""
    async def scroll_all(page) -> None:
        prev_count = 0
        for _ in range(_MAX_SCROLL_ROUNDS):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(_SCROLL_PAUSE_MS)
            count = await page.evaluate(
                f"document.querySelectorAll('{tile_selector}').length"
            )
            logger.debug("Scroll round: %d tiles", count)
            if count == prev_count:
                break
            prev_count = count
        logger.info("Scroll complete: %d tiles loaded", prev_count)
    return scroll_all


async def fetch_all_jobs_html(url: str) -> str:
    """Fetch *url* with auto-scroll to load all infinite-scroll job listings."""
    from scrapling.fetchers import AsyncDynamicSession

    async with AsyncDynamicSession(headless=True, network_idle=True) as session:
        page_response = await session.fetch(
            url,
            page_action=_make_scroll_action(_JOB_TILE_SELECTOR),
            network_idle=True,
        )

    if page_response is None or page_response.status not in range(200, 300):
        raise RuntimeError(
            f"scroll_fetcher failed for {url} "
            f"(status {getattr(page_response, 'status', '?')})"
        )

    html = str(page_response.html_content)
    if not html:
        body = page_response.body
        html = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)

    logger.info("scroll_fetcher: %d bytes for %s", len(html), url)
    return html
