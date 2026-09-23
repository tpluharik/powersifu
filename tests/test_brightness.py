import subprocess
import unittest
from unittest.mock import Mock

from powersifu.brightness import BrightnessError, set_brightness


class BrightnessTests(unittest.TestCase):
    def test_sets_absolute_percentage(self):
        runner = Mock()
        set_brightness(42, runner=runner)
        runner.assert_called_once_with(
            ["brightnessctl", "--quiet", "set", "42%"],
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
            set_brightness(60, runner=runner)

    def test_command_error_is_reported(self):
        runner = Mock(
            side_effect=subprocess.CalledProcessError(
                1, ["brightnessctl"], stderr="Permission denied"
            )
        )
        with self.assertRaisesRegex(BrightnessError, "Permission denied"):
            set_brightness(60, runner=runner)


if __name__ == "__main__":
    unittest.main()
