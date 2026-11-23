"""Parser and client tests (no Home Assistant needed)."""

from __future__ import annotations

from pathlib import Path

import aiohttp
from aiohttp.test_utils import TestServer
import pytest

from custom_components.technicolor_homeware.api import TechnicolorAuthError, TechnicolorClient
from custom_components.technicolor_homeware.parser import (
    extract_broadband,
    extract_devices,
    extract_info,
    extract_wan,
    parse_duration,
    parse_page,
    summarize_page,
)

from .mock_router import MockRouter

FIX = Path(__file__).parent / "fixtures"


def _devices(name: str) -> dict:
    return extract_devices(parse_page((FIX / name).read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    ("name", "count", "first_mac", "first_name", "first_ip"),
    [
        ("device-modal.lp.txt", 1, "74:83:c2:fd:e0:07", "EdgeRouter-X", "192.168.0.152"),
        ("device-modal_len_8.lp", 1, "02:11:12:12:12:12", "Mate", "192.168.1.2"),
        ("device-modal_len6.lp", 3, "c8:2b:96:11:09:59", "hostname1", "192.168.1.216"),
        ("device-modal_len_12.lp", 2, "e8:ab:fa:2b:ce:e0", "hostname1_aqua", "192.168.1.251"),
        ("ipv6devices-modal.lp", 1, "a4:83:e7:32:7e:11", "DeviceHostName", "192.168.1.111"),
        ("device-modal_.lp", None, "10:5a:17:12:a0:d6", "Luce-Studio", None),
        ("device-modal_2_3_1_fw.lp", 27, "3c:71:bf:39:ab:3b", None, "192.168.1.53"),
    ],
)
def test_device_samples(name, count, first_mac, first_name, first_ip) -> None:
    devices = _devices(name)
    if count is not None:
        assert len(devices) == count, list(devices)
    assert first_mac in devices
    dev = devices[first_mac]
    if first_name:
        assert dev["name"] == first_name
    if first_ip:
        assert dev["ip"] == first_ip
    assert dev["connected"] is True


def test_status_light_off_means_disconnected() -> None:
    html = (FIX / "device-modal.lp.txt").read_text(encoding="utf-8").replace("light green", "light off")
    assert extract_devices(parse_page(html))["74:83:c2:fd:e0:07"]["connected"] is False


def test_info_wan_broadband() -> None:
    info = extract_info([parse_page((FIX / "system-info-modal.lp").read_text(encoding="utf-8"))])
    assert info["product"] == "Telia F1"
    assert info["sw_version"] == "19.5.1062-4581003"
    assert info["mac"] == "aa:bb:cc:45:18:0e"
    assert info["uptime_seconds"] == 19 * 86400 + 6 * 3600 + 13 * 60 + 8
    assert info["cpu"] == 2.0 and info["memory"] == 86.0
    home = parse_page((FIX / "home.html").read_text(encoding="utf-8"))
    wan = extract_wan(home)
    assert wan["connected"] is True and wan["ip"] == "77.126.41.183"
    bb = extract_broadband(home)
    assert bb == {"connected": True, "up": 3.52, "down": 44.88}
    assert "modals/gateway-modal.lp" in home["links"]


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("0d 10:39:22", 10 * 3600 + 39 * 60 + 22),
        ("3 nap 4 óra 5 perc 6 másodperc", 3 * 86400 + 4 * 3600 + 5 * 60 + 6),
        ("22 hours 10 minutes 39 seconds", 22 * 3600 + 10 * 60 + 39),
        ("nonsense", None),
    ],
)
def test_duration(text, seconds) -> None:
    assert parse_duration(text) == seconds


def test_summary_masks() -> None:
    html = (FIX / "home.html").read_text(encoding="utf-8")
    summary = summarize_page("/", 200, html)
    assert "77.126.41.183" not in str(summary)
    assert "77.126.x.x" in str(summary)


async def _client(server: TestServer, password: str) -> tuple[TechnicolorClient, aiohttp.ClientSession]:
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    return TechnicolorClient(session, f"127.0.0.1:{server.port}", "admin", password), session


async def test_client_login_relogin_reboot(socket_enabled) -> None:
    router = MockRouter()
    async with TestServer(router.app()) as server:
        client, session = await _client(server, "SECRET1234")
        async with session:
            html = await client.async_get("modals/device-modal.lp")
            assert "EdgeRouter-X" in html and router.logins == 1
            router.expire_sessions()
            html = await client.async_get("modals/device-modal.lp")
            assert "EdgeRouter-X" in html and router.logins == 2
            await client.async_reboot()
            assert router.reboots == 1
            probe = await client.async_probe()
            assert probe["modals/device-modal.lp"]["tables"][0]["headers"][0] == "Status"
            assert "ajax/internet.lua" in probe
            assert not any("reboot" in p for p in probe)


async def test_client_wrong_password(socket_enabled) -> None:
    router = MockRouter()
    async with TestServer(router.app()) as server:
        client, session = await _client(server, "wrong")
        async with session:
            with pytest.raises(TechnicolorAuthError):
                await client.async_login()


@pytest.mark.parametrize(
    ("html", "token"),
    [
        ('<meta name="CSRFtoken" content="abc123def456">', "abc123def456"),
        ("<meta content='abc123def456' name='CSRFtoken'/>", "abc123def456"),
        ("<meta name=CSRFtoken content=abc123def456>", "abc123def456"),
        ('<META NAME="CSRFtoken"\n      CONTENT="abc123def456" />', "abc123def456"),
        ('<input type="hidden" name="CSRFtoken" value="abc123def456">', "abc123def456"),
        ('<script>var CSRFtoken = "abc123def456";</script>', "abc123def456"),
        ('<meta name="CSRFtoken" content="">', None),
    ],
)
def test_csrf_variants(html, token) -> None:
    from custom_components.technicolor_homeware.parser import extract_csrf

    assert extract_csrf(html) == token


async def test_follows_https_style_redirect(socket_enabled) -> None:
    """The router moves http:// to another origin; login must POST there, not to the old one."""
    from aiohttp import web

    router = MockRouter()
    async with TestServer(router.app()) as real:
        front = web.Application()

        async def redirect(request: web.Request) -> web.Response:
            raise web.HTTPFound(f"http://127.0.0.1:{real.port}{request.path_qs}")

        front.router.add_route("*", "/{tail:.*}", redirect)
        async with TestServer(front) as entry:
            client, session = await _client(entry, "SECRET1234")
            async with session:
                html = await client.async_get("modals/device-modal.lp")
                assert "EdgeRouter-X" in html
                assert client.base_url == f"http://127.0.0.1:{real.port}"
                assert router.logins == 1
