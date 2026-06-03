"""Heuristic extractor for unknown job sites."""
import re
from bs4 import BeautifulSoup, Tag
from app.models.job import JobListing

# Signals that an element is a job title
_TITLE_PATTERNS = re.compile(
    r"(job.?title|position|role|opening|posting|career)", re.I
)
_LOCATION_PATTERNS = re.compile(r"(location|city|region|remote|office)", re.I)
_SKIP_TAGS = {"script", "style", "noscript", "header", "footer", "nav"}

# Common containers used by job boards
_CARD_SELECTORS = [
    "li[class*='job']",
    "div[class*='job']",
    "article[class*='job']",
    "tr[class*='job']",
    "li[class*='position']",
    "div[class*='position']",
    "li[class*='opening']",
    "div[class*='opening']",
    "div[class*='posting']",
]


def _best_text(el: Tag) -> str:
    return el.get_text(separator=" ", strip=True)


def parse(html: str, base_url: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_SKIP_TAGS):
        tag.decompose()

    jobs: list[JobListing] = []

    # Try structured card selectors first
    cards: list[Tag] = []
    for sel in _CARD_SELECTORS:
        cards = soup.select(sel)
        if len(cards) >= 2:
            break

    for card in cards:
        a = card.find("a", href=True)
        if not a:
            continue
        title = _best_text(a) or _best_text(card)
        href: str = a["href"]
        url = href if href.startswith("http") else _resolve(base_url, href)

        loc_el = card.find(
            lambda t: t.name in ("span", "div", "p")
            and _LOCATION_PATTERNS.search(" ".join(t.get("class", [])) + t.get("id", "")),
        )
        location = _best_text(loc_el) if loc_el else ""
        jobs.append(JobListing(title=title, description="", location=location, url=url))

    if jobs:
        return jobs

    # Last resort: grab the page as a single listing
    title_el = (
        soup.find("h1")
        or soup.find("h2")
    )
    desc_el = soup.find("main") or soup.find("article") or soup.body
    title = _best_text(title_el) if title_el else "Unknown Position"
    description = _best_text(desc_el)[:2000] if desc_el else ""
    jobs.append(JobListing(title=title, description=description, location="", url=base_url))
    return jobs


def _resolve(base: str, href: str) -> str:
    from urllib.parse import urljoin
    return urljoin(base, href)
