"""HTML fetcher using the Scrapling CLI agent.

Strategy (per Scrapling agent skill docs):
  1. scrapling extract get          — fast HTTP, no browser
  2. scrapling extract fetch        — Chromium, for JS-rendered pages
  3. scrapling extract stealthy-fetch — stealth Chromium, for anti-bot sites

Each level is tried only if the previous returns empty or fails.
--ai-targeted cleans hidden elements and extracts main content, reducing noise for parsers.

Important: Custom career pages (React, Vue, Next.js) are detected via SPA indicators
and automatically escalated to browser rendering. This ensures JavaScript-heavy sites
are properly scraped even when initially detected as "generic" HTML.
"""
import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve the scrapling binary: prefer the venv binary, fall back to PATH
# __file__ = app/scrapers/fetcher.py  →  parents[2] = project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRAPLING = str(_PROJECT_ROOT / ".venv" / "bin" / "scrapling")
if not Path(_SCRAPLING).exists():
    _SCRAPLING = shutil.which("scrapling") or "scrapling"

# Content length thresholds
_MIN_CONTENT_LENGTH = 2000          # bytes — error/shell pages are usually <1kb; real pages are larger
_MIN_CONTENT_LENGTH_SPA = 3000      # bytes — SPA/generic sites need more (job data fetched via XHR)
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2  # exponential backoff multiplier

# SPA/JavaScript framework indicators (compiled once)
_SPA_INDICATORS = re.compile(
    r'id\s*=\s*["\'](?:root|app)["\']|'  # React root, Vue app
    r'__NEXT_DATA__|__nuxt__|'              # Next.js, Nuxt markers
    r'<script[^>]*type=["\']application/json|'  # Inline data
    r'content=["\']application/ld\+json|'      # JSON-LD (injected by JS)
    r'<noscript>.*?JavaScript|'                 # "Enable JS" message
    r'document\.getElementById\(["\']',       # DOM manipulation
    re.IGNORECASE | re.DOTALL
)


def _is_spa_indicator_html(html: str) -> bool:
    """Detect if HTML contains signs of SPA/client-side rendering.
    
    Returns True if the HTML suggests it's a React/Vue/Next.js app that needs
    browser rendering to inject dynamic content (like job listings).
    
    Checks first 10KB only (performance optimization).
    """
    return bool(_SPA_INDICATORS.search(html[:10000]))


async def _run_scrapling(
    command: str,
    url: str,
    ai_targeted: bool = True,
    extra_flags: list[str] | None = None,
    min_content_length: int | None = None,
) -> str:
    """Run a scrapling extract <command> with exponential backoff retry logic.
    
    Args:
        command: The scrapling command (get, fetch, stealthy-fetch)
        url: The URL to fetch
        ai_targeted: Strip noise/hidden elements (default True)
        extra_flags: Additional flags (--network-idle, etc.)
        min_content_length: Minimum bytes to consider success (default _MIN_CONTENT_LENGTH)
    
    Returns HTML string on success, or '' on failure after all retries exhausted.
    """
    if min_content_length is None:
        min_content_length = _MIN_CONTENT_LENGTH
    
    last_error = None
    
    for attempt in range(_MAX_RETRIES):
        try:
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
                out_path = f.name

            cmd = [_SCRAPLING, "extract", command, url, out_path]
            if ai_targeted:
                cmd.append("--ai-targeted")
            cmd += extra_flags or []
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode != 0:
                logger.debug("scrapling %s stderr: %s", command, stderr.decode(errors="replace")[:300])
                last_error = f"Process returned {proc.returncode}"
                continue

            html = Path(out_path).read_text(encoding="utf-8", errors="replace")
            if len(html) >= min_content_length:
                logger.info("scrapling extract %s succeeded for %s (%d bytes)", command, url, len(html))
                return html
            logger.warning("scrapling extract %s returned thin content (%d bytes, need %d) for %s",
                          command, len(html), min_content_length, url)
            last_error = "Content too thin"
            
        except asyncio.TimeoutError:
            logger.warning("scrapling extract %s timed out for %s (attempt %d/%d)", command, url, attempt + 1, _MAX_RETRIES)
            last_error = "Timeout"
        except Exception as exc:
            logger.warning("scrapling extract %s error for %s (attempt %d/%d): %s", command, url, attempt + 1, _MAX_RETRIES, exc)
            last_error = str(exc)
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass
        
        # Exponential backoff before retry
        if attempt < _MAX_RETRIES - 1:
            wait_time = (_RETRY_BACKOFF ** attempt)
            logger.debug("Retrying after %d seconds...", wait_time)
            await asyncio.sleep(wait_time)
    
    logger.warning("All scrapling extract %s attempts failed for %s. Last error: %s", command, url, last_error)
    return ""


