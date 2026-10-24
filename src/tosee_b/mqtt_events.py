"""Publish ToSee-B events to MQTT without retained messages."""

import os
import threading

import paho.mqtt.client as mqtt


TOPICS = {
    "motion": "tosee_b/event/motion",
    "doorbell": "tosee_b/event/doorbell",
}


def publish_event(kind, environ=None):
    """Publish one event to the existing MQTT broker."""
    if kind not in TOPICS:
        raise ValueError(f"Unknown ToSee-B event: {kind}")

    env = os.environ if environ is None else environ

    required = (
        "TOSEE_MQTT_HOST",
        "TOSEE_MQTT_USERNAME",
        "TOSEE_MQTT_PASSWORD",
    )
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise ValueError(
            "Missing MQTT environment variables: " + ", ".join(missing)
        )

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="tosee_b_events",
    )
    client.username_pw_set(
        env["TOSEE_MQTT_USERNAME"],
        env["TOSEE_MQTT_PASSWORD"],
    )

    connected = threading.Event()
    connection_result = {"error": None}

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            connection_result["error"] = str(reason_code)
        connected.set()

    client.on_connect = on_connect

    try:
        client.connect(
            env["TOSEE_MQTT_HOST"],
            int(env.get("TOSEE_MQTT_PORT", "1883")),
            keepalive=30,
        )
        client.loop_start()

        if not connected.wait(timeout=5):
            raise TimeoutError("MQTT connection confirmation timed out")

        if connection_result["error"] is not None:
            raise RuntimeError(
                "MQTT connection rejected: "
                + connection_result["error"]
            )

        info = client.publish(
            TOPICS[kind],
            payload="ON",
            qos=1,
            retain=False,
        )

        info.wait_for_publish(timeout=5)
        if not info.is_published():
            raise TimeoutError("MQTT publish confirmation timed out")

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed: {info.rc}")
    finally:
        client.disconnect()
        client.loop_stop()
