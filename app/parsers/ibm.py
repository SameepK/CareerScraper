"""Parser for IBM Careers (Phenom People ATS at careers.ibm.com)."""
from bs4 import BeautifulSoup
from app.models.job import JobListing


def parse(html: str, base_url: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobListing] = []

    for card in soup.select("article.article--card"):
        # Title + URL
        a = card.select_one("h3.article__header__text__title a.link")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        url = href if href.startswith("http") else f"https://careers.ibm.com{href}"

        # Location
        loc_el = card.select_one("span.card-item-location")
        location = loc_el.get_text(strip=True) if loc_el else ""

        jobs.append(JobListing(title=title, description="", location=location, url=url))

    return jobs
