"""Parser for Oracle HCM job boards (*.fa.oraclecloud.com/hcmUI/CandidateExperience).

Live board structure (confirmed against jpmc.fa.oraclecloud.com):
  <div class="job-tile ...">
    <a class="job-grid-item__link" href="https://.../job/ID/...">
    <span class="job-tile__title">Job Title</span>
    <li class="job-list-item__job-info-item">
      <div aria-label="Locations">City, State, Country</div>
    </li>
  </div>
"""
from bs4 import BeautifulSoup
from app.models.job import JobListing


def parse(html: str, base_url: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobListing] = []

    for tile in soup.select("div.job-tile"):
        title_el = tile.select_one("span.job-tile__title, [class*='job-tile__title']")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        a = tile.select_one("a.job-grid-item__link[href], a[href*='/job/']")
        url = a["href"] if a else base_url
        if url and not url.startswith("http"):
            from urllib.parse import urljoin
            url = urljoin(base_url, url)

        # Location: try aria-label first, then fall back to first info-item text
        location = ""
        info_items = tile.select("li.job-list-item__job-info-item")
        for li in info_items:
            loc_el = li.select_one("[aria-label='Locations']")
            if loc_el:
                location = loc_el.get_text(strip=True)
                break
        if not location and info_items:
            location = info_items[0].get_text(strip=True)

        # Description: pull the short summary if present
        desc_el = tile.select_one("[class*='job-tile__description'], [class*='job-description']")
        description = desc_el.get_text(strip=True) if desc_el else ""

        jobs.append(JobListing(title=title, description=description, location=location, url=url))

    # Single job detail page fallback
    if not jobs:
        title_el = soup.select_one("h1[class*='job-title'], h1")
        desc_el = soup.select_one("[class*='job-description'], main")
        loc_el = soup.select_one("[aria-label='Locations'], [class*='location']")
        if title_el:
            jobs.append(JobListing(
                title=title_el.get_text(strip=True),
                description=desc_el.get_text(separator=" ", strip=True)[:3000] if desc_el else "",
                location=loc_el.get_text(strip=True) if loc_el else "",
                url=base_url,
            ))

    return jobs
