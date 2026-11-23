"""HTML parsing for Technicolor Homeware web pages (pure functions, no HA deps)."""

from __future__ import annotations

import ipaddress
import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
IPV4_RE = re.compile(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b")
NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
CSRF_RES = (
    re.compile(r"""<meta\b[^>]*?\bname\s*=\s*["']?CSRFtoken\b["']?[^>]*?\bcontent\s*=\s*["']?([^"'\s>]+)""", re.I),
    re.compile(r"""<meta\b[^>]*?\bcontent\s*=\s*["']?([^"'\s>]+)["']?[^>]*?\bname\s*=\s*["']?CSRFtoken\b""", re.I),
    re.compile(r"""\bname\s*=\s*["']?CSRFtoken\b["']?[^>]*?\bvalue\s*=\s*["']?([^"'\s>]+)""", re.I),
    re.compile(r"""\bCSRFtoken["']?\s*[:=]\s*["']([0-9A-Za-z_\-+/=]{8,})["']"""),
)
LINK_RE = re.compile(r"""(?:^|["'/\s])(modals/[A-Za-z0-9_\-]+\.lp)""")
AJAX_RE = re.compile(r"""(?:^|["'/\s])(ajax/[A-Za-z0-9_\-]+\.lua)""")

COLORS = ("green", "red", "orange", "yellow", "blue", "off", "gray", "grey")
SENSITIVE_NAME = ("pass", "psk", "key", "secret", "user", "pin", "ssid", "token")

_NEG_RE = re.compile(
    r"(disconnected|not connected|no connection|offline|link down|\bdown\b|"
    r"disabled|nincs|bontva|lecsatlakoz|kapcsolat n[eé]lk|inakt[ií]v|connecting)",
    re.I,
)
_POS_RE = re.compile(
    r"(connected|\bup\b|online|link up|csatlakozva|csatlakoztatva|kapcsol[oó]dva|"
    r"akt[ií]v|\bactive\b|el[eé]rhet[oő])",
    re.I,
)

_DURATION_UNITS = {
    "d": 86400, "day": 86400, "days": 86400, "nap": 86400, "napja": 86400,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "óra": 3600, "ó": 3600,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "perc": 60, "p": 60,
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "mp": 1, "másodperc": 1,
}


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_csrf(html: str) -> str | None:
    """Return the CSRF token from a page, if present."""
    for regex in CSRF_RES:
        if match := regex.search(html):
            return match.group(1)
    if "csrftoken" in html.lower():
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["meta", "input"]):
            name = (tag.get("name") or tag.get("id") or "").lower()
            if name == "csrftoken" and (value := tag.get("content") or tag.get("value")):
                return value.strip()
    return None


def is_login_page(html: str, *, modal: bool) -> bool:
    """Detect the Homeware sign-in page (returned when the session expired)."""
    lowered = html.lower()
    if "sign-me-in" in lowered or 'id="srp_password"' in lowered or "name=\"srp_password\"" in lowered:
        return True
    if modal and ("srp-min.js" in lowered or "/js/srp" in lowered or 'id="signin"' in lowered):
        return True
    return False


_ENDPOINT_RE = re.compile(
    r"""["'](/?[A-Za-z0-9_\-./]*(?:login|auth|session|api|srp|token)[A-Za-z0-9_\-./]*)["']""", re.I
)


