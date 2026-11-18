"""Network security, SSRF validation, and safe URL dispatch protections."""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse
from app.core.config import settings
from app.core.errors import SSRFSecurityError

# Cloud metadata and forbidden target hostnames
BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata.internal",
    "169.254.169.254",
    "instance-data",
}

# Special IPv4 / IPv6 subnets that must be blocked
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),  # Current network
    ipaddress.ip_network("10.0.0.0/8"),  # RFC 1918 Private
    ipaddress.ip_network("100.64.0.0/10"),  # Shared address space / CGNAT
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local & cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),  # RFC 1918 Private
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918 Private
    ipaddress.ip_network("198.18.0.0/15"),  # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved for future use
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    # IPv6
    ipaddress.ip_network("::/128"),  # Unspecified
    ipaddress.ip_network("::1/128"),  # Loopback
    ipaddress.ip_network("fc00::/7"),  # Unique local
    ipaddress.ip_network("fe80::/10"),  # Link-local
    ipaddress.ip_network("ff00::/8"),  # Multicast
]


def is_ip_blocked(ip_addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Checks whether an IP address falls within any blocked/private network range."""
    # Special exception for local development and test mode when loopback is explicitly enabled
    if settings.ALLOW_LOOPBACK_IN_DEV and settings.APP_ENV != "production":
        if ip_addr.is_loopback or str(ip_addr) in ("127.0.0.1", "::1"):
            return False

    if (
        ip_addr.is_loopback
        or ip_addr.is_private
        or ip_addr.is_link_local
        or ip_addr.is_reserved
        or ip_addr.is_multicast
    ):
        return True

    for net in BLOCKED_NETWORKS:
        if ip_addr in net:
            return True

    return False


def validate_provider_base_url(url: Optional[str]) -> Optional[str]:
    """Validates custom provider base URLs against SSRF, internal network probing, and cloud metadata access.

    Raises:
        SSRFSecurityError: If the URL targets internal networks, loopback (in prod), or cloud metadata.
    """
    if not url or not url.strip():
        return None

    cleaned_url = url.strip()
    parsed = urlparse(cleaned_url)

    # 1. Scheme validation
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFSecurityError(f"Invalid URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    if settings.APP_ENV == "production" and parsed.scheme.lower() != "https":
        raise SSRFSecurityError("Insecure protocol: HTTPS is strictly required for provider endpoints in production.")

    # 2. Hostname validation
    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityError("Provider base URL must include a valid hostname.")

    lower_host = hostname.lower()
    if lower_host in BLOCKED_HOSTNAMES or lower_host.endswith(".internal") or lower_host.endswith(".local"):
        raise SSRFSecurityError(f"Access to host '{hostname}' is prohibited (SSRF protection).")

    # If SSRF protection is disabled globally (e.g. specialized offline airgap test), return cleaned
    if not settings.SSRF_PROTECTION_ENABLED:
        return cleaned_url.rstrip("/")

    # 3. Direct IP checking
    try:
        direct_ip = ipaddress.ip_address(lower_host)
        if is_ip_blocked(direct_ip):
            raise SSRFSecurityError(f"Target destination IP '{direct_ip}' is in a restricted network range.")
        return cleaned_url.rstrip("/")
    except ValueError:
        # Not a raw IP literal, proceed to DNS resolution
        pass

    # In local/test mode, allow localhost if ALLOW_LOOPBACK_IN_DEV is enabled
    if lower_host == "localhost":
        if settings.ALLOW_LOOPBACK_IN_DEV and settings.APP_ENV != "production":
            return cleaned_url.rstrip("/")
        else:
            raise SSRFSecurityError("Access to localhost is prohibited in production mode.")

    # 4. DNS Resolution & Rebinding protection
    try:
        resolved_addresses = socket.getaddrinfo(lower_host, parsed.port or (443 if parsed.scheme == "https" else 80))
        for res in resolved_addresses:
            sockaddr = res[4]
            ip_str = sockaddr[0]
            resolved_ip = ipaddress.ip_address(ip_str)
            if is_ip_blocked(resolved_ip):
                raise SSRFSecurityError(
                    f"Host '{hostname}' resolves to restricted IP '{resolved_ip}' (SSRF protection)."
                )
    except socket.gaierror as exc:
        raise SSRFSecurityError(f"Failed to resolve provider hostname '{hostname}': {exc}")

    return cleaned_url.rstrip("/")
