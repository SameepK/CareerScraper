"""Paginating fetcher for IBM Careers (careers.ibm.com / Phenom People ATS).

IBM paginates via a "Next >>" link (paginationNextLink). We follow that link
sequentially until it disappears, collecting all article cards into one document.
"""
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from bs4 import BeautifulSoup
from scrapling.fetchers import AsyncDynamicSession

logger = logging.getLogger(__name__)

_MAX_PAGES = 100   # safety cap (~900 jobs)


def _strip_fragment(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(fragment=""))


def _next_url(soup: BeautifulSoup) -> str | None:
    """Return the href of the Next page link, or None if we're on the last page."""
    link = soup.select_one("a.paginationNextLink")
    return link["href"] if link else None


async def fetch_all_pages_html(url: str) -> str:
    """Fetch every page of IBM job results and return concatenated article cards."""
    current_url = _strip_fragment(url)
    all_cards: list[str] = []
    page_num = 0

    async with AsyncDynamicSession(headless=True, network_idle=True) as session:
        while current_url and page_num < _MAX_PAGES:
            resp = await session.fetch(current_url, network_idle=True)
            if resp is None or resp.status not in range(200, 300):
                logger.warning("IBM fetcher: page %d returned status %s", page_num + 1, getattr(resp, "status", "?"))
                break

            html = str(resp.html_content)
            soup = BeautifulSoup(html, "html.parser")

            cards = soup.select("article.article--card")
            logger.debug("IBM fetcher: page %d — %d cards", page_num + 1, len(cards))
            for card in cards:
                all_cards.append(str(card))

            current_url = _next_url(soup)
            page_num += 1

    logger.info("IBM fetcher: %d total job cards across %d pages", len(all_cards), page_num)
    return f"<html><body>{''.join(all_cards)}</body></html>"
