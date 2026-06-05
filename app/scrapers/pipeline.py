"""Orchestrate careers discovery → fetch → detect → parse into JobListings."""
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Tag
from app.scrapers.fetcher import fetch_html
from app.scrapers.careers_finder import find_careers_url
from app.scrapers.ats_detector import detect_ats, ATS
from app.models.job import JobListing

# ── Iframe embed patterns ──────────────────────────────────────────────────────
_IFRAME_PATTERNS = [
    (re.compile(r'src="(https://jobs\.ashbyhq\.com/[^"?]+)', re.I),          ATS.ASHBY),
    (re.compile(r'src="(https://(?:job-boards|boards)\.greenhouse\.io/[^"?]+)', re.I), ATS.GREENHOUSE),
    (re.compile(r'src="(https://jobs\.lever\.co/[^"?]+)', re.I),              ATS.LEVER),
    (re.compile(r'src="(https://[^"]*myworkdayjobs\.com/[^"?]+)', re.I),      ATS.WORKDAY),
    (re.compile(r'src="(https://[^"]*avature\.net/[^"?]+)', re.I),            ATS.AVATURE),
    (re.compile(r'src="(https://[^"]*fa\.oraclecloud\.com/[^"?]+)', re.I),    ATS.ORACLE_HCM),
]

# ── Direct <a href> link patterns ─────────────────────────────────────────────
# Matches job-specific URLs (not just ATS homepages) so we don't false-positive
# on marketing pages that mention ATS names in blog posts etc.
_DIRECT_LINK_PATTERNS: list[tuple[re.Pattern, ATS]] = [
    # Greenhouse  /company/jobs/12345  (both boards. and job-boards. subdomains)
    (re.compile(r'https://(?:job-boards|boards)\.greenhouse\.io/[^/\s"\']+/jobs/\d+', re.I), ATS.GREENHOUSE),
    # Lever       /company/uuid
    (re.compile(r'https://jobs\.lever\.co/[^/\s"\']+/[a-f0-9-]{36}', re.I),        ATS.LEVER),
    # Ashby       /company/uuid
    (re.compile(r'https://jobs\.ashbyhq\.com/[^/\s"\']+/[a-f0-9-]{36}', re.I),     ATS.ASHBY),
    # Workday     /en-US/company/job/city/title/jobId
    (re.compile(r'https://[^/\s"\']+myworkdayjobs\.com/[^\s"\']+/job/', re.I),      ATS.WORKDAY),
    # Avature     /careers/JobDetail/title/id
    (re.compile(r'https://[^/\s"\']+avature\.net/[^\s"\']+/JobDetail/', re.I),      ATS.AVATURE),
    # Oracle HCM  /hcmUI/.../job/id
    (re.compile(r'https://[^/\s"\']+fa\.oraclecloud\.com/hcmUI/[^\s"\']+/job/\d+', re.I), ATS.ORACLE_HCM),
    # Jobvite
    (re.compile(r'https://jobs\.jobvite\.com/[^/\s"\']+/job/[^\s"\']+', re.I),      ATS.GENERIC),
    # SmartRecruiters
    (re.compile(r'https://careers\.smartrecruiters\.com/[^/\s"\']+/[^\s"\']+', re.I), ATS.GENERIC),
    # Workable
    (re.compile(r'https://apply\.workable\.com/[^/\s"\']+/j/[A-Z0-9]+', re.I),     ATS.GENERIC),
    # BambooHR
    (re.compile(r'https://[^/\s"\']+bamboohr\.com/careers/[^\s"\']+', re.I),        ATS.GENERIC),
    # Rippling
    (re.compile(r'https://ats\.rippling\.com/[^/\s"\']+/jobs/[^\s"\']+', re.I),     ATS.GENERIC),
    # Breezy
    (re.compile(r'https://[^/\s"\']+breezy\.hr/p/[^\s"\']+', re.I),                ATS.GENERIC),
]

# ── Self-hosted custom careers page pattern ────────────────────────────────────
# Companies like Linear host their own page at /careers with relative links
# to /careers/UUID (same domain). We detect this by counting relative UUID hrefs.
_UUID_RE = re.compile(r'^/[^/]+/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', re.I)

# Minimum matching links to trust the detection
_MIN_DIRECT_LINKS = 3

# ── Fetch strategies ───────────────────────────────────────────────────────────
_SCROLL_ATS       = {ATS.ORACLE_HCM}
_SPA_ATS          = {ATS.ASHBY, ATS.WORKDAY, ATS.ORACLE_HCM}
_NO_AI_TARGET_ATS = {ATS.ORACLE_HCM}
_PAGINATE_ATS     = {ATS.IBM}

