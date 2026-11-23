"""SRP-6 client used by the Technicolor Homeware web interface.

Port of the modified pysrp client used by the Technicolor/Homeware login page
(SHA-256, 2048-bit RFC 5054 group, fixed multiplier k). Pure Python, no deps.
Based on https://github.com/cocagne/pysrp (MIT) and pytechnicolor (MIT).
"""

from __future__ import annotations

import hashlib
import hmac
import os

_N_HEX = (
    "AC6BDB41324A9A9BF166DE5E1389582FAF72B6651987EE07FC3192943DB56050A37329CBB4"
    "A099ED8193E0757767A13DD52312AB4B03310DCD7F48A9DA04FD50E8083969EDB767B0CF60"
    "95179A163AB3661A05FBD5FAAAE82918A9962F0B93B855F97993EC975EEAA80D740ADBF4FF"
    "747359D041D5C33EA71D281E446B14773BCA97B43A23FB801676BD207A436C6481F1D2B907"
    "8717461A5B9D32E688F87748544523B524B0D57D5EA77A2775D2ECFA032CFBDBF52FB37861"
    "60279004E57AE6AF874E7303CE53299CCC041C7BC308D82A5698F3A8D0C38271AE35F8E9DB"
    "FBB694B5C803D89F7AE435DE236D525F54759B65E372FCD68EF20FA7111F9E4AFF73"
)
N = int(_N_HEX, 16)
G = 2
# The router uses this fixed multiplier (SRP-6 style) instead of H(N, g).
K = int("05b9e8ef059c6b32ea59fc1d322d37f04aa30bae5aa9003b8321e21ddb04e300", 16)


def long_to_bytes(value: int) -> bytes:
    """Big-endian bytes without leading zeros (b'' for 0, like pysrp)."""
    if value == 0:
        return b""
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def bytes_to_long(data: bytes) -> int:
    """Big-endian bytes to int."""
    return int.from_bytes(data, "big")


def _to_bytes(value: int | str | bytes) -> bytes:
    if isinstance(value, int):
        return long_to_bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    return value


def hash_int(*args: int | str | bytes) -> int:
    """SHA-256 over the concatenated arguments, as an int."""
    digest = hashlib.sha256()
    for arg in args:
        digest.update(_to_bytes(arg))
    return int(digest.hexdigest(), 16)


def _sha(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _hn_xor_hg() -> bytes:
    h_n = _sha(long_to_bytes(N))
    h_g = _sha(long_to_bytes(G))
    return bytes(a ^ b for a, b in zip(h_n, h_g, strict=True))


class SrpUser:
    """Client side of the router's SRP handshake."""

    def __init__(self, username: str, password: str, secret_a: int | None = None) -> None:
        """Generate the ephemeral key pair (CPU heavy: run in an executor)."""
        self.username = username
        self._password = password
        if secret_a is None:
            secret_a = bytes_to_long(os.urandom(32)) | (1 << 255)
        self._a = secret_a
        self.A = pow(G, self._a, N)
        self._h_amk: bytes | None = None

    def start(self) -> tuple[str, str]:
        """Return (I, A as lowercase hex) for the first /authenticate call."""
        return self.username, long_to_bytes(self.A).hex()

    def process_challenge(self, salt_hex: str, b_hex: str) -> str | None:
        """Return M as hex for the second /authenticate call (CPU heavy)."""
        salt = bytes_to_long(bytes.fromhex(salt_hex))
        big_b = bytes_to_long(bytes.fromhex(b_hex))
        if big_b % N == 0:
            return None
        u = hash_int(self.A, big_b)
        if u == 0:
            return None
        x = hash_int(salt, hash_int(f"{self.username}:{self._password}"))
        v = pow(G, x, N)
        secret = pow(big_b - K * v, self._a + u * x, N)
        session_key = _sha(long_to_bytes(secret))
        m = _sha(
            _hn_xor_hg()
            + _sha(self.username.encode("utf-8"))
            + long_to_bytes(salt)
            + long_to_bytes(self.A)
            + long_to_bytes(big_b)
            + session_key
        )
        self._h_amk = _sha(long_to_bytes(self.A) + m + session_key)
        return m.hex()

    def verify_session(self, server_m_hex: str) -> bool:
        """Check the server's proof (H(A, M, K))."""
        if self._h_amk is None:
            return False
        try:
            server_m = bytes.fromhex(server_m_hex)
        except ValueError:
            return False
        return hmac.compare_digest(self._h_amk, server_m)
