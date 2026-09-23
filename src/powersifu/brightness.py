"""Permission-safe screen-brightness control for Linux desktops."""

from __future__ import annotations

import gettext
import subprocess
from collections.abc import Callable


class BrightnessError(RuntimeError):
    """Raised when the configured display brightness cannot be applied."""


Runner = Callable[..., subprocess.CompletedProcess[str]]
BrightnessSetter = Callable[[int], None]


def _set_gnome_slider_brightness(percent: int) -> None:
    """Set GNOME Shell's global slider so its UI and the backlight stay aligned."""

    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi, GLib
    except (ImportError, ValueError) as error:
        raise BrightnessError("GNOME slider bindings are unavailable") from error

    slider_name = gettext.dgettext("gnome-shell", "Brightness")
    try:
        desktop = Atspi.get_desktop(0)
        shell = None
        for index in range(desktop.get_child_count()):
            try:
                candidate = desktop.get_child_at_index(index)
                if candidate is not None and candidate.get_name() == "gnome-shell":
                    shell = candidate
                    break
            except GLib.Error:
                continue
        if shell is None:
            raise BrightnessError("GNOME Shell is not present on the accessibility bus")

        stack = [shell]
        visited = 0
        while stack and visited < 10_000:
            accessible = stack.pop()
            visited += 1
            try:
                if (
                    accessible.get_role() == Atspi.Role.SLIDER
                    and accessible.get_name() == slider_name
                ):
                    value = accessible.get_value_iface()
                    if value is None or not value.set_current_value(percent / 100):
                        raise BrightnessError("GNOME rejected the brightness slider value")
                    return
                for index in range(accessible.get_child_count() - 1, -1, -1):
                    child = accessible.get_child_at_index(index)
                    if child is not None:
                        stack.append(child)
            except GLib.Error:
                continue
    except BrightnessError:
        raise
    except (GLib.Error, AttributeError, RuntimeError, TypeError) as error:
        raise BrightnessError(f"GNOME slider service failed: {error}") from error

    raise BrightnessError("GNOME's global brightness slider was not found")


def _set_mutter_brightness(percent: int) -> None:
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
        value = minimum + round((maximum - minimum) * percent / 100)
        value = max(minimum, min(maximum, value))
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


def _set_gnome_brightness(percent: int) -> None:
    """Update GNOME Shell's global slider and Mutter's physical backlight."""

    slider_error: str | None = None
    try:
        _set_gnome_slider_brightness(percent)
    except BrightnessError as error:
        slider_error = str(error)

    try:
        _set_mutter_brightness(percent)
    except BrightnessError as error:
        detail = (
            f"GNOME slider failed: {slider_error}. "
            if slider_error is not None
            else "GNOME slider changed, but "
        )
        raise BrightnessError(
            f"{detail}Mutter backlight failed: {error}"
        ) from error


def set_brightness(
    percent: int,
    runner: Runner = subprocess.run,
    gnome_setter: BrightnessSetter | None = None,
) -> None:
    """Set the primary backlight to an absolute percentage."""

    if isinstance(percent, bool) or not isinstance(percent, int) or not 1 <= percent <= 100:
        raise ValueError("Brightness must be an integer from 1 to 100")

    # GNOME Shell keeps its own brightness model for the Quick Settings slider.
    # Updating that session model first keeps the slider and hardware in sync.
    # Other desktops fall back to brightnessctl below.
    try:
        (gnome_setter or _set_gnome_brightness)(percent)
        return
    except BrightnessError as error:
        desktop_error = str(error)

    try:
        runner(
            ["brightnessctl", "--class=backlight", "--quiet", "set", f"{percent}%"],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except FileNotFoundError as error:
        command_error = "brightnessctl is not installed"
        command_exception = error
    except subprocess.TimeoutExpired as error:
        command_error = "brightnessctl did not respond"
        command_exception = error
    except subprocess.CalledProcessError as error:
        command_error = (
            (error.stderr or "").strip()
            or (error.stdout or "").strip()
            or "brightnessctl failed"
        )
        command_exception = error
    else:
        return

    raise BrightnessError(
        f"GNOME display service failed: {desktop_error}. "
        f"brightnessctl also failed: {command_error}"
    ) from command_exception
