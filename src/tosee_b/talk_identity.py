"""Identify an HA user using the authenticated HA WebSocket API."""

import asyncio
import json

from websockets.asyncio.client import connect


HA_WS_URL = "ws://192.168.1.40:8123/api/websocket"


async def identify_ha_user(token):
    if not isinstance(token, str) or not 20 <= len(token) <= 8192:
        return None

    try:
        async with asyncio.timeout(5):
            async with connect(HA_WS_URL, max_size=16384) as ws:
                hello = json.loads(await ws.recv())
                if hello.get("type") != "auth_required":
                    return None

                await ws.send(json.dumps({
                    "type": "auth",
                    "access_token": token,
                }))

                auth = json.loads(await ws.recv())
                if auth.get("type") != "auth_ok":
                    return None

                await ws.send(json.dumps({
                    "id": 1,
                    "type": "auth/current_user",
                }))

                result = json.loads(await ws.recv())
                if result.get("type") != "result":
                    return None
                if result.get("id") != 1 or not result.get("success"):
                    return None

                user = result.get("result", {})
                user_id = user.get("id")

                if not isinstance(user_id, str) or not user_id:
                    return None

                return {
                    "id": user_id,
                    "is_owner": user.get("is_owner") is True,
                }

    except (OSError, TimeoutError, ValueError, TypeError, KeyError):
        return None