def page_fingerprint(html: str) -> str:
    """Short description of an unexpected page for error logs (never input values)."""
    soup = BeautifulSoup(html, "html.parser")
    parts: list[str] = []
    if soup.title and soup.title.string:
        parts.append(f"title={_clean(soup.title.string)[:60]!r}")
    metas = [m.get("name") for m in soup.find_all("meta") if m.get("name")]
    if metas:
        parts.append(f"meta={metas[:10]}")
    for tag in re.findall(r"<meta[^>]*csrf[^>]*>", html, re.I)[:2]:
        hidden = re.sub(
            r"""(content\s*=\s*["']?)([^"'\s>]*)""", lambda m: f"{m.group(1)}<{len(m.group(2))} chars>", tag, flags=re.I
        )
        parts.append(f"csrf_tag={hidden[:160]!r}")
    refresh = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
    if refresh is not None:
        parts.append(f"refresh={refresh.get('content', '')[:80]!r}")
    scripts = [s.get("src") for s in soup.find_all("script") if s.get("src")]
    if scripts:
        parts.append(f"js={scripts[:12]}")
    forms = [f.get("action") or "" for f in soup.find_all("form")]
    if forms:
        parts.append(f"forms={forms[:5]}")
    inputs = [f"{i.get('type', 'text')}:{i.get('name') or i.get('id') or ''}" for i in soup.find_all("input")]
    if inputs:
        parts.append(f"inputs={inputs[:15]}")
    endpoints = sorted({e for e in _ENDPOINT_RE.findall(html) if not e.endswith((".png", ".gif", ".css"))})
    if endpoints:
        parts.append(f"endpoints={endpoints[:15]}")
    redirect = re.search(r"""location(?:\.href)?\s*=\s*["']([^"']+)""", html)
    if redirect:
        parts.append(f"js_redirect={redirect.group(1)[:80]!r}")
    for tag in soup(["script", "style"]):
        tag.decompose()
    parts.append(f"text={_clean(soup.get_text(' ', strip=True))[:160]!r}")
    parts.append(f"bytes={len(html)}")
    return " ".join(parts)


def text_state(text: str | None) -> bool | None:
    """Interpret a status text as connected (True) / not (False) / unknown."""
    if not text:
        return None
    if _NEG_RE.search(text):
        return False
    if _POS_RE.search(text):
        return True
    return None


def color_state(color: str | None) -> bool | None:
    """Interpret a status light colour."""
    if color == "green":
        return True
    if color in ("red", "off", "gray", "grey"):
        return False
    return None


def parse_duration(text: str | None) -> int | None:
    """Parse '19 days 6 hours 13 minutes 8 seconds', '0d 10:39:22', '3 nap 4 óra'."""
    if not text:
        return None
    text = text.lower()
    total = 0
    found = False
    if match := re.search(r"(?:(\d+)\s*(?:d|days?|nap)\s*,?\s*)?(\d{1,3}):(\d{2}):(\d{2})", text):
        days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
        return days * 86400 + hours * 3600 + minutes * 60 + seconds
    for number, unit in re.findall(r"(\d+)\s*([a-záéíóöőúüű]+)", text):
        unit = unit.rstrip(".,")
        if unit in _DURATION_UNITS:
            total += int(number) * _DURATION_UNITS[unit]
            found = True
    return total if found else None


def first_number(text: str | None) -> float | None:
    """First number in a text ('86 %' -> 86.0, '1,5 Mbps' -> 1.5)."""
    if not text:
        return None
    if match := NUMBER_RE.search(text):
        try:
            return float(match.group(0).replace(",", "."))
        except ValueError:
            return None
    return None


def normalize_mac(value: str) -> str:
    """aa:bb:cc:dd:ee:ff lower case."""
    return value.replace("-", ":").lower()


def is_public_ipv4(value: str) -> bool:
    """True for a globally routable IPv4 address."""
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _color_of(node: Tag) -> str | None:
    for el in node.select(".light, i, span.icon, div.icon"):
        for cls in el.get("class", []):
            if cls in COLORS:
                return cls
    return None


def _control_value(controls: Tag) -> str:
    text = _clean(controls.get_text(" ", strip=True))
    radios = controls.select("input[type=radio]")
    if radios:
        for radio in radios:
            if radio.has_attr("checked"):
                parent = radio.find_parent("label")
                return _clean(parent.get_text(" ", strip=True)) if parent else radio.get("value", "")
        return ""
    if text:
        return text
    select = controls.find("select")
    if select is not None:
        option = select.find("option", selected=True)
        if option is not None:
            return _clean(option.get_text(" ", strip=True))
    switch = controls.select_one(".switch input[type=hidden]")
    if switch is not None and not _is_sensitive(switch.get("name", "")):
        return "on" if switch.get("value") == "1" else "off"
    return ""


def _is_sensitive(name: str) -> bool:
    name = name.lower()
    return any(part in name for part in SENSITIVE_NAME)


def _unique_key(store: dict[str, Any], key: str) -> str:
    if key not in store:
        return key
    index = 2
    while f"{key} #{index}" in store:
        index += 1
    return f"{key} #{index}"