async def fetch_html(
    url: str,
    ai_targeted: bool = True,
    browser: bool = False,
    network_idle: bool = False,
    is_generic_site: bool = False,
) -> str:
    """Return HTML for *url*, escalating through get → fetch → stealthy-fetch.

    Smart escalation strategy:
    1. If browser=True, use browser rendering directly (skip get)
    2. If browser=False but is_generic_site=True, try get first but detect SPA and escalate to browser
    3. Otherwise, use standard escalation (get → fetch → stealthy-fetch)

    Args:
        ai_targeted:    Strip noise/hidden elements for cleaner parsing (default True).
                        Set False when you need raw HTML to detect embedded iframes.
        browser:        Skip `get` and start directly with browser-based `fetch`.
                        Use for JS-heavy SPAs (Ashby, Workday, Oracle HCM).
        network_idle:   Pass --network-idle to browser commands.
                        Use for pages that fire many XHR requests to load job listings.
        is_generic_site: This is a custom careers page that might use React/Vue/Next.js.
                        Use smarter SPA detection and lower content threshold.
    """
    
    # Determine the content length threshold
    min_content = _MIN_CONTENT_LENGTH_SPA if is_generic_site else _MIN_CONTENT_LENGTH
    
    # For known SPA systems, start with browser
    if browser:
        commands = ("fetch", "stealthy-fetch")
    # For generic sites, try fast path but be smart about SPA detection
    elif is_generic_site:
        commands = ("get", "fetch", "stealthy-fetch")
    # For everything else, standard escalation
    else:
        commands = ("get", "fetch", "stealthy-fetch")
    
    extra: list[str] = ["--network-idle"] if network_idle else []
    
    for i, command in enumerate(commands):
        # --network-idle only applies to browser commands
        flags = extra if command in ("fetch", "stealthy-fetch") else []
        
        # Use lower threshold for initial attempts on SPA sites
        attempt_min_content = min_content if (is_generic_site and command == "get") else _MIN_CONTENT_LENGTH
        
        html = await _run_scrapling(command, url, ai_targeted=ai_targeted, 
                                   extra_flags=flags, min_content_length=attempt_min_content)
        
        if html:
            # For generic sites with get command, check if it's a SPA that needs rendering
            if is_generic_site and command == "get" and _is_spa_indicator_html(html):
                logger.info("SPA framework detected in %s — escalating to browser rendering", url)
                # Try browser rendering instead
                browser_html = await _run_scrapling(
                    "fetch", url,
                    ai_targeted=ai_targeted,
                    extra_flags=extra + ["--network-idle"],
                    min_content_length=_MIN_CONTENT_LENGTH_SPA
                )
                if browser_html:
                    return browser_html
            
            # If we got content that passes the threshold, return it
            if len(html) >= min_content:
                return html

    # If ai_targeted=True stripped all content, retry every command raw
    if ai_targeted:
        logger.info("ai_targeted pass failed for %s — retrying without --ai-targeted", url)
        for command in commands:
            flags = extra if command in ("fetch", "stealthy-fetch") else []
            attempt_min_content = min_content if (is_generic_site and command == "get") else _MIN_CONTENT_LENGTH
            html = await _run_scrapling(command, url, ai_targeted=False, extra_flags=flags,
                                       min_content_length=attempt_min_content)
            if html:
                return html

    raise RuntimeError(f"All scrapling fetch methods failed for {url}")
