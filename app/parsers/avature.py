"""Parser for Avature job boards (*.avature.net).

Live board structure (confirmed against bloomberg.avature.net):
  <article class="article article--result">
    <div class="article__header">
      <h3 class="article__header__text__title">
        <a class="link" href="https://...avature.net/careers/JobDetail/...">Job Title</a>
      </h3>
      <div class="article__header__text__subtitle">
        <span class="list-item-location">City, Country</span>
      </div>
    </div>
  </article>
"""
from bs4 import BeautifulSoup
from app.models.job import JobListing


def parse(html: str, base_url: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobListing] = []

    for card in soup.select("article.article--result"):
        a = card.select_one("h3 a.link[href], .article__header__text__title a[href]")
        if not a:
            continue
        title = a.get_text(strip=True)
        url: str = a["href"]
        if not url.startswith("http"):
            from urllib.parse import urljoin
            url = urljoin(base_url, url)

        loc_el = card.select_one(".list-item-location, .article__header__text__subtitle span")
        location = loc_el.get_text(strip=True) if loc_el else ""

        jobs.append(JobListing(title=title, description="", location=location, url=url))

    # Single job detail page fallback
    if not jobs:
        title_el = soup.select_one("h1.title, h1")
        desc_el = soup.select_one(".article__body, main, article")
        loc_el = soup.select_one(".list-item-location, .job-location")
        if title_el:
            jobs.append(JobListing(
                title=title_el.get_text(strip=True),
                description=desc_el.get_text(separator=" ", strip=True)[:3000] if desc_el else "",
                location=loc_el.get_text(strip=True) if loc_el else "",
                url=base_url,
            ))

    return jobs
