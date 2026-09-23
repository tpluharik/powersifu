"""Screen-brightness control through the desktop's brightnessctl helper."""

from __future__ import annotations

import subprocess
from collections.abc import Callable


class BrightnessError(RuntimeError):
    """Raised when the configured display brightness cannot be applied."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def set_brightness(percent: int, runner: Runner = subprocess.run) -> None:
    """Set the primary backlight to an absolute percentage."""

    if isinstance(percent, bool) or not isinstance(percent, int) or not 1 <= percent <= 100:
        raise ValueError("Brightness must be an integer from 1 to 100")

    try:
        runner(
            ["brightnessctl", "--quiet", "set", f"{percent}%"],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except FileNotFoundError as error:
        raise BrightnessError(
            "brightnessctl is not installed; install it or disable brightness automation"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise BrightnessError("brightnessctl did not respond") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or error.stdout.strip() or "brightness change failed"
        raise BrightnessError(message) from error
