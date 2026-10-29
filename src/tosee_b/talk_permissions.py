"""Explicit allowlist for Home Assistant talkback users."""

import os


def can_use_talkback(user):
    """Deny by default; grant access only to configured HA user IDs."""
    if not isinstance(user, dict):
        return False

    user_id = user.get("id")
    if not isinstance(user_id, str) or not user_id:
        return False

    configured = os.environ.get("TOSEE_TALK_ALLOWED_USERS", "")
    allowed = {
        item.strip()
        for item in configured.split(",")
        if item.strip()
    }

    return user_id in allowed
