"""Parser for Workday job boards (*.myworkdayjobs.com)."""
from bs4 import BeautifulSoup
from app.models.job import JobListing


def parse(html: str, base_url: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobListing] = []

    # Workday renders job titles in <a data-automation-id="jobTitle">
    for a in soup.select("a[data-automation-id='jobTitle']"):
        title = a.get_text(strip=True)
        href: str = a.get("href", "")
        url = href if href.startswith("http") else _resolve(base_url, href)

        # Location lives in a sibling <dd data-automation-id="locations"> or nearby
        container = a.find_parent("li") or a.find_parent("div")
        loc_el = None
        if container:
            loc_el = container.select_one(
                "dd[data-automation-id='locations'], "
                "dl[data-automation-id='workerSubType'], "
                "span[class*='location']"
            )
        location = loc_el.get_text(strip=True) if loc_el else ""
        jobs.append(JobListing(title=title, description="", location=location, url=url))

    # Fallback: some Workday embeds use <li class="...GJOF..."> (obfuscated CSS)
    if not jobs:
        for li in soup.select("li[class]"):
            a = li.select_one("a[href]")
            if not a:
                continue
            title = a.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            href = a["href"]
            url = href if href.startswith("http") else _resolve(base_url, href)
            loc_spans = li.select("span")
            location = loc_spans[-1].get_text(strip=True) if loc_spans else ""
            jobs.append(JobListing(title=title, description="", location=location, url=url))

    # Single job detail page
    if not jobs:
        title_el = soup.select_one("h1[data-automation-id='jobPostingHeader'], h1")
        desc_el = soup.select_one(
            "div[data-automation-id='jobPostingDescription'], "
            "div[class*='job-description'], main"
        )
        loc_el = soup.select_one("span[data-automation-id='location'], dd[data-automation-id='locations']")
        if title_el:
            jobs.append(JobListing(
                title=title_el.get_text(strip=True),
                description=desc_el.get_text(separator=" ", strip=True)[:3000] if desc_el else "",
                location=loc_el.get_text(strip=True) if loc_el else "",
                url=base_url,
            ))

    return jobs


def _resolve(base: str, href: str) -> str:
    from urllib.parse import urljoin
    return urljoin(base, href)
