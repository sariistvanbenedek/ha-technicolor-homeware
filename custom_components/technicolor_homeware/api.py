"""Async client for the Technicolor Homeware web interface."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
import re
from typing import Any, TypeVar

import aiohttp
from yarl import URL

from .const import HOME_PAGE, PROBE_MAX_PAGES, PROBE_PAGES, PROBE_SKIP
from .parser import extract_csrf, is_login_page, page_fingerprint, parse_page, summarize_page
from .srp6 import SrpUser

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")

Executor = Callable[..., Awaitable[Any]]

REQUEST_TIMEOUT = 20
HEADERS = {"X-Requested-With": "XMLHttpRequest"}


class TechnicolorError(Exception):
    """Base error."""


class TechnicolorConnectionError(TechnicolorError):
    """The router could not be reached or answered unexpectedly."""


class TechnicolorAuthError(TechnicolorError):
    """The router rejected the credentials."""


class TechnicolorPageNotFound(TechnicolorError):
    """The page does not exist on this firmware."""


async def _default_executor(func: Callable[..., _T], *args: Any) -> _T:
    return await asyncio.get_running_loop().run_in_executor(None, func, *args)


class TechnicolorClient:
    """Logs in with SRP-6 and reads pages, re-authenticating when needed."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        use_ssl: bool = False,
        executor: Executor | None = None,
    ) -> None:
        """Initialize."""
        self._session = session
        self._base = f"{'https' if use_ssl else 'http'}://{host.strip().rstrip('/')}"
        self._username = username
        self._password = password
        self._executor = executor or _default_executor
        self._lock = asyncio.Lock()
        self._logged_in = False

    @property
    def base_url(self) -> str:
        """Router web address."""
        return self._base

    async def _request(
        self, method: str, path: str, data: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        url = f"{self._base}/{path.lstrip('/')}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, url, data=data, headers=HEADERS, ssl=False, allow_redirects=True
                ) as resp:
                    text = await resp.text(errors="replace")
                    return resp.status, text, str(resp.url)
        except TimeoutError as err:
            raise TechnicolorConnectionError(f"Timeout while requesting {url}") from err
        except aiohttp.ClientError as err:
            raise TechnicolorConnectionError(f"Error requesting {url}: {type(err).__name__}: {err}") from err

    async def _login(self) -> None:
        """SRP-6 login (caller holds the lock)."""
        self._logged_in = False
        token = None
        seen: list[str] = []
        for path in (HOME_PAGE, "login.lp"):
            status, text, url = await self._request("GET", path)
            self._adopt_origin(url)
            if status < 400 and (token := extract_csrf(text)):
                break
            seen.append(f"[{path} -> HTTP {status} {url} {page_fingerprint(text)}]")
        if not token:
            raise TechnicolorConnectionError("No CSRF token on the login page: " + " ".join(seen))

        user: SrpUser = await self._executor(SrpUser, self._username, self._password)
        ident, a_hex = user.start()
        challenge = await self._post_json("authenticate", {"CSRFtoken": token, "I": ident, "A": a_hex})
        if "error" in challenge or "s" not in challenge or "B" not in challenge:
            raise TechnicolorAuthError(f"Login refused: {challenge.get('error', challenge)}")

        m_hex = await self._executor(user.process_challenge, challenge["s"], challenge["B"])
        if m_hex is None:
            raise TechnicolorAuthError("Invalid SRP challenge from router")
        proof = await self._post_json("authenticate", {"CSRFtoken": token, "M": m_hex})
        if "error" in proof or "M" not in proof:
            raise TechnicolorAuthError(f"Wrong username or password (router said: {proof.get('error', proof)})")
        if not user.verify_session(proof["M"]):
            raise TechnicolorAuthError("Router proof did not verify")
        self._logged_in = True
        _LOGGER.debug("Logged in to %s", self._base)

    def _adopt_origin(self, final_url: str) -> None:
        """Follow the router's own redirect (e.g. http -> https) for later requests.

        A POST answered with a redirect would turn into a GET, so the login must
        talk to the address the router actually serves.
        """
        url = URL(final_url)
        current = URL(self._base)
        if not url.host or url.host != current.host:
            return
        origin = str(url.origin())
        if origin != self._base:
            _LOGGER.info("Router redirected %s to %s, using that address", self._base, origin)
            self._base = origin

    async def _post_json(self, path: str, data: dict[str, str]) -> dict[str, Any]:
        status, text, _ = await self._request("POST", path, data)
        if status in (401, 403):
            raise TechnicolorAuthError(f"Login refused (HTTP {status})")
        try:
            result = json.loads(text)
        except ValueError as err:
            raise TechnicolorConnectionError(
                f"Unexpected login answer (HTTP {status}): {page_fingerprint(text)}"
            ) from err
        if not isinstance(result, dict):
            raise TechnicolorConnectionError("Unexpected login answer")
        return result

    async def async_login(self) -> None:
        """Log in (used by the config flow)."""
        async with self._lock:
            await self._login()

    def _needs_login(self, path: str, status: int, text: str, url: str) -> bool:
        if status in (401, 403):
            return True
        if "login.lp" in url and "login.lp" not in path:
            return True
        return is_login_page(text, modal=path != HOME_PAGE)

    async def async_get(self, path: str) -> str:
        """GET a page as an authenticated user."""
        async with self._lock:
            if not self._logged_in:
                await self._login()
            status, text, url = await self._request("GET", path)
            if self._needs_login(path, status, text, url):
                _LOGGER.debug("Session expired, logging in again")
                await self._login()
                status, text, url = await self._request("GET", path)
                if self._needs_login(path, status, text, url):
                    raise TechnicolorAuthError("The router keeps asking for login")
            if status == 404:
                raise TechnicolorPageNotFound(path)
            if status >= 400:
                raise TechnicolorConnectionError(f"HTTP {status} for {path}")
            return text

    async def async_post(self, path: str, data: dict[str, str]) -> tuple[int, str]:
        """POST with a fresh CSRF token (token taken from the home page)."""
        home = await self.async_get(HOME_PAGE)
        token = extract_csrf(home)
        if not token:
            raise TechnicolorConnectionError("No CSRF token on the home page")
        async with self._lock:
            status, text, _ = await self._request("POST", path, {**data, "CSRFtoken": token})
        return status, text

    async def async_reboot(self) -> None:
        """Ask the gateway to reboot (same request as the web UI's Reboot button)."""
        status, _ = await self.async_post("modals/gateway-modal.lp", {"action": "system_reboot"})
        if status >= 400:
            raise TechnicolorConnectionError(f"Reboot request failed (HTTP {status})")

    async def async_login_assets(self) -> dict[str, str]:
        """The public sign-in page and its scripts (no credentials), for troubleshooting."""
        status, text, url = await self._request("GET", HOME_PAGE)
        self._adopt_origin(url)
        files = {"login_page.html": f"<!-- HTTP {status} {url} -->\n{text}"}
        for src in re.findall(r"""<script[^>]+src=["']([^"']+)["']""", text, re.I)[:8]:
            if "://" in src:
                continue
            path = src.split("?")[0]
            try:
                js_status, js, _ = await self._request("GET", path)
            except TechnicolorError:
                continue
            if js_status == 200:
                files[path.strip("/").replace("/", "_")] = js[:400_000]
        return files

    async def async_probe(self) -> dict[str, Any]:
        """Read-only survey of the web UI, for diagnostics and future support."""
        results: dict[str, Any] = {}
        queue: list[str] = list(PROBE_PAGES)
        index = 0
        while index < len(queue) and len(results) < PROBE_MAX_PAGES:
            path = queue[index]
            index += 1
            if path in results or (path != HOME_PAGE and any(s in path.lower() for s in PROBE_SKIP)):
                continue
            try:
                async with self._lock:
                    if not self._logged_in:
                        await self._login()
                    status, text, _ = await self._request("GET", path)
            except TechnicolorError as err:
                results[path] = {"error": str(err)}
                continue
            summary = await self._executor(summarize_page, path, status, text)
            results[path] = summary
            for link in summary.get("links", []) + summary.get("ajax", []):
                if link not in queue:
                    queue.append(link)
        return results


def parse_in_executor(executor: Executor, html: str) -> Awaitable[dict[str, Any]]:
    """Parse a page off the event loop."""
    return executor(parse_page, html)
