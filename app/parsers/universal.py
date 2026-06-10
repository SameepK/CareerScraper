"""
Universal job listing parser — works on any ATS without per-site CSS knowledge.

Algorithm
─────────
1. Remove noise tags (nav, footer, script…).
2. Find every <a href> that looks like a job detail URL (numeric ID, UUID,
   or /job(s)/ path segment).
3. Group anchors by URL-base pattern; require ≥ MIN_JOBS matches to filter
   out single stray links.
4. For each anchor, walk up the DOM to find the smallest container that holds
   meaningful text beyond the link itself — that container is the "job card."
5. Extract title = the most prominent text node in the card that isn't "Apply"
   or other nav noise.
6. Extract location = any text matching location heuristics.
7. Fall back to scanning ALL anchors on the page if step 2 finds nothing.
"""
import re
from collections import defaultdict
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from app.models.job import JobListing

# ── Noise removal ──────────────────────────────────────────────────────────────
_NOISE_TAGS = {"script", "style", "noscript", "nav", "header", "footer",
               "aside", "form", "iframe"}

# ── Job-detail URL patterns ────────────────────────────────────────────────────
# Matches URLs that look like individual job postings across any ATS
_JOB_URL_RE = re.compile(
    r"(/jobs?/|/careers?/|/openings?/|/positions?/|/apply/|"
    r"/job-detail|/JobDetail|/requisition)"
    r"|[/_-]\d{5,}"          # numeric ID ≥ 5 digits
    r"|[/_][a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",  # UUID
    re.I,
)

# ── Navigation / button noise in anchor text ──────────────────────────────────
_NAV_NOISE_RE = re.compile(
    r"^(apply(\s+now)?|learn\s+more|view|see\s+job|open\s+role|→|>|details?|"
    r"read\s+more|click\s+here|more\s+info|submit|get\s+started|save|"
    r"save\s+job|bookmark|share|refer|referral)$",
    re.I,
)

# ── Location heuristics ────────────────────────────────────────────────────────
_LOCATION_CLASS_RE = re.compile(r"location|city|region|locale|office|geo", re.I)
_LOCATION_TEXT_RE = re.compile(
    r"\b(remote|hybrid|on.?site|san francisco|new york|london|berlin|toronto|"
    r"seattle|boston|chicago|los angeles|austin|singapore|tokyo|paris|"
    r"amsterdam|sydney|bangalore|dublin|denver|atlanta|united states|usa|"
    r"u\.s\.|canada|europe|apac|emea|latam|worldwide|global)\b",
    re.I,
)

_MIN_JOBS = 2          # need at least this many job links to trust a pattern
_MAX_TITLE_LEN = 120   # titles longer than this are probably scraped garbage


def _resolve(base: str, href: str) -> str:
    if href.startswith("http"):
        return href
    return urljoin(base, href)


def _url_base_pattern(href: str) -> str:
    """Return the common URL prefix for grouping job links.

    Strips the last path segment (the unique job ID/slug) so that all jobs
    under the same board group together regardless of their individual slugs.
    For deeper paths like /careers/JobDetail/Slug/ID we strip the last two
    segments so Bloomberg-style URLs (/careers/JobDetail/*) still group.
    """
    parsed = urlparse(href)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return href
    # Keep up to 2 path segments, always dropping the final one (the ID)
    depth = min(len(parts) - 1, 2)
    base_path = "/" + "/".join(parts[:depth]) if depth else "/"
    return f"{parsed.scheme}://{parsed.netloc}{base_path}" if parsed.netloc else base_path


def _is_job_url(href: str, base_domain: str) -> bool:
    parsed = urlparse(href)
    # Allow same-domain relative links and matching-domain absolute links
    if parsed.netloc and parsed.netloc != base_domain:
        return False
    return bool(_JOB_URL_RE.search(href))


