"""Permission-safe screen-brightness control for Linux desktops."""

from __future__ import annotations

import subprocess
from collections.abc import Callable


class BrightnessError(RuntimeError):
    """Raised when the configured display brightness cannot be applied."""


Runner = Callable[..., subprocess.CompletedProcess[str]]
BrightnessSetter = Callable[[int], None]


def _set_gnome_brightness(percent: int) -> None:
    """Set the active internal panel through Mutter's session D-Bus API."""

    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, GLib
    except (ImportError, ValueError) as error:
        raise BrightnessError("GNOME display service bindings are unavailable") from error

    destination = "org.gnome.Mutter.DisplayConfig"
    object_path = "/org/gnome/Mutter/DisplayConfig"
    interface = "org.gnome.Mutter.DisplayConfig"
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        response = connection.call_sync(
            destination,
            object_path,
            "org.freedesktop.DBus.Properties",
            "Get",
            GLib.Variant("(ss)", (interface, "Backlight")),
            GLib.VariantType.new("(v)"),
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )
        serial, devices = response.unpack()[0]
        device = next(
            (
                candidate
                for candidate in devices
                if candidate.get("active") and candidate.get("connector")
            ),
            None,
        )
        if device is None:
            raise BrightnessError("GNOME did not report an active built-in display")

        minimum = int(device["min"])
        maximum = int(device["max"])
        if maximum <= 0 or minimum < 0 or minimum > maximum:
            raise BrightnessError("GNOME reported an invalid backlight range")
        value = max(minimum, min(maximum, round(maximum * percent / 100)))
        connection.call_sync(
            destination,
            object_path,
            interface,
            "SetBacklight",
            GLib.Variant("(usi)", (int(serial), str(device["connector"]), value)),
            None,
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )
    except BrightnessError:
        raise
    except (GLib.Error, KeyError, TypeError, ValueError) as error:
        raise BrightnessError(f"GNOME display service failed: {error}") from error


def set_brightness(
    percent: int,
    runner: Runner = subprocess.run,
    gnome_setter: BrightnessSetter | None = None,
) -> None:
    """Set the primary backlight to an absolute percentage."""

    if isinstance(percent, bool) or not isinstance(percent, int) or not 1 <= percent <= 100:
        raise ValueError("Brightness must be an integer from 1 to 100")

    try:
        runner(
            ["brightnessctl", "--class=backlight", "--quiet", "set", f"{percent}%"],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
        return
    except FileNotFoundError as error:
        command_error = "brightnessctl is not installed"
    except subprocess.TimeoutExpired as error:
        command_error = "brightnessctl did not respond"
    except subprocess.CalledProcessError as error:
        command_error = (
            (error.stderr or "").strip()
            or (error.stdout or "").strip()
            or "brightnessctl failed"
        )

    try:
        (gnome_setter or _set_gnome_brightness)(percent)
    except BrightnessError as desktop_error:
        raise BrightnessError(
            f"{command_error}. GNOME fallback also failed: {desktop_error}"
        ) from desktop_error
