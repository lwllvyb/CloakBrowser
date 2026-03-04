"""Core browser launch functions for cloakbrowser.

Provides launch() and launch_async() — thin wrappers around Playwright
that use our patched stealth Chromium binary instead of stock Chromium.

Usage:
    from cloakbrowser import launch

    browser = launch()
    page = browser.new_page()
    page.goto("https://protected-site.com")
    browser.close()
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal, TypedDict
from urllib.parse import unquote, urlparse, urlunparse

from .config import DEFAULT_VIEWPORT, get_default_stealth_args
from .download import ensure_binary

logger = logging.getLogger("cloakbrowser")


class _ProxySettingsRequired(TypedDict):
    server: str


class ProxySettings(_ProxySettingsRequired, total=False):
    """Playwright-compatible proxy configuration."""

    bypass: str
    username: str
    password: str


def launch(
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    timezone: str | None = None,
    locale: str | None = None,
    geoip: bool = False,
    **kwargs: Any,
) -> Any:
    """Launch stealth Chromium browser. Returns a Playwright Browser object.

    Args:
        headless: Run in headless mode (default True).
        proxy: Proxy URL string or Playwright proxy dict.
            String: 'http://user:pass@proxy:8080' (credentials auto-extracted).
            Dict: {"server": "http://proxy:8080", "bypass": ".google.com", ...}
            — passed directly to Playwright.
        args: Additional Chromium CLI arguments to pass.
        stealth_args: Include default stealth fingerprint args (default True).
            Set to False if you want to pass your own --fingerprint flags.
        timezone: IANA timezone (e.g. 'America/New_York'). Sets --fingerprint-timezone binary flag.
        locale: BCP 47 locale (e.g. 'en-US'). Sets --lang binary flag.
        geoip: Auto-detect timezone/locale from proxy IP (default False).
            Requires ``pip install cloakbrowser[geoip]``. Downloads ~70 MB
            GeoLite2-City database on first use.  Explicit timezone/locale
            always override geoip results.
        **kwargs: Passed directly to playwright.chromium.launch().

    Returns:
        Playwright Browser object — use same API as playwright.chromium.launch().

    Example:
        >>> from cloakbrowser import launch
        >>> browser = launch()
        >>> page = browser.new_page()
        >>> page.goto("https://bot.incolumitas.com")
        >>> print(page.title())
        >>> browser.close()
    """
    from patchright.sync_api import sync_playwright

    binary_path = ensure_binary()
    timezone, locale = _maybe_resolve_geoip(geoip, proxy, timezone, locale)
    chrome_args = _build_args(stealth_args, args, timezone=timezone, locale=locale)

    logger.debug("Launching stealth Chromium (headless=%s, args=%d)", headless, len(chrome_args))

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        executable_path=binary_path,
        headless=headless,
        args=chrome_args,
        ignore_default_args=["--enable-automation"],
        **_build_proxy_kwargs(proxy),
        **kwargs,
    )

    # Patch close() to also stop the Playwright instance
    _original_close = browser.close

    def _close_with_cleanup() -> None:
        _original_close()
        pw.stop()

    browser.close = _close_with_cleanup

    return browser


async def launch_async(
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    timezone: str | None = None,
    locale: str | None = None,
    geoip: bool = False,
    **kwargs: Any,
) -> Any:
    """Async version of launch(). Returns a Playwright Browser object.

    Args:
        headless: Run in headless mode (default True).
        proxy: Proxy URL string or Playwright proxy dict (see launch() for details).
        args: Additional Chromium CLI arguments to pass.
        stealth_args: Include default stealth fingerprint args (default True).
        timezone: IANA timezone (e.g. 'America/New_York'). Sets --fingerprint-timezone binary flag.
        locale: BCP 47 locale (e.g. 'en-US'). Sets --lang binary flag.
        geoip: Auto-detect timezone/locale from proxy IP (default False).
        **kwargs: Passed directly to playwright.chromium.launch().

    Returns:
        Playwright Browser object (async API).

    Example:
        >>> import asyncio
        >>> from cloakbrowser import launch_async
        >>>
        >>> async def main():
        ...     browser = await launch_async()
        ...     page = await browser.new_page()
        ...     await page.goto("https://bot.incolumitas.com")
        ...     print(await page.title())
        ...     await browser.close()
        >>>
        >>> asyncio.run(main())
    """
    from patchright.async_api import async_playwright

    binary_path = ensure_binary()
    timezone, locale = _maybe_resolve_geoip(geoip, proxy, timezone, locale)
    chrome_args = _build_args(stealth_args, args, timezone=timezone, locale=locale)

    logger.debug("Launching stealth Chromium async (headless=%s, args=%d)", headless, len(chrome_args))

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        executable_path=binary_path,
        headless=headless,
        args=chrome_args,
        ignore_default_args=["--enable-automation"],
        **_build_proxy_kwargs(proxy),
        **kwargs,
    )

    # Patch close() to also stop the Playwright instance
    _original_close = browser.close

    async def _close_with_cleanup() -> None:
        await _original_close()
        await pw.stop()

    browser.close = _close_with_cleanup

    return browser


def launch_persistent_context(
    user_data_dir: str | os.PathLike,
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    user_agent: str | None = None,
    viewport: dict | None = None,
    locale: str | None = None,
    timezone_id: str | None = None,
    color_scheme: Literal["light", "dark", "no-preference"] | None = None,
    geoip: bool = False,
    **kwargs: Any,
) -> Any:
    """Launch stealth browser with a persistent profile and return a BrowserContext.

    This persists cookies, localStorage, cache, and other browser state across
    sessions by storing them in ``user_data_dir``. Also avoids incognito detection
    by services like BrowserScan (-10% penalty).

    Args:
        user_data_dir: Path to the directory where browser profile data is stored.
            Created automatically if it doesn't exist. Reuse the same path across
            sessions to restore cookies, localStorage, cached credentials, etc.
        headless: Run in headless mode (default True).
        proxy: Proxy URL string or Playwright proxy dict (see launch() for details).
        args: Additional Chromium CLI arguments.
        stealth_args: Include default stealth fingerprint args (default True).
        user_agent: Custom user agent string.
        viewport: Viewport size dict, e.g. {"width": 1920, "height": 1080}.
        locale: Browser locale, e.g. "en-US".
        timezone_id: Timezone, e.g. "America/New_York".
        color_scheme: Color scheme preference — 'light', 'dark', or 'no-preference'.
            Default: None (uses Chromium default, which is 'light').
        geoip: Auto-detect timezone/locale from proxy IP (default False).
            Requires ``pip install cloakbrowser[geoip]``.
        **kwargs: Passed directly to playwright.chromium.launch_persistent_context().

    Returns:
        Playwright BrowserContext object backed by a persistent profile.
        Call ``.close()`` when done — this also stops the Playwright instance.

    Example:
        >>> from cloakbrowser import launch_persistent_context
        >>> ctx = launch_persistent_context("./my-profile", headless=False)
        >>> page = ctx.new_page()
        >>> page.goto("https://protected-site.com")
        >>> ctx.close()  # Profile is saved; re-use path next run to restore state.
    """
    from patchright.sync_api import sync_playwright

    binary_path = ensure_binary()
    timezone_id, locale = _maybe_resolve_geoip(geoip, proxy, timezone_id, locale)
    chrome_args = _build_args(stealth_args, args, timezone=timezone_id, locale=locale)

    logger.debug(
        "Launching persistent stealth Chromium (headless=%s, user_data_dir=%s)",
        headless,
        user_data_dir,
    )

    context_kwargs: dict[str, Any] = {}
    if user_agent:
        context_kwargs["user_agent"] = user_agent
    context_kwargs["viewport"] = viewport or DEFAULT_VIEWPORT
    if locale:
        context_kwargs["locale"] = locale
    if timezone_id:
        context_kwargs["timezone_id"] = timezone_id
    if color_scheme:
        context_kwargs["color_scheme"] = color_scheme
    context_kwargs.update(kwargs)

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=os.fspath(user_data_dir),
        executable_path=binary_path,
        headless=headless,
        args=chrome_args,
        ignore_default_args=["--enable-automation"],
        **_build_proxy_kwargs(proxy),
        **context_kwargs,
    )

    # Patch close() to also stop the Playwright instance
    _original_close = context.close

    def _close_with_cleanup() -> None:
        _original_close()
        pw.stop()

    context.close = _close_with_cleanup

    return context


async def launch_persistent_context_async(
    user_data_dir: str | os.PathLike,
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    user_agent: str | None = None,
    viewport: dict | None = None,
    locale: str | None = None,
    timezone_id: str | None = None,
    color_scheme: Literal["light", "dark", "no-preference"] | None = None,
    geoip: bool = False,
    **kwargs: Any,
) -> Any:
    """Async version of launch_persistent_context().

    Launch stealth browser with a persistent profile and return a BrowserContext.
    This persists cookies, localStorage, cache, and other browser state across
    sessions by storing them in ``user_data_dir``.

    Args:
        user_data_dir: Path to the directory where browser profile data is stored.
            Created automatically if it doesn't exist.
        headless: Run in headless mode (default True).
        proxy: Proxy URL string or Playwright proxy dict (see launch() for details).
        args: Additional Chromium CLI arguments.
        stealth_args: Include default stealth fingerprint args (default True).
        user_agent: Custom user agent string.
        viewport: Viewport size dict, e.g. {"width": 1920, "height": 1080}.
        locale: Browser locale, e.g. "en-US".
        timezone_id: Timezone, e.g. "America/New_York".
        color_scheme: Color scheme preference — 'light', 'dark', or 'no-preference'.
        geoip: Auto-detect timezone/locale from proxy IP (default False).
        **kwargs: Passed directly to playwright.chromium.launch_persistent_context().

    Returns:
        Playwright BrowserContext object backed by a persistent profile (async API).
        Call ``await .close()`` when done.

    Example:
        >>> import asyncio
        >>> from cloakbrowser import launch_persistent_context_async
        >>>
        >>> async def main():
        ...     ctx = await launch_persistent_context_async("./my-profile", headless=False)
        ...     page = await ctx.new_page()
        ...     await page.goto("https://protected-site.com")
        ...     await ctx.close()
        >>>
        >>> asyncio.run(main())
    """
    from patchright.async_api import async_playwright

    binary_path = ensure_binary()
    timezone_id, locale = _maybe_resolve_geoip(geoip, proxy, timezone_id, locale)
    chrome_args = _build_args(stealth_args, args, timezone=timezone_id, locale=locale)

    logger.debug(
        "Launching persistent stealth Chromium async (headless=%s, user_data_dir=%s)",
        headless,
        user_data_dir,
    )

    context_kwargs: dict[str, Any] = {}
    if user_agent:
        context_kwargs["user_agent"] = user_agent
    context_kwargs["viewport"] = viewport or DEFAULT_VIEWPORT
    if locale:
        context_kwargs["locale"] = locale
    if timezone_id:
        context_kwargs["timezone_id"] = timezone_id
    if color_scheme:
        context_kwargs["color_scheme"] = color_scheme
    context_kwargs.update(kwargs)

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=os.fspath(user_data_dir),
        executable_path=binary_path,
        headless=headless,
        args=chrome_args,
        ignore_default_args=["--enable-automation"],
        **_build_proxy_kwargs(proxy),
        **context_kwargs,
    )

    # Patch close() to also stop the Playwright instance
    _original_close = context.close

    async def _close_with_cleanup() -> None:
        await _original_close()
        await pw.stop()

    context.close = _close_with_cleanup

    return context


def launch_context(
    headless: bool = True,
    proxy: str | ProxySettings | None = None,
    args: list[str] | None = None,
    stealth_args: bool = True,
    user_agent: str | None = None,
    viewport: dict | None = None,
    locale: str | None = None,
    timezone_id: str | None = None,
    color_scheme: Literal["light", "dark", "no-preference"] | None = None,
    geoip: bool = False,
    **kwargs: Any,
) -> Any:
    """Launch stealth browser and return a BrowserContext with common options pre-set.

    Convenience function that creates a browser + context in one call.
    Useful for setting user agent, viewport, locale, etc.

    Args:
        headless: Run in headless mode (default True).
        proxy: Proxy URL string or Playwright proxy dict (see launch() for details).
        args: Additional Chromium CLI arguments.
        stealth_args: Include default stealth fingerprint args (default True).
        user_agent: Custom user agent string.
        viewport: Viewport size dict, e.g. {"width": 1920, "height": 1080}.
        locale: Browser locale, e.g. "en-US".
        timezone_id: Timezone, e.g. "America/New_York".
        color_scheme: Color scheme preference — 'light', 'dark', or 'no-preference'.
            Default: None (uses Chromium default, which is 'light').
            Note: 'no-preference' doesn't work in Patchright (falls back to 'light').
        geoip: Auto-detect timezone/locale from proxy IP (default False).
        **kwargs: Passed to browser.new_context().

    Returns:
        Playwright BrowserContext object.
    """
    # Resolve geoip BEFORE launch() to avoid double-resolution and ensure
    # resolved values flow to both binary flags AND context params
    timezone_id, locale = _maybe_resolve_geoip(geoip, proxy, timezone_id, locale)
    # Skip --fingerprint-timezone binary flag: it only applies to the default
    # context and interferes with Playwright's timezone_id on new contexts.
    # Timezone is set via browser.new_context(timezone_id=...) below instead.
    browser = launch(headless=headless, proxy=proxy, args=args, stealth_args=stealth_args,
                     timezone=None, locale=locale)

    context_kwargs: dict[str, Any] = {}
    if user_agent:
        context_kwargs["user_agent"] = user_agent
    context_kwargs["viewport"] = viewport or DEFAULT_VIEWPORT
    if locale:
        context_kwargs["locale"] = locale
    if timezone_id:
        context_kwargs["timezone_id"] = timezone_id
    if color_scheme:
        context_kwargs["color_scheme"] = color_scheme
    context_kwargs.update(kwargs)

    try:
        context = browser.new_context(**context_kwargs)
    except Exception:
        browser.close()
        raise

    # Patch close() to also close the browser (and its Playwright instance)
    _original_ctx_close = context.close

    def _close_context_with_cleanup() -> None:
        _original_ctx_close()
        browser.close()

    context.close = _close_context_with_cleanup

    return context


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _maybe_resolve_geoip(
    geoip: bool,
    proxy: str | ProxySettings | None,
    timezone: str | None,
    locale: str | None,
) -> tuple[str | None, str | None]:
    """Auto-fill timezone/locale from proxy IP when geoip is enabled."""
    if not geoip or not proxy or (timezone is not None and locale is not None):
        return timezone, locale

    from .geoip import resolve_proxy_geo

    proxy_url = proxy.get("server") if isinstance(proxy, dict) else proxy
    if not proxy_url:
        return timezone, locale
    geo_tz, geo_locale = resolve_proxy_geo(proxy_url)
    if timezone is None:
        timezone = geo_tz
    if locale is None:
        locale = geo_locale
    return timezone, locale


def _build_args(
    stealth_args: bool,
    extra_args: list[str] | None,
    timezone: str | None = None,
    locale: str | None = None,
) -> list[str]:
    """Combine stealth args with user-provided args and locale flags."""
    result = []
    if stealth_args:
        result.extend(get_default_stealth_args())
    if extra_args:
        result.extend(extra_args)
    # Timezone/locale flags are independent of stealth_args — always inject when set
    if timezone:
        result.append(f"--fingerprint-timezone={timezone}")
    if locale:
        result.append(f"--lang={locale}")
    return result


def _parse_proxy_url(proxy: str) -> dict[str, Any]:
    """Parse proxy URL, extracting credentials into separate Playwright fields.

    Handles: http://user:pass@host:port -> {server: "http://host:port", username: "user", password: "pass"}
    Also handles: no credentials, URL-encoded special chars, socks5://, missing port.
    """
    parsed = urlparse(proxy)

    if not parsed.username:
        return {"server": proxy}

    # Rebuild server URL without credentials
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"

    server = urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))

    result: dict[str, Any] = {"server": server}
    result["username"] = unquote(parsed.username)
    if parsed.password:
        result["password"] = unquote(parsed.password)

    return result


def _build_proxy_kwargs(proxy: str | ProxySettings | None) -> dict[str, Any]:
    """Build proxy kwargs for Playwright launch."""
    if proxy is None:
        return {}
    if isinstance(proxy, dict):
        return {"proxy": proxy}
    return {"proxy": _parse_proxy_url(proxy)}
