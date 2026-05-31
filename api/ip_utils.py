"""
ip_utils.py — IPv6-safe LAN check for the orchestrator.

Key fix: Python's ipaddress raises TypeError (not ValueError) when
comparing an IPv4 address against an IPv6 network. Catch both.
"""
from __future__ import annotations
import ipaddress
import os
from fastapi import HTTPException, Request

# ── Network ranges ────────────────────────────────────────────────────────────
_LAN_NETS = [
    # IPv4
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local
    # IPv6
    ipaddress.ip_network("::1/128"),           # loopback
    ipaddress.ip_network("fe80::/10"),         # link-local
    ipaddress.ip_network("fc00::/7"),          # ULA
]

_LOCALHOST = {"127.0.0.1", "::1", "0:0:0:0:0:0:0:1"}


def strip_ip(ip: str) -> str:
    """Strip ::ffff: prefix (IPv4-mapped IPv6) and IPv6 zone id."""
    if "%" in ip:
        ip = ip.split("%")[0]
    if ip.lower().startswith("::ffff:"):
        ip = ip[7:]
    return ip.strip()


def is_lan(ip: str) -> bool:
    """
    Return True if ip is on the local network (IPv4 or IPv6).
    Catches TypeError for mixed IPv4/IPv6 network comparisons.
    """
    ip = strip_ip(ip)
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for net in _LAN_NETS:
        try:
            if addr in net:
                return True
        except TypeError:
            pass   # mixed version (IPv4 addr vs IPv6 net) — skip
    return False


def is_localhost(ip: str) -> bool:
    return strip_ip(ip) in _LOCALHOST


def get_client_ip(request: Request) -> str:
    """
    Real client IP — reads X-Forwarded-For first (set by Vite/nginx proxy),
    then X-Real-IP, then direct TCP connection. Strips ::ffff: and zone ids.
    """
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return strip_ip(xff.split(",")[0].strip())
    xri = request.headers.get("x-real-ip", "").strip()
    if xri:
        return strip_ip(xri)
    ip = (request.client.host if request.client else "") or "0.0.0.0"
    return strip_ip(ip)


def check_access(ip: str, access_mode: str, label: str = "This endpoint") -> None:
    """
    Enforce access mode:
      "lan"       → any private/LAN IP (default)
      "localhost"  → 127.x / ::1 only
    Raises HTTP 403 if access is denied.
    """
    if access_mode == "localhost":
        if not is_localhost(ip):
            raise HTTPException(
                403,
                f"{label} is restricted to the server machine (your IP: {ip}). "
                "Set access mode to 'lan' to allow LAN access.",
            )
    else:  # "lan"
        if not is_lan(ip):
            raise HTTPException(
                403,
                f"{label} is only accessible from the local network (your IP: {ip}).",
            )
