"""Fallback for sites that only serve full browsers: render the page in headless Chromium.

Some sites answer a plain HTTP client with 403 or a JavaScript check page but serve a real
browser normally (France24 does). We load them in Chromium, honestly identified as headless (no
disguise, no CAPTCHA solving): sites that block headless browsers too (TASS) stay unreadable here,
and are a job for the paid scraping provider.

Safety: Chromium follows redirects and loads sub-resources on its own, and Playwright's request
interception does not see redirect hops. So every connection goes through `GuardProxy`, a local
proxy that allows HTTPS on port 443 to hosts that resolve only to public addresses, and connects
to the exact address it checked (no second DNS lookup to rebind). Private destinations are refused
whatever path leads to them.
"""

import asyncio
import contextlib
import ipaddress
import os
import socket

from pipeline.extract.fetch import FetchFailed, Page

NAV_TIMEOUT_S = 20.0
SETTLE_S = 3.0  # time for JavaScript to build the article after the document loads
_MAX_RENDERS = 2  # Chromium is memory-hungry on the 2 vCPU / 8 GB VPS
_SKIPPED_RESOURCES = {"image", "media", "font"}
_renders = asyncio.Semaphore(_MAX_RENDERS)
# Set when Chromium fails to start (not installed in this image): stop trying until restart.
_launch_failed = False


def enabled() -> bool:
    """On unless BROWSER_FALLBACK=0, Playwright is missing or Chromium failed to start."""
    if _launch_failed or os.environ.get("BROWSER_FALLBACK", "1") == "0":
        return False
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False
    return True


def _public_address(host: str, port: int) -> str | None:
    """One address of `host`, provided every address it resolves to is public; else None.

    Same rule as `pipeline.common.net.assert_public_url`, returning the address so the proxy
    connects to what it checked.
    """
    try:
        resolved = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        return None
    addresses = [sockaddr[0].split("%")[0] for *_, sockaddr in resolved]
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        return None
    return addresses[0]


class GuardProxy:
    """Local HTTPS-only forward proxy that refuses non-public destinations."""

    def __init__(self) -> None:
        self.blocked: list[str] = []  # host:port refused, for the caller's error message
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> GuardProxy:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def url(self) -> str:
        assert self._server is not None
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
            method, target, *_ = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ")
            if method != "CONNECT":  # plain HTTP is not proxied: https only
                await self._refuse(writer, target)
                return
            host, _, port_text = target.rpartition(":")
            host = host.strip("[]")
            address = (
                await asyncio.to_thread(_public_address, host, 443) if port_text == "443" else None
            )
            if address is None:
                await self._refuse(writer, target)
                return
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(address, 443), timeout=10
            )
        except TimeoutError, OSError, ValueError, asyncio.IncompleteReadError:
            writer.close()
            return
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        await asyncio.gather(
            _pipe(reader, upstream_writer), _pipe(upstream_reader, writer), return_exceptions=True
        )

    async def _refuse(self, writer: asyncio.StreamWriter, target: str) -> None:
        self.blocked.append(target)
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        with contextlib.suppress(OSError):
            await writer.drain()
        writer.close()


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()
    finally:
        writer.close()


async def render_page(url: str) -> Page:
    """Load `url` in headless Chromium through `GuardProxy` and return the rendered HTML.

    Raises `FetchFailed` with a plain reason when the page cannot be loaded.
    """
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import async_playwright

    async def skip_heavy(route) -> None:
        if route.request.resource_type in _SKIPPED_RESOURCES:
            await route.abort()
        else:
            await route.continue_()

    async with _renders, GuardProxy() as proxy, async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(
                proxy={"server": proxy.url},
                # Chromium skips the proxy for loopback by default; send that through it too.
                args=["--proxy-bypass-list=<-loopback>"],
            )
        except PlaywrightError as e:
            global _launch_failed
            _launch_failed = True
            raise FetchFailed("The page could not be opened in a browser") from e
        try:
            page = await browser.new_page()
            await page.route("**/*", skip_heavy)
            try:
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_S * 1000
                )
            except PlaywrightError as e:
                if proxy.blocked:
                    raise FetchFailed("The link does not point to a public website") from e
                if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
                    raise FetchFailed("The site took too long to answer") from e
                raise FetchFailed("The site could not be reached") from e
            await page.wait_for_timeout(SETTLE_S * 1000)
            html = await _settled_content(page)
            return Page(
                url=page.url,
                status=response.status if response else 200,
                content_type="text/html",
                body=html.encode("utf-8"),
                truncated=False,
            )
        finally:
            await browser.close()


async def _settled_content(page) -> str:
    """The page HTML; a JavaScript check may still be navigating, so retry briefly."""
    from playwright.async_api import Error as PlaywrightError

    for _ in range(10):
        try:
            return await page.content()
        except PlaywrightError:
            await page.wait_for_timeout(500)
    raise FetchFailed("The page kept changing and could not be read")