def parse_page(html: str) -> dict[str, Any]:
    """Parse any Homeware page into a generic, JSON-friendly structure."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    title_el = soup.find(["h2", "h1"])
    result: dict[str, Any] = {
        "title": _clean(title_el.get_text(" ", strip=True)) if title_el else "",
        "fields": {},
        "states": {},
        "tables": [],
        "cards": {},
        "popups": [],
        "ids": {},
    }

    for group in soup.select(".control-group"):
        label = group.find("label", class_="control-label")
        controls = group.find(class_="controls")
        if label is None or controls is None or controls.find("table") is not None:
            continue
        key = _clean(label.get_text(" ", strip=True)).rstrip(":")
        if not key:
            continue
        key = _unique_key(result["fields"], key)
        result["fields"][key] = _control_value(controls)
        if color := _color_of(controls):
            result["states"][key] = color

    for table in soup.find_all("table"):
        headers = [_clean(th.get_text(" ", strip=True)) for th in table.select("thead th")]
        body_rows = table.select("tbody tr") or table.find_all("tr")
        if not headers and body_rows:
            first_th = body_rows[0].find_all("th")
            if first_th:
                headers = [_clean(th.get_text(" ", strip=True)) for th in first_th]
        rows = []
        for row in body_rows:
            cells = row.find_all("td")
            if not cells:
                continue
            rows.append(
                [{"text": _clean(td.get_text(" ", strip=True)), "color": _color_of(td)} for td in cells]
            )
        result["tables"].append({"id": table.get("id", ""), "headers": headers, "rows": rows})

    for card in soup.select(".smallcard"):
        classes = card.get("class", [])
        if "popUp" in classes:
            continue
        title = card.select_one(".header-title")
        content = card.select_one(".content") or card
        name = _clean(title.get_text(" ", strip=True)) if title else ""
        if not name:
            continue
        lights = [
            cls
            for el in content.select(".light, i")
            for cls in el.get("class", [])
            if cls in COLORS
        ]
        remote = card.find(attrs={"data-remote": True})
        name = _unique_key(result["cards"], name)
        result["cards"][name] = {
            "text": _clean(content.get_text(" ", strip=True)),
            "lights": lights,
            "remote": remote.get("data-remote") if remote else None,
        }

    seen_popup_macs: set[str] = set()
    for popup in soup.select("div.popUp"):
        text = _clean(popup.get_text(" ", strip=True))
        mac = MAC_RE.search(text)
        if not mac or normalize_mac(mac.group(0)) in seen_popup_macs:
            continue
        seen_popup_macs.add(normalize_mac(mac.group(0)))
        title = popup.select_one(".device_poptitle, .header-title")
        result["popups"].append(
            {"title": _clean(title.get_text(" ", strip=True)) if title else "", "text": text}
        )

    for el in soup.find_all(id=True):
        if el.name in ("table", "form", "body", "html"):
            continue
        text = _clean(el.get_text(" ", strip=True))
        if text and len(text) <= 120 and el.get("id") not in result["ids"]:
            result["ids"][el["id"]] = text

    result["links"] = sorted(set(LINK_RE.findall(html)))
    result["ajax"] = sorted(set(AJAX_RE.findall(html)))
    return result


def _find_index(headers: list[str], groups: list[tuple[str, ...]], exclude: tuple[str, ...] = ()) -> int | None:
    lowered = [h.lower() for h in headers]
    for keys in groups:
        for index, header in enumerate(lowered):
            if any(ex in header for ex in exclude):
                continue
            if any(key in header for key in keys):
                return index
    return None


def _cell(row: list[dict[str, Any]], index: int | None) -> dict[str, Any] | None:
    if index is None or index >= len(row):
        return None
    return row[index]


def extract_devices(page: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Connected-device list from device-modal.lp (table or card layout)."""
    devices: dict[str, dict[str, Any]] = {}
    for table in page.get("tables", []):
        headers = table["headers"]
        rows = table["rows"]
        has_mac_header = any("mac" in h.lower() for h in headers)
        if not has_mac_header and not any(MAC_RE.search(c["text"]) for r in rows for c in r):
            continue
        i_status = _find_index(headers, [("status", "állapot", "statusz")])
        i_name = _find_index(
            headers,
            [("hostname", "host name", "gazdagép", "gépnév"), ("friendly", "name", "név"), ("device", "eszköz")],
            exclude=("type", "típus"),
        )
        i_ip = _find_index(headers, [("ipv4", "ip address", "ip-cím", "ip cím", "ip-address"), ("ip",)], exclude=("ipv6",))
        i_mac = _find_index(headers, [("mac",)])
        i_if = _find_index(
            headers, [("interface", "interfész", "csatlakozás"), ("port",), ("type", "típus"), ("connection", "kapcsolat")]
        )
        for row in rows:
            mac_cell = _cell(row, i_mac)
            mac_match = MAC_RE.search(mac_cell["text"]) if mac_cell else None
            if mac_match is None:
                mac_match = next((m for c in row if (m := MAC_RE.search(c["text"]))), None)
            if mac_match is None:
                continue
            mac = normalize_mac(mac_match.group(0))
            name_cell = _cell(row, i_name)
            ip_cell = _cell(row, i_ip)
            ip_match = IPV4_RE.search(ip_cell["text"]) if ip_cell else None
            if ip_match is None and i_ip is None:
                ip_match = next((m for c in row if (m := IPV4_RE.search(c["text"]))), None)
            connected: bool | None = True
            status_cell = _cell(row, i_status)
            if status_cell is not None:
                connected = color_state(status_cell["color"])
                if connected is None:
                    connected = text_state(status_cell["text"])
                if connected is None:
                    connected = True
            if_cell = _cell(row, i_if)
            devices[mac] = {
                "mac": mac,
                "name": (name_cell["text"] if name_cell else "") or "",
                "ip": ip_match.group(0) if ip_match else None,
                "interface": if_cell["text"] if if_cell else None,
                "connected": bool(connected),
            }
    if not devices:
        for popup in page.get("popups", []):
            mac_match = MAC_RE.search(popup["text"])
            if not mac_match:
                continue
            mac = normalize_mac(mac_match.group(0))
            ip_match = IPV4_RE.search(popup["text"])
            devices[mac] = {
                "mac": mac,
                "name": popup.get("title", ""),
                "ip": ip_match.group(0) if ip_match else None,
                "interface": None,
                "connected": True,
            }
    return devices


