import subprocess
import unittest
from unittest.mock import Mock, patch

from powersifu.brightness import BrightnessError, _set_gnome_brightness, set_brightness


class BrightnessTests(unittest.TestCase):
    @patch("powersifu.brightness._set_mutter_brightness")
    @patch("powersifu.brightness._set_gnome_slider_brightness")
    def test_gnome_updates_shell_slider_and_mutter(self, slider_setter, mutter_setter):
        _set_gnome_brightness(42)

        slider_setter.assert_called_once_with(42)
        mutter_setter.assert_called_once_with(42)

    @patch("powersifu.brightness._set_mutter_brightness")
    @patch(
        "powersifu.brightness._set_gnome_slider_brightness",
        side_effect=BrightnessError("slider unavailable"),
    )
    def test_gnome_falls_back_to_mutter(self, slider_setter, mutter_setter):
        _set_gnome_brightness(42)

        slider_setter.assert_called_once_with(42)
        mutter_setter.assert_called_once_with(42)

    def test_prefers_gnome_session_to_keep_desktop_slider_in_sync(self):
        runner = Mock()
        gnome_setter = Mock()

        set_brightness(42, runner=runner, gnome_setter=gnome_setter)

        gnome_setter.assert_called_once_with(42)
        runner.assert_not_called()

    def test_gnome_error_falls_back_to_absolute_percentage(self):
        runner = Mock()
        gnome_setter = Mock(side_effect=BrightnessError("GNOME unavailable"))

        set_brightness(42, runner=runner, gnome_setter=gnome_setter)

        runner.assert_called_once_with(
            ["brightnessctl", "--class=backlight", "--quiet", "set", "42%"],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )

    def test_rejects_out_of_range_values(self):
        with self.assertRaises(ValueError):
            set_brightness(0)
        with self.assertRaises(ValueError):
            set_brightness(101)

    def test_missing_helper_has_actionable_error(self):
        runner = Mock(side_effect=FileNotFoundError())
        with self.assertRaisesRegex(BrightnessError, "brightnessctl is not installed"):
            set_brightness(
                60,
                runner=runner,
                gnome_setter=Mock(side_effect=BrightnessError("GNOME unavailable")),
            )

    def test_command_error_is_reported(self):
        runner = Mock(
            side_effect=subprocess.CalledProcessError(
                1, ["brightnessctl"], stderr="Permission denied"
            )
        )
        with self.assertRaisesRegex(BrightnessError, "Permission denied"):
            set_brightness(
                60,
                runner=runner,
                gnome_setter=Mock(side_effect=BrightnessError("GNOME unavailable")),
            )

    def test_successful_gnome_session_does_not_try_denied_brightnessctl(self):
        runner = Mock(
            side_effect=subprocess.CalledProcessError(
                1, ["brightnessctl"], stderr="Permission denied"
            )
        )
        gnome_setter = Mock()

        set_brightness(85, runner=runner, gnome_setter=gnome_setter)

        gnome_setter.assert_called_once_with(85)
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
