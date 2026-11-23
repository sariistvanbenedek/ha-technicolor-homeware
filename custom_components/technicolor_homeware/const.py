"""Constants for the Technicolor Homeware integration."""

from datetime import timedelta

DOMAIN = "technicolor_homeware"

DEFAULT_HOST = "192.168.1.1"
DEFAULT_USERNAME = "admin"

SCAN_INTERVAL = timedelta(seconds=30)
SLOW_REFRESH_SECONDS = 300

HOME_PAGE = "/"
DEVICE_PAGES = ("modals/device-modal.lp", "modals/ipv6devices-modal.lp")
INFO_PAGES = ("modals/system-info-modal.lp", "modals/gateway-modal.lp")
GATEWAY_PAGE = "modals/gateway-modal.lp"
INTERNET_PAGE = "modals/internet-modal.lp"

# Pages the diagnostics probe always tries (read-only GET requests).
PROBE_PAGES = (
    "/",
    "modals/gateway-modal.lp",
    "modals/system-info-modal.lp",
    "modals/device-modal.lp",
    "modals/internet-modal.lp",
    "modals/broadband-modal.lp",
    "modals/ethernet-modal.lp",
    "modals/gpon-modal.lp",
    "modals/optical-modal.lp",
    "modals/sfp-modal.lp",
    "modals/diagnostics-connection-modal.lp",
    "modals/diagnostics-network-modal.lp",
)
# Never fetched by the probe: actions, credentials, Wi-Fi keys.
PROBE_SKIP = (
    "reset", "reboot", "restart", "upgrade", "logout", "signout", "password",
    "user", "assist", "remote", "voice", "sip", "mmpbx",
    "backup", "restore", "config", "ping", "traceroute", "qrcode",
)
SETTINGS_REFRESH_SECONDS = 60
SWITCH_SPEC_FILE = "switches.json"
PROBE_MAX_PAGES = 45
