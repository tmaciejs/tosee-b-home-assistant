"""Tests for the ToSee-B event service configuration."""

import tempfile
import unittest
from pathlib import Path

from tosee_b.event_service import load_env_file


class TestEventService(unittest.TestCase):

    def test_load_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.env"
            path.write_text(
                "# MQTT configuration\n"
                "TOSEE_MQTT_HOST=192.168.1.40\n"
                "TOSEE_MQTT_PORT=1883\n"
                "TOSEE_MQTT_USERNAME=tosee_mqtt\n"
            )

            settings = load_env_file(path)

            self.assertEqual(
                settings["TOSEE_MQTT_HOST"], "192.168.1.40"
            )
            self.assertEqual(
                settings["TOSEE_MQTT_PORT"], "1883"
            )
            self.assertEqual(
                settings["TOSEE_MQTT_USERNAME"], "tosee_mqtt"
            )

    def test_password_with_equals_sign(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.env"
            path.write_text("TOSEE_MQTT_PASSWORD=abc=123=xyz\n")

            settings = load_env_file(path)

            self.assertEqual(
                settings["TOSEE_MQTT_PASSWORD"], "abc=123=xyz"
            )


if __name__ == "__main__":
    unittest.main()
