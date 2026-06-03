"""HTML fetcher using the Scrapling CLI agent.

Strategy (per Scrapling agent skill docs):
  1. scrapling extract get          — fast HTTP, no browser
  2. scrapling extract fetch        — Chromium, for JS-rendered pages
  3. scrapling extract stealthy-fetch — stealth Chromium, for anti-bot sites

Each level is tried only if the previous returns empty or fails.
--ai-targeted cleans hidden elements and extracts main content, reducing noise for parsers.
"""
import asyncio
import logging
import os
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

_MIN_CONTENT_LENGTH = 500  # bytes — below this we consider the fetch a failure


async def _run_scrapling(command: str, url: str, ai_targeted: bool = True, extra_flags: list[str] | None = None) -> str:
    """Run a scrapling extract <command> and return HTML string, or '' on failure."""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        out_path = f.name

    cmd = [_SCRAPLING, "extract", command, url, out_path]
    if ai_targeted:
        cmd.append("--ai-targeted")
    cmd += extra_flags or []
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            logger.debug("scrapling %s stderr: %s", command, stderr.decode(errors="replace")[:300])

        html = Path(out_path).read_text(encoding="utf-8", errors="replace")
        if len(html) >= _MIN_CONTENT_LENGTH:
            logger.info("scrapling extract %s succeeded for %s (%d bytes)", command, url, len(html))
            return html
        logger.warning("scrapling extract %s returned thin content (%d bytes) for %s", command, len(html), url)
        return ""
    except asyncio.TimeoutError:
        logger.warning("scrapling extract %s timed out for %s", command, url)
        return ""
    except Exception as exc:
        logger.warning("scrapling extract %s error for %s: %s", command, url, exc)
        return ""
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


async def fetch_html(
    url: str,
    ai_targeted: bool = True,
    browser: bool = False,
    network_idle: bool = False,
) -> str:
    """Return HTML for *url*, escalating through get → fetch → stealthy-fetch.

    Args:
        ai_targeted:  Strip noise/hidden elements for cleaner parsing (default True).
                      Set False when you need raw HTML to detect embedded iframes.
        browser:      Skip `get` and start directly with browser-based `fetch`.
                      Use for JS-heavy SPAs (Ashby, Workday, Oracle HCM).
        network_idle: Pass --network-idle to browser commands.
                      Use for pages that fire many XHR requests to load job listings.
    """
    commands = ("fetch", "stealthy-fetch") if browser else ("get", "fetch", "stealthy-fetch")
    extra: list[str] = ["--network-idle"] if network_idle else []
    for command in commands:
        # --network-idle only applies to browser commands
        flags = extra if command in ("fetch", "stealthy-fetch") else []
        html = await _run_scrapling(command, url, ai_targeted=ai_targeted, extra_flags=flags)
        if html:
            return html

    raise RuntimeError(f"All scrapling fetch methods failed for {url}")
