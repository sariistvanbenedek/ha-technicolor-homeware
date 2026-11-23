"""A fake Homeware web UI with a real SRP-6 server side, for tests."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import secrets

from aiohttp import web

from custom_components.technicolor_homeware.srp6 import (
    G,
    K,
    N,
    bytes_to_long,
    hash_int,
    long_to_bytes,
)

FIXTURES = Path(__file__).parent / "fixtures"

LOGIN_PAGE = """<!DOCTYPE html><html><head><meta name="CSRFtoken" content="{token}">
<script src="/js/srp-min.js"></script></head><body><form id="login">
<input type="password" id="srp_password"><div id="sign-me-in" class="btn">Sign in</div>
</form></body></html>"""

GATEWAY_MODAL = """<div class="modal-header"><h2>Gateway</h2></div><div class="modal-body">
<form class="form-horizontal"><fieldset>
<div class="control-group"><label class="control-label">Uptime</label><div class="controls">
<span class="simple-desc">19 days 6 hours 13 minutes 8 seconds</span></div></div>
<div id="btn-system-reboot" class="btn">Reboot</div></fieldset></form></div>
<script>$("#btn-system-reboot").click(function(){$.post("/modals/gateway-modal.lp",
{action:"system_reboot",CSRFtoken:$("meta[name=CSRFtoken]").attr("content")});});</script>"""


def _sha(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


class MockRouter:
    """State of the fake router."""

    def __init__(self, username: str = "admin", password: str = "SECRET1234") -> None:
        self.username = username
        self.salt = os.urandom(16)
        x = hash_int(bytes_to_long(self.salt), hash_int(f"{username}:{password}"))
        self.verifier = pow(G, x, N)
        self.sessions: dict[str, dict] = {}
        self.logins = 0
        self.reboots = 0
        self.requests: list[str] = []
        self.device_page = "device-modal.lp.txt"

    def expire_sessions(self) -> None:
        for session in self.sessions.values():
            session["auth"] = False

    def _session(self, request: web.Request, response: web.StreamResponse | None = None) -> dict:
        sid = request.cookies.get("sessionID")
        if sid not in self.sessions:
            sid = secrets.token_hex(8)
            self.sessions[sid] = {"auth": False, "token": secrets.token_hex(16)}
            request["new_sid"] = sid
        return self.sessions[sid]

    def _respond(self, request: web.Request, text: str, status: int = 200, content_type: str = "text/html") -> web.Response:
        resp = web.Response(text=text, status=status, content_type=content_type)
        if sid := request.get("new_sid"):
            resp.set_cookie("sessionID", sid, path="/", httponly=True)
        return resp

    async def login_page(self, request: web.Request) -> web.Response:
        session = self._session(request)
        return self._respond(request, LOGIN_PAGE.format(token=session["token"]))

    async def home(self, request: web.Request) -> web.Response:
        session = self._session(request)
        if not session["auth"]:
            return self._respond(request, LOGIN_PAGE.format(token=session["token"]))
        html = (FIXTURES / "home.html").read_text(encoding="utf-8")
        html = html.replace("<head>", f'<head><meta name="CSRFtoken" content="{session["token"]}">', 1)
        return self._respond(request, html)

    async def authenticate(self, request: web.Request) -> web.Response:
        session = self._session(request)
        data = await request.post()
        if data.get("CSRFtoken") != session["token"]:
            return self._respond(request, "Forbidden", status=403)
        if "I" in data:
            secret_b = bytes_to_long(os.urandom(32))
            big_a = bytes_to_long(bytes.fromhex(data["A"]))
            big_b = (K * self.verifier + pow(G, secret_b, N)) % N
            session.update(I=data["I"], A=big_a, b=secret_b, B=big_b)
            return self._json(request, f'{{"s":"{self.salt.hex()}","B":"{long_to_bytes(big_b).hex()}"}}')
        if "M" in data and "A" in session:
            big_a, big_b = session["A"], session["B"]
            u = hash_int(big_a, big_b)
            secret = pow(big_a * pow(self.verifier, u, N), session["b"], N)
            key = _sha(long_to_bytes(secret))
            hnxg = bytes(a ^ b for a, b in zip(_sha(long_to_bytes(N)), _sha(long_to_bytes(G))))
            expected = _sha(
                hnxg + _sha(session["I"].encode()) + self.salt + long_to_bytes(big_a) + long_to_bytes(big_b) + key
            )
            if session["I"] != self.username or data["M"] != expected.hex():
                return self._json(request, '{"error":{"msg":"failed","waitTime":3,"wrongCount":1}}')
            session["auth"] = True
            self.logins += 1
            return self._json(request, f'{{"M":"{_sha(long_to_bytes(big_a) + expected + key).hex()}"}}')
        return self._json(request, '{"error":{"msg":"failed"}}')

    def _json(self, request: web.Request, text: str) -> web.Response:
        return self._respond(request, text, content_type="application/json")

    async def modal(self, request: web.Request) -> web.Response:
        session = self._session(request)
        name = request.match_info["name"]
        self.requests.append(name)
        if not session["auth"]:
            return self._respond(request, LOGIN_PAGE.format(token=session["token"]))
        if request.method == "POST":
            data = await request.post()
            if data.get("CSRFtoken") != session["token"]:
                return self._respond(request, "Forbidden", status=403)
            if name == "gateway-modal" and data.get("action") == "system_reboot":
                self.reboots += 1
            return self._respond(request, "{}", content_type="application/json")
        files = {
            "device-modal": self.device_page,
            "system-info-modal": "system-info-modal.lp",
            "broadband-modal": "broadband-modal.lp",
            "diagnostics-connection-modal": "diagnostics-connection-modal.lp",
        }
        if name == "gateway-modal":
            return self._respond(request, GATEWAY_MODAL)
        if name not in files:
            return self._respond(request, "Not found", status=404)
        return self._respond(request, (FIXTURES / files[name]).read_text(encoding="utf-8"))

    async def ajax(self, request: web.Request) -> web.Response:
        session = self._session(request)
        if not session["auth"]:
            return self._respond(request, "Forbidden", status=403)
        return self._json(request, '{"wan_ip":"77.126.41.183","status":"connected"}')

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", self.home)
        app.router.add_get("/login.lp", self.login_page)
        app.router.add_post("/authenticate", self.authenticate)
        app.router.add_route("*", "/modals/{name}.lp", self.modal)
        app.router.add_get("/ajax/{name}.lua", self.ajax)
        return app
