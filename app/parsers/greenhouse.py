"""Parser for Greenhouse job boards (boards.greenhouse.io and job-boards.greenhouse.io)."""
from bs4 import BeautifulSoup
from app.models.job import JobListing


def parse(html: str, base_url: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobListing] = []

    # ── Format A: job-boards.greenhouse.io  (<tr class="job-post">) ───────────
    for row in soup.select("tr.job-post"):
        a = row.select_one("a[href]")
        if not a:
            continue
        href = a["href"]
        url = href if href.startswith("http") else f"https://job-boards.greenhouse.io{href}"
        paras = a.select("p")
        title = paras[0].get_text(strip=True) if paras else a.get_text(strip=True)
        location = paras[1].get_text(strip=True) if len(paras) > 1 else ""
        jobs.append(JobListing(title=title, description="", location=location, url=url))

    if jobs:
        return jobs

    # ── Format B: boards.greenhouse.io  (<section.level-0> / <div.opening>) ───
    for section in soup.select("section.level-0"):
        for item in section.select("div.opening"):
            a = item.select_one("a[href]")
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a["href"]
            url = href if href.startswith("http") else f"https://boards.greenhouse.io{href}"
            location_el = item.select_one(".location")
            location = location_el.get_text(strip=True) if location_el else ""
            jobs.append(JobListing(title=title, description="", location=location, url=url))

    # Single job detail page (when scraping a specific listing)
    if not jobs:
        title_el = soup.select_one("#header h1.app-title, #app_body h1")
        desc_el = soup.select_one("#content div#app_body, #content .section")
        loc_el = soup.select_one(".location")
        if title_el:
            jobs.append(JobListing(
                title=title_el.get_text(strip=True),
                description=desc_el.get_text(separator=" ", strip=True) if desc_el else "",
                location=loc_el.get_text(strip=True) if loc_el else "",
                url=base_url,
            ))

    return jobs