INFO_KEYS: dict[str, tuple[str, ...]] = {
    "vendor": ("product vendor", "gyártó", "vendor"),
    "product": ("product name", "termék neve", "terméknév", "model name", "modell"),
    "serial": ("serial number", "sorozatszám", "serial"),
    "firmware": ("firmware version", "firmware verzió", "firmware-verzió", "firmware"),
    "software": ("software version", "szoftver verzió", "szoftververzió", "szoftver"),
    "hardware": ("hardware version", "hardver verzió", "hardververzió", "hardver"),
    "mac": ("mac address", "mac-cím", "mac cím", "mac"),
    "uptime": ("uptime", "üzemidő", "működési idő", "bekapcsolási idő", "futási idő"),
    "cpu": ("cpu usage", "cpu-használat", "cpu terhelés", "processzor", "cpu"),
    "memory": ("memory usage", "memóriahasználat", "memória", "memory"),
}


def find_field(fields: dict[str, str], keys: tuple[str, ...]) -> str | None:
    """First non-empty field whose label contains one of the keys (in key order)."""
    lowered = {label.lower(): value for label, value in fields.items()}
    for key in keys:
        for label, value in lowered.items():
            if key in label and value:
                return value
    return None


def extract_info(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Gateway information (model, versions, uptime, load) from info pages."""
    fields: dict[str, str] = {}
    for page in pages:
        for label, value in page.get("fields", {}).items():
            fields.setdefault(label, value)
    info: dict[str, Any] = {}
    for name, keys in INFO_KEYS.items():
        info[name] = find_field(fields, keys)
    if info.get("mac"):
        mac = MAC_RE.search(info["mac"])
        info["mac"] = normalize_mac(mac.group(0)) if mac else None
    info["uptime_seconds"] = parse_duration(info.pop("uptime"))
    info["cpu"] = first_number(info.get("cpu"))
    info["memory"] = first_number(info.get("memory"))
    info["sw_version"] = info.get("firmware") or info.get("software")
    return info


def _card(cards: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any] | None:
    for title, card in cards.items():
        lowered = title.lower()
        if any(key in lowered for key in keys):
            return card
    return None


def _card_state(card: dict[str, Any]) -> bool | None:
    state = color_state(card["lights"][0]) if card.get("lights") else None
    if state is None:
        state = text_state(card.get("text"))
    return state


def extract_wan(home: dict[str, Any] | None, internet: dict[str, Any] | None = None) -> dict[str, Any]:
    """Internet (WAN) status and public IP."""
    wan: dict[str, Any] = {"connected": None, "ip": None, "status": None}
    if home:
        card = _card(home.get("cards", {}), ("internet",))
        if card:
            wan["connected"] = _card_state(card)
            wan["status"] = card["text"][:120] or None
            ips = [ip for ip in IPV4_RE.findall(card["text"]) if is_public_ipv4(ip)]
            wan["ip"] = ips[0] if ips else None
    if internet and (wan["ip"] is None or wan["connected"] is None):
        fields = internet.get("fields", {})
        states = internet.get("states", {})
        if wan["ip"] is None:
            for value in fields.values():
                ips = [ip for ip in IPV4_RE.findall(value) if is_public_ipv4(ip)]
                if ips:
                    wan["ip"] = ips[0]
                    break
        if wan["connected"] is None:
            for label, value in fields.items():
                if any(k in label.lower() for k in ("status", "állapot")):
                    state = color_state(states.get(label))
                    wan["connected"] = state if state is not None else text_state(value)
                    wan["status"] = value or wan["status"]
                    break
    return wan


def extract_broadband(home: dict[str, Any] | None) -> dict[str, Any]:
    """Broadband / fibre link state and line rates from the home page card."""
    result: dict[str, Any] = {"connected": None, "up": None, "down": None}
    if not home:
        return result
    card = _card(home.get("cards", {}), ("broadband", "szélessáv", "gpon", "optik", "fiber", "fibre", "optical"))
    if card:
        result["connected"] = _card_state(card)
    ids = home.get("ids", {})
    for key, value in ids.items():
        lowered = key.lower()
        if "rate" in lowered and "up" in lowered:
            result["up"] = first_number(value)
        elif "rate" in lowered and "down" in lowered:
            result["down"] = first_number(value)
    return result


# --- diagnostics helpers ---------------------------------------------------


def mask_text(text: str) -> str:
    """Hide the device-specific half of MACs and public IPv4 addresses."""
    text = MAC_RE.sub(lambda m: normalize_mac(m.group(0))[:8] + ":xx:xx:xx", text)
    return IPV4_RE.sub(
        lambda m: (".".join(m.group(0).split(".")[:2]) + ".x.x") if is_public_ipv4(m.group(0)) else m.group(0),
        text,
    )


def mask(obj: Any) -> Any:
    """Recursively mask strings for diagnostics output."""
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, dict):
        return {mask(k) if isinstance(k, str) else k: mask(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask(v) for v in obj]
    return obj


def summarize_page(path: str, status: int, html: str) -> dict[str, Any]:
    """Compact, masked description of a page for the diagnostics probe."""
    summary: dict[str, Any] = {"status": status, "bytes": len(html)}
    if path.endswith(".lua"):
        try:
            summary["json"] = mask(json.loads(html))
        except ValueError:
            summary["text"] = mask_text(html[:500])
        return summary
    summary["login_page"] = is_login_page(html, modal=path != "/")
    parsed = parse_page(html)
    serial_like = ("serial", "sorozat")
    fields = {
        k: ("***" if any(s in k.lower() for s in serial_like) else v) for k, v in list(parsed["fields"].items())[:80]
    }
    summary.update(
        {
            "title": parsed["title"],
            "fields": mask(fields),
            "states": parsed["states"],
            "tables": mask(
                [
                    {"id": t["id"], "headers": t["headers"], "rows": t["rows"][:6], "row_count": len(t["rows"])}
                    for t in parsed["tables"][:6]
                ]
            ),
            "cards": mask(parsed["cards"]),
            "popups": len(parsed["popups"]),
            "ids": mask(dict(list(parsed["ids"].items())[:80])),
            "links": parsed["links"],
            "ajax": parsed["ajax"],
            "has_system_reboot": "system_reboot" in html,
        }
    )
    return summary
