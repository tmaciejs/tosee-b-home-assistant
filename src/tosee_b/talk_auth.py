"""Verify a Home Assistant access token without storing it."""

import urllib.error
import urllib.request


HA_API_URL = "http://192.168.1.40:8123/api/"


def verify_ha_token(token):
    if not isinstance(token, str) or not 20 <= len(token) <= 8192:
        return False

    try:
        request = urllib.request.Request(
            HA_API_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False