# Heading tags used for department / location grouping above job lists
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

# Keywords that indicate a heading is a location rather than a department
_LOCATION_HINTS = re.compile(
    r"\b(remote|hybrid|office|san francisco|new york|london|berlin|toronto|"
    r"austin|seattle|boston|chicago|los angeles|singapore|tokyo|paris|"
    r"amsterdam|sydney|bangalore|dublin|tel aviv|vancouver|denver|atlanta|"
    r"united states|usa|uk|canada|europe|apac|emea|latam|worldwide|global)\b",
    re.I,
)


def _nearest_heading(tag: Tag, soup: BeautifulSoup) -> str:
    """
    Walk backwards through siblings and ancestors to find the nearest heading
    that acts as a section label (department or location) for this tag.
    """
    # Search previous siblings first
    for sib in tag.find_previous_siblings():
        if not isinstance(sib, Tag):
            continue
        if sib.name in _HEADING_TAGS:
            return sib.get_text(strip=True)
        # Heading nested inside a sibling container
        h = sib.find(_HEADING_TAGS)
        if h:
            return h.get_text(strip=True)

    # Walk up ancestors
    for ancestor in tag.parents:
        if not isinstance(ancestor, Tag):
            continue
        for sib in ancestor.find_previous_siblings():
            if not isinstance(sib, Tag):
                continue
            if sib.name in _HEADING_TAGS:
                return sib.get_text(strip=True)
            h = sib.find(_HEADING_TAGS)
            if h:
                return h.get_text(strip=True)

    return ""


def _find_embedded_ats(html: str) -> tuple[str, ATS] | None:
    """Detect a known ATS board embedded via <iframe src="...">."""
    for pattern, ats in _IFRAME_PATTERNS:
        m = pattern.search(html)
        if m:
            url = m.group(1)
            if ats == ATS.ASHBY:
                url = re.sub(r"/embed$", "", url)
            return url, ats
    return None


def _extract_job_from_anchor(a: Tag, base_url: str, soup: BeautifulSoup) -> JobListing | None:
    """Extract title, location, and URL from a structured job anchor element."""
    href: str = a["href"]

    # Resolve relative URLs
    if href.startswith("/"):
        parsed = urlparse(base_url)
        href = f"{parsed.scheme}://{parsed.netloc}{href}"
    href = href.split("?")[0].rstrip("/")

    # ── Title extraction ──────────────────────────────────────────
    # Strategy: look for the first non-empty text span/div in the anchor,
    # ignoring "Learn more", "→", and other navigation noise.
    _NAV_NOISE = re.compile(r'^(learn\s*more|apply|→|>|view|see\s*job|open\s*role)$', re.I)

    title = ""
    # Try structured children first (e.g. Linear's rowLeft > span)
    children = list(a.find_all(["span", "div", "p"], recursive=True))
    for el in children:
        txt = el.get_text(strip=True)
        if txt and not _NAV_NOISE.match(txt) and len(txt) > 3:
            title = txt
            break
    if not title:
        title = a.get_text(strip=True)
        # Strip trailing nav noise
        title = re.sub(r'[\s→>]+(?:learn\s*more|apply|view)?$', '', title, flags=re.I).strip()
    if not title:
        return None

    # ── Location extraction ───────────────────────────────────────
    location = ""
    # 1. Look for a child element with "location" in its class name
    loc_el = a.find(lambda t: isinstance(t, Tag) and bool(
        re.search(r'location|city|region', " ".join(t.get("class", [])), re.I)
    ))
    if loc_el:
        location = loc_el.get_text(strip=True)

    # 2. Fallback: second non-noise child element (many layouts: [title div][location div])
    if not location and len(children) >= 2:
        for el in children[1:]:
            txt = el.get_text(strip=True)
            if txt and txt != title and not _NAV_NOISE.match(txt) and len(txt) > 1:
                # Only treat as location if it looks like one
                if _LOCATION_HINTS.search(txt) or len(txt) < 40:
                    location = txt
                    break

    # 3. Fallback: nearest heading if it looks like a location
    if not location:
        heading = _nearest_heading(a, soup)
        if heading and _LOCATION_HINTS.search(heading):
            location = heading

    return JobListing(title=title, description="", location=location, url=href)


