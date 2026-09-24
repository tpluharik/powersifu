"""Interfaces to power-profiles-daemon and Linux power supplies."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import PROFILE_NAMES


POWER_PROFILES_NAME = "org.freedesktop.UPower.PowerProfiles"
POWER_PROFILES_PATH = "/org/freedesktop/UPower/PowerProfiles"
POWER_PROFILES_INTERFACE = "org.freedesktop.UPower.PowerProfiles"
DBUS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
DBUS_TIMEOUT_MS = 3_000


class PowerProfileError(RuntimeError):
    pass


def _dbus_modules():
    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
    except (ImportError, ValueError) as error:
        raise PowerProfileError("The Gio D-Bus integration is not installed") from error
    return Gio, GLib


def _get_active_profile_dbus() -> str:
    Gio, GLib = _dbus_modules()
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        response = connection.call_sync(
            POWER_PROFILES_NAME,
            POWER_PROFILES_PATH,
            DBUS_PROPERTIES_INTERFACE,
            "Get",
            GLib.Variant(
                "(ss)",
                (POWER_PROFILES_INTERFACE, "ActiveProfile"),
            ),
            GLib.VariantType.new("(v)"),
            Gio.DBusCallFlags.NONE,
            DBUS_TIMEOUT_MS,
            None,
        )
    except GLib.Error as error:
        message = f"Could not read the active power profile: {error.message}"
        raise PowerProfileError(message) from error
    return str(response.unpack()[0])


def _set_profile_dbus(profile: str) -> None:
    Gio, GLib = _dbus_modules()
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        connection.call_sync(
            POWER_PROFILES_NAME,
            POWER_PROFILES_PATH,
            DBUS_PROPERTIES_INTERFACE,
            "Set",
            GLib.Variant(
                "(ssv)",
                (
                    POWER_PROFILES_INTERFACE,
                    "ActiveProfile",
                    GLib.Variant("s", profile),
                ),
            ),
            None,
            Gio.DBusCallFlags.NONE,
            DBUS_TIMEOUT_MS,
            None,
        )
    except GLib.Error as error:
        raise PowerProfileError(f"Could not change the power profile: {error.message}") from error


def get_active_profile(reader: Callable[[], str] | None = None) -> str:
    """Read the daemon's active profile without spawning powerprofilesctl."""

    profile = (reader or _get_active_profile_dbus)()
    if profile not in PROFILE_NAMES:
        raise PowerProfileError(f"Unknown active profile: {profile}")
    return profile


def set_profile(profile: str, writer: Callable[[str], None] | None = None) -> None:
    """Set a supported profile directly through the daemon's system D-Bus API."""

    if profile not in PROFILE_NAMES:
        raise ValueError(f"Unsupported power profile: {profile}")
    (writer or _set_profile_dbus)(profile)


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
