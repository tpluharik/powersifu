import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from powersifu.config import ConfigStore, sanitize_config, sync_autostart


class ConfigTests(unittest.TestCase):
    def test_invalid_profiles_fall_back_to_defaults(self):
        config = sanitize_config(
            {
                "automation": {
                    "enabled": True,
                    "ac_profile": "turbo",
                    "battery_profile": "silent",
                    "poll_seconds": 1,
                }
            }
        )
        self.assertEqual(config["automation"]["ac_profile"], "balanced")
        self.assertEqual(config["automation"]["battery_profile"], "power-saver")
        self.assertEqual(config["automation"]["poll_seconds"], 2)

    def test_store_round_trip_is_private_and_valid_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            store = ConfigStore(path)
            store.load()
            store.data["automation"]["ac_profile"] = "performance"
            store.save()
            self.assertEqual(json.loads(path.read_text())["automation"]["ac_profile"], "performance")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_autostart_override_can_disable_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": temporary}):
                path = sync_autostart(False)
                content = path.read_text()
                self.assertIn("Hidden=true", content)
                self.assertIn("X-GNOME-Autostart-enabled=false", content)

    def test_invalid_schedule_days_are_ignored(self):
        config = sanitize_config(
            {
                "schedules": [
                    {
                        "enabled": True,
                        "label": "Bad input",
                        "time": "08:00",
                        "days": ["not-a-day"],
                        "profile": "balanced",
                    }
                ]
            }
        )
        self.assertEqual(config["schedules"], [])


if __name__ == "__main__":
    unittest.main()
