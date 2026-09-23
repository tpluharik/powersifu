"""Interfaces to power-profiles-daemon and Linux power supplies."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import PROFILE_NAMES


class PowerProfileError(RuntimeError):
    pass


def _run(*arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["powerprofilesctl", *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except FileNotFoundError as error:
        raise PowerProfileError("powerprofilesctl is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise PowerProfileError("powerprofilesctl did not respond") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or error.stdout.strip() or "profile change failed"
        raise PowerProfileError(message) from error
    return completed.stdout.strip()


def get_active_profile() -> str:
    profile = _run("get")
    if profile not in PROFILE_NAMES:
        raise PowerProfileError(f"Unknown active profile: {profile}")
    return profile


def set_profile(profile: str) -> None:
    if profile not in PROFILE_NAMES:
        raise ValueError(f"Unsupported power profile: {profile}")
    _run("set", profile)


def on_ac_power(root: Path = Path("/sys/class/power_supply")) -> bool:
    """Return True when an online mains-class supply is present."""

    if not root.exists():
        return False
    for supply in root.iterdir():
        try:
            supply_type = (supply / "type").read_text(encoding="utf-8").strip()
            online = (supply / "online").read_text(encoding="utf-8").strip()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if supply_type in {"Mains", "USB", "USB_C", "USB_PD"} and online == "1":
            return True
    return False
