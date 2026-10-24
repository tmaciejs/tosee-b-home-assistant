"""Unit tests for ToSee-B MQTT event publishing."""

import unittest
from unittest.mock import MagicMock, patch

from tosee_b.mqtt_events import TOPICS, publish_event


ENV = {
    "TOSEE_MQTT_HOST": "127.0.0.1",
    "TOSEE_MQTT_PORT": "1883",
    "TOSEE_MQTT_USERNAME": "test_user",
    "TOSEE_MQTT_PASSWORD": "test_password",
}


class TestMQTTEvents(unittest.TestCase):

    def test_topics(self):
        self.assertEqual(TOPICS["motion"], "tosee_b/event/motion")
        self.assertEqual(TOPICS["doorbell"], "tosee_b/event/doorbell")

    def test_unknown_event(self):
        with self.assertRaises(ValueError):
            publish_event("unknown", environ=ENV)

    def test_missing_credentials(self):
        with self.assertRaises(ValueError):
            publish_event("motion", environ={})

    @patch("tosee_b.mqtt_events.mqtt.Client")
    def test_motion_publish(self, client_factory):
        client = MagicMock()
        client_factory.return_value = client

        def simulate_connect():
            reason_code = MagicMock()
            reason_code.is_failure = False
            client.on_connect(client, None, None, reason_code, None)

        client.loop_start.side_effect = simulate_connect
        client.publish.return_value.is_published.return_value = True
        client.publish.return_value.rc = 0

        publish_event("motion", environ=ENV)

        client.publish.assert_called_once_with(
            "tosee_b/event/motion",
            payload="ON",
            qos=1,
            retain=False,
        )
        client.disconnect.assert_called_once()

    @patch("tosee_b.mqtt_events.mqtt.Client")
    def test_doorbell_publish(self, client_factory):
        client = MagicMock()
        client_factory.return_value = client

        def simulate_connect():
            reason_code = MagicMock()
            reason_code.is_failure = False
            client.on_connect(client, None, None, reason_code, None)

        client.loop_start.side_effect = simulate_connect
        client.publish.return_value.is_published.return_value = True
        client.publish.return_value.rc = 0

        publish_event("doorbell", environ=ENV)

        client.publish.assert_called_once_with(
            "tosee_b/event/doorbell",
            payload="ON",
            qos=1,
            retain=False,
        )


if __name__ == "__main__":
    unittest.main()


class TestMQTTConnectionErrors(unittest.TestCase):

    @patch("tosee_b.mqtt_events.mqtt.Client")
    def test_connection_rejected(self, client_factory):
        client = MagicMock()
        client_factory.return_value = client

        def simulate_rejection():
            reason_code = MagicMock()
            reason_code.is_failure = True
            reason_code.__str__.return_value = "Bad username or password"
            client.on_connect(
                client, None, None, reason_code, None
            )

        client.loop_start.side_effect = simulate_rejection

        with self.assertRaisesRegex(
            RuntimeError, "MQTT connection rejected"
        ):
            publish_event("motion", environ=ENV)

        client.publish.assert_not_called()
        client.disconnect.assert_called_once()
