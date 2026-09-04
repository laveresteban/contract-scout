"""Headless-browser rendering fallback for JS-gated / bot-protected boards.

Most sources in this app are reachable with plain ``httpx`` requests, which is
faster and cheaper. A few boards (notably Dice) render their results through a
JavaScript framework and intermittently serve a bot challenge or an empty shell
to raw HTTP clients. For those cases we fall back to rendering the page in a
real headless browser via Playwright and returning the fully-rendered HTML,
which the existing per-source parsers can then consume unchanged.

Playwright is an *optional* dependency, mirroring how ``jobspy`` and
``apify-client`` are handled elsewhere. If it (or its browser binaries) are not
installed, every helper here degrades gracefully to a no-op so the rest of the
pipeline keeps working on the httpx path.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# A realistic desktop Chrome UA so rendered requests look like a normal browser.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when dep is absent
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False
    logger.info("playwright is not installed; browser-render fallback disabled.")


def browser_available() -> bool:
    """Whether the Playwright package is importable (browser may still be missing)."""
    return PLAYWRIGHT_AVAILABLE


async def fetch_rendered(
    url: str,
    *,
    wait_selector: str | None = None,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30_000,
    settle_ms: int = 1_500,
) -> str | None:
    """Render ``url`` in a headless browser and return its HTML, or ``None``.

    Returns ``None`` (never raises) when Playwright is unavailable, the browser
    cannot launch, or the navigation fails, so callers can treat this purely as
    a best-effort enhancement over the httpx path.

    Args:
        url: The page to render.
        wait_selector: Optional CSS selector to wait for before capturing HTML.
        wait_until: Playwright load state to await on navigation.
        timeout_ms: Navigation / selector timeout in milliseconds.
        settle_ms: Extra idle time after load to let late XHR content paint.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return None

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=_BROWSER_UA,
                    locale="en-US",
                    viewport={"width": 1366, "height": 900},
                )
                page = await context.new_page()
                await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                if wait_selector:
                    try:
                        await page.wait_for_selector(wait_selector, timeout=timeout_ms)
                    except Exception:
                        # Selector never appeared; return whatever rendered anyway.
                        pass
                if settle_ms:
                    await page.wait_for_timeout(settle_ms)
                return await page.content()
            finally:
                await browser.close()
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Browser render failed for %s: %s", url, type(exc).__name__)
        return None
