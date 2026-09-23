"""Persistent configuration for PowerSifu."""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


APP_ID = "io.github.tpluharik.PowerSifu"
PROFILE_NAMES = ("power-saver", "balanced", "performance")

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 2,
    "start_at_login": True,
    "automation": {
        "enabled": True,
        "ac_profile": "balanced",
        "battery_profile": "power-saver",
        "poll_seconds": 5,
    },
    "brightness": {
        "enabled": False,
        "profiles": {
            "power-saver": 40,
            "balanced": 70,
            "performance": 100,
        },
    },
    "application_rules": [],
    "schedules": [],
}


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def default_config_path() -> Path:
    return config_home() / "powersifu" / "config.json"


def _merge_defaults(value: Any, default: Any) -> Any:
    if isinstance(default, dict):
        incoming = value if isinstance(value, dict) else {}
        return {
            key: _merge_defaults(incoming.get(key), default_value)
            for key, default_value in default.items()
        }
    if isinstance(default, list):
        return value if isinstance(value, list) else deepcopy(default)
    return default if value is None or not isinstance(value, type(default)) else value


def sanitize_config(value: Any) -> dict[str, Any]:
    config = _merge_defaults(value, DEFAULT_CONFIG)
    config["version"] = DEFAULT_CONFIG["version"]
    automation = config["automation"]
    for key in ("ac_profile", "battery_profile"):
        if automation[key] not in PROFILE_NAMES:
            automation[key] = DEFAULT_CONFIG["automation"][key]
    automation["poll_seconds"] = min(max(int(automation["poll_seconds"]), 2), 60)

    brightness = config["brightness"]
    brightness["enabled"] = bool(brightness["enabled"])
    for profile in PROFILE_NAMES:
        default = DEFAULT_CONFIG["brightness"]["profiles"][profile]
        try:
            percent = int(brightness["profiles"][profile])
        except (TypeError, ValueError):
            percent = default
        brightness["profiles"][profile] = min(max(percent, 1), 100)

    rules = []
    for rule in value.get("application_rules", []) if isinstance(value, dict) else []:
        if not isinstance(rule, dict):
            continue
        name = str(rule.get("process", "")).strip()
        profile = str(rule.get("profile", ""))
        if name and profile in PROFILE_NAMES:
            rules.append(
                {
                    "enabled": bool(rule.get("enabled", True)),
                    "process": name,
                    "profile": profile,
                }
            )
    config["application_rules"] = rules

    schedules = []
    for schedule in value.get("schedules", []) if isinstance(value, dict) else []:
        if not isinstance(schedule, dict):
            continue
        time_value = str(schedule.get("time", ""))
        days = schedule.get("days", [])
        profile = str(schedule.get("profile", ""))
        if (
            len(time_value) == 5
            and time_value[2] == ":"
            and isinstance(days, list)
            and profile in PROFILE_NAMES
        ):
            try:
                hour, minute = (int(part) for part in time_value.split(":"))
            except ValueError:
                continue
            normalized_days: list[int] = []
            for day in days:
                try:
                    numeric_day = int(day)
                except (TypeError, ValueError):
                    continue
                if numeric_day in range(7):
                    normalized_days.append(numeric_day)
            if 0 <= hour <= 23 and 0 <= minute <= 59 and normalized_days:
                schedules.append(
                    {
                        "enabled": bool(schedule.get("enabled", True)),
                        "label": str(schedule.get("label", "")).strip(),
                        "time": time_value,
                        "days": sorted(set(normalized_days)),
                        "profile": profile,
                    }
                )
    config["schedules"] = schedules
    return config


class ConfigStore:
    """Read and atomically write the user's settings."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_path()
        self.data = deepcopy(DEFAULT_CONFIG)

    def load(self) -> dict[str, Any]:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            loaded = {}
        self.data = sanitize_config(loaded)
        return self.data

    def save(self) -> None:
        self.data = sanitize_config(self.data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="config-", suffix=".json", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()


def sync_autostart(enabled: bool) -> Path:
    """Write a per-user override for the package's XDG autostart entry."""

    destination = config_home() / "autostart" / f"{APP_ID}.desktop"
    destination.parent.mkdir(parents=True, exist_ok=True)
    hidden = "false" if enabled else "true"
    autostart_enabled = "true" if enabled else "false"
    content = f"""[Desktop Entry]
Type=Application
Name=PowerSifu
Comment=Automate Linux power profiles
Exec=powersifu --background
Icon=powersifu
Terminal=false
Hidden={hidden}
X-GNOME-Autostart-enabled={autostart_enabled}
OnlyShowIn=GNOME;KDE;Unity;XFCE;LXQt;MATE;Cinnamon;
"""
    destination.write_text(content, encoding="utf-8")
    return destination
