"""Parser for Ashby job boards (*.ashbyhq.com).

Live board structure (confirmed against jobs.ashbyhq.com):
  <a class="_container_j2da7_1" href="/COMPANY/UUID">
    <div class="ashby-job-posting-brief ...">
      <h3 class="ashby-job-posting-brief-title">Job Title</h3>
      <div class="ashby-job-posting-brief-details"><p>Dept • Location • Type</p></div>
    </div>
  </a>
"""
from bs4 import BeautifulSoup
from app.models.job import JobListing


def parse(html: str, base_url: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobListing] = []

    # Board listing: stable Ashby semantic class names (ashby-job-posting-brief-*)
    for card in soup.select("div.ashby-job-posting-brief"):
        title_el = card.select_one(".ashby-job-posting-brief-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)

        # The <a> wrapping the card contains the relative href
        a = card.find_parent("a", href=True)
        if not a:
            a = card.select_one("a[href]")
        href: str = a["href"] if a else ""
        url = href if href.startswith("http") else _resolve(base_url, href)

        # Details line: "Dept • Location • Type • Work arrangement"
        details_el = card.select_one(".ashby-job-posting-brief-details")
        location = _extract_location(details_el.get_text(strip=True) if details_el else "")

        jobs.append(JobListing(title=title, description="", location=location, url=url))

    # Single job detail page fallback
    if not jobs:
        title_el = soup.select_one("h1")
        desc_el = soup.select_one("div[class*='posting'], main, article")
        loc_el = soup.select_one(".ashby-job-posting-brief-details, span[class*='location']")
        if title_el:
            jobs.append(JobListing(
                title=title_el.get_text(strip=True),
                description=desc_el.get_text(separator=" ", strip=True)[:3000] if desc_el else "",
                location=_extract_location(loc_el.get_text(strip=True) if loc_el else ""),
                url=base_url,
            ))

    return jobs


def _extract_location(details: str) -> str:
    """Pull the location segment from 'Dept • Location • Type' style strings."""
    parts = [p.strip() for p in details.replace("•", "·").split("·")]
    # Location is typically the second segment (index 1)
    if len(parts) >= 2:
        return parts[1]
    return details


def _resolve(base: str, href: str) -> str:
    from urllib.parse import urljoin
    return urljoin(base, href)
