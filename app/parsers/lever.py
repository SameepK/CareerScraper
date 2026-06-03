"""Parser for Lever job boards (jobs.lever.co)."""
from bs4 import BeautifulSoup
from app.models.job import JobListing


def parse(html: str, base_url: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobListing] = []

    # Board listing page
    for posting in soup.select("div.posting"):
        a = posting.select_one("a.posting-title[href]")
        if not a:
            continue
        title_el = a.select_one("h5")
        title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
        url = a["href"]
        loc_el = posting.select_one(".location, .sort-by-location")
        location = loc_el.get_text(strip=True) if loc_el else ""
        jobs.append(JobListing(title=title, description="", location=location, url=url))

    # Single posting detail page
    if not jobs:
        title_el = soup.select_one("div.posting-headline h2")
        desc_el = soup.select_one("div.content")
        loc_el = soup.select_one("div.posting-categories .location")
        if title_el:
            jobs.append(JobListing(
                title=title_el.get_text(strip=True),
                description=desc_el.get_text(separator=" ", strip=True) if desc_el else "",
                location=loc_el.get_text(strip=True) if loc_el else "",
                url=base_url,
            ))

    return jobs