def _extract_title(card: Tag, anchor: Tag) -> str:
    """
    Find the best title text in a card element.
    Priority: heading tags > anchor text > first substantial child text.
    """
    # 1. Heading inside the card
    for tag in ("h1", "h2", "h3", "h4"):
        h = card.find(tag)
        if h:
            t = h.get_text(strip=True)
            if t and not _NAV_NOISE_RE.match(t) and len(t) <= _MAX_TITLE_LEN:
                return t

    # 2. Anchor text itself (if it's not navigation noise)
    anchor_text = anchor.get_text(separator=" ", strip=True)
    if anchor_text and not _NAV_NOISE_RE.match(anchor_text) and len(anchor_text) <= _MAX_TITLE_LEN:
        return anchor_text

    # 3. First non-noise text node in the card
    for child in card.descendants:
        if isinstance(child, NavigableString):
            t = child.strip()
            if t and not _NAV_NOISE_RE.match(t) and len(t) > 4 and len(t) <= _MAX_TITLE_LEN:
                return t

    return ""


def _extract_location(card: Tag) -> str:
    """Extract a location string from a job card."""
    # 1. Element whose class/id name contains location-related keywords
    loc_el = card.find(
        lambda t: isinstance(t, Tag) and bool(
            _LOCATION_CLASS_RE.search(" ".join(t.get("class", [])) + t.get("id", ""))
        )
    )
    if loc_el:
        return loc_el.get_text(strip=True)

    # 2. Any text node that looks like a location
    for el in card.find_all(["span", "p", "div", "li"], recursive=True):
        t = el.get_text(strip=True)
        if t and _LOCATION_TEXT_RE.search(t) and len(t) < 80:
            return t

    return ""


def _find_card(anchor: Tag) -> Tag:
    """
    Walk up the DOM from the anchor to find the smallest container that
    holds meaningful context (title text beyond the anchor itself).
    Stops at the first container that has either a heading OR at least one
    sibling element with text (covers <p>-based layouts like Aurora).
    """
    _STOP_TAGS = {"body", "main", "section", "article", "ul", "ol", "table",
                  "tbody", "thead", "html"}
    node = anchor.parent
    while node and isinstance(node, Tag):
        if node.name in _STOP_TAGS:
            break
        # Stop if there's a heading inside
        if node.find(["h1", "h2", "h3", "h4"]):
            return node
        # Stop if there's at least one sibling element with distinct text
        # (e.g. Aurora's <p class="...heading"> sitting next to the Apply link)
        siblings_with_text = [
            c for c in node.children
            if isinstance(c, Tag) and c is not anchor and c.get_text(strip=True)
        ]
        if siblings_with_text:
            return node
        node = node.parent
    return anchor.parent if isinstance(anchor.parent, Tag) else anchor


def parse(html: str, base_url: str) -> list[JobListing]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    base_domain = urlparse(base_url).netloc
    all_anchors: list[Tag] = [
        a for a in soup.find_all("a", href=True)
        if _is_job_url(a["href"], base_domain)
    ]

    # ── Group anchors by URL base pattern ─────────────────────────────────────
    pattern_groups: dict[str, list[Tag]] = defaultdict(list)
    for a in all_anchors:
        pattern_groups[_url_base_pattern(a["href"])].append(a)

    # Keep only patterns with enough links; pick the largest group
    candidates = sorted(
        [(pat, anchors) for pat, anchors in pattern_groups.items() if len(anchors) >= _MIN_JOBS],
        key=lambda x: len(x[1]),
        reverse=True,
    )

    # Use all anchors from the best group(s) that share the same top-level base
    target_anchors: list[Tag] = []
    if candidates:
        best_base = _url_base_pattern(candidates[0][0])
        for pat, anchors in candidates:
            if _url_base_pattern(pat) == best_base or len(candidates) == 1:
                target_anchors.extend(anchors)
    else:
        # No pattern found — try all job-url anchors
        target_anchors = all_anchors

    if not target_anchors:
        return []

    seen: set[str] = set()
    jobs: list[JobListing] = []

    for anchor in target_anchors:
        href = _resolve(base_url, anchor["href"])
        url = href.split("?")[0].rstrip("/")
        if url in seen:
            continue
        seen.add(url)

        card = _find_card(anchor)
        title = _extract_title(card, anchor)
        if not title:
            continue

        location = _extract_location(card)
        jobs.append(JobListing(title=title, description="", location=location, url=url))

    return jobs