def _extract_direct_links(html: str, page_url: str) -> tuple[list[JobListing], ATS] | None:
    """
    Detect and extract jobs from pages that list job links directly in HTML.

    Handles two patterns:
    A) Absolute links to known ATS job URLs  (e.g. Figma → boards.greenhouse.io/...)
    B) Relative links to /path/UUID on the same domain (e.g. Linear → /careers/UUID)
    """
    soup = BeautifulSoup(html, "html.parser")
    all_anchors: list[Tag] = soup.find_all("a", href=True)

    # ── Pattern A: absolute ATS links ────────────────────────────────────────
    for pattern, ats in _DIRECT_LINK_PATTERNS:
        matching = [a for a in all_anchors if pattern.search(a["href"])]
        if len(matching) < _MIN_DIRECT_LINKS:
            continue

        seen: set[str] = set()
        jobs: list[JobListing] = []
        for a in matching:
            job = _extract_job_from_anchor(a, page_url, soup)
            if job and job.url not in seen:
                seen.add(job.url)
                jobs.append(job)
        if jobs:
            return jobs, ats

    # ── Pattern B: relative /path/UUID links (self-hosted custom pages) ───────
    matching_rel = [a for a in all_anchors if _UUID_RE.match(a["href"])]
    if len(matching_rel) >= _MIN_DIRECT_LINKS:
        seen = set()
        jobs = []
        for a in matching_rel:
            job = _extract_job_from_anchor(a, page_url, soup)
            if job and job.url not in seen:
                seen.add(job.url)
                jobs.append(job)
        if jobs:
            return jobs, ATS.GENERIC

    return None


async def _fetch_for_ats(url: str, ats: ATS) -> str:
    """Fetch HTML using the right strategy for the given ATS."""
    if ats in _SCROLL_ATS:
        from app.scrapers.scroll_fetcher import fetch_all_jobs_html
        return await fetch_all_jobs_html(url)

    if ats in _PAGINATE_ATS:
        from app.scrapers.ibm_fetcher import fetch_all_pages_html
        return await fetch_all_pages_html(url)

    return await fetch_html(
        url,
        ai_targeted=(ats not in _NO_AI_TARGET_ATS),
        browser=(ats in _SPA_ATS),
    )


async def scrape(url: str) -> tuple[list[JobListing], ATS]:
    # Step 1: resolve any company homepage to its actual careers page
    careers_url = await find_careers_url(url)

    # Step 2: detect ATS from URL
    ats = detect_ats(careers_url)

    # Step 3: for generic pages, inspect HTML for embedded / direct-linked ATS boards
    if ats == ATS.GENERIC:
        raw_html = await fetch_html(careers_url, ai_targeted=False, browser=False)

        # 3a: iframe embed (e.g. Credal → Ashby iframe)
        embedded = _find_embedded_ats(raw_html)
        if embedded:
            careers_url, ats = embedded
        else:
            # 3b: direct ATS job links in the page HTML (e.g. Figma → 159 Greenhouse hrefs)
            direct = _extract_direct_links(raw_html, careers_url)
            if direct:
                return direct  # jobs already extracted, no need for a second fetch

            # 3c: SPA / JS-rendered page — retry with browser to expose dynamic links
            #     (e.g. Affirm: Next.js page that injects job-boards.greenhouse.io hrefs)
            rendered_html = await fetch_html(careers_url, ai_targeted=False, browser=True)
            embedded = _find_embedded_ats(rendered_html)
            if embedded:
                careers_url, ats = embedded
            else:
                direct = _extract_direct_links(rendered_html, careers_url)
                if direct:
                    return direct

    # Step 4: fetch the ATS board and parse it
    html = await _fetch_for_ats(careers_url, ats)

    if ats == ATS.GREENHOUSE:
        from app.parsers.greenhouse import parse
    elif ats == ATS.LEVER:
        from app.parsers.lever import parse
    elif ats == ATS.ASHBY:
        from app.parsers.ashby import parse  # type: ignore[assignment]
    elif ats == ATS.WORKDAY:
        from app.parsers.workday import parse  # type: ignore[assignment]
    elif ats == ATS.AVATURE:
        from app.parsers.avature import parse  # type: ignore[assignment]
    elif ats == ATS.ORACLE_HCM:
        from app.parsers.oracle_hcm import parse  # type: ignore[assignment]
    elif ats == ATS.IBM:
        from app.parsers.ibm import parse  # type: ignore[assignment]
    else:
        from app.parsers.generic import parse  # type: ignore[assignment]

    jobs = parse(html, careers_url)
    return jobs, ats
