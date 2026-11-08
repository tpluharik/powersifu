"""Safe same-user process termination for application rules."""

from __future__ import annotations

import os
import re
import signal
from pathlib import Path


PROCESS_NAME = re.compile(r"^[A-Za-z0-9_.+@-]{1,64}$")
COMMON_PROTECTED_NAMES = {
    "powersifu",
    "systemd",
    "init",
    "systemd-userwork",
    "systemd-executor",
    "systemd-logind",
    "dbus-daemon",
    "dbus-broker",
    "Xorg",
    "Xwayland",
    "wayland",
    "pipewire",
    "wireplumber",
    "pulseaudio",
}
DESKTOP_PROTECTED_NAMES = {
    "GNOME": {
        "gnome-shell",
        "gnome-session-b",
        "gnome-session-binary",
        "gnome-session",
        "gnome-settings-daemon",
        "gdm",
    },
    "KDE": {
        "plasmashell",
        "kwin_x11",
        "kwin_wayland",
        "ksmserver",
        "kded5",
        "kded6",
        "startplasma-x11",
        "startplasma-wayland",
    },
    "Unity": {
        "compiz",
        "unity-panel-service",
        "unity-settings-daemon",
    },
    "XFCE": {
        "xfce4-session",
        "xfwm4",
        "xfce4-panel",
        "xfsettingsd",
    },
    "LXQt": {
        "lxqt-session",
        "lxqt-panel",
        "lxqt-powermanagement",
        "openbox",
        "labwc",
    },
    "MATE": {
        "mate-session",
        "mate-panel",
        "mate-settings-daemon",
        "marco",
    },
    "Cinnamon": {
        "cinnamon",
        "cinnamon-session",
        "cinnamon-settings-daemon",
        "muffin",
    },
}
PROTECTED_NAMES = COMMON_PROTECTED_NAMES | {
    name
    for desktop_names in DESKTOP_PROTECTED_NAMES.values()
    for name in desktop_names
}
PROTECTED_NAMES_CASEFOLD = {name.casefold() for name in PROTECTED_NAMES}


def validate_process_name(name: str) -> bool:
    normalized = name.strip()
    return bool(PROCESS_NAME.fullmatch(normalized)) and normalized.casefold() not in PROTECTED_NAMES_CASEFOLD


def _identities(process_dir: Path) -> set[str]:
    identities: set[str] = set()
    try:
        identities.add((process_dir / "comm").read_text(encoding="utf-8").strip())
    except (FileNotFoundError, PermissionError, OSError):
        pass
    try:
        identities.add((process_dir / "exe").resolve().name)
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return {identity.casefold() for identity in identities if identity}


def _session_id(process_dir: Path) -> int | None:
    """Read the session ID from /proc/PID/stat without trusting process names."""

    try:
        stat_value = (process_dir / "stat").read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None
    closing_parenthesis = stat_value.rfind(")")
    if closing_parenthesis < 0:
        return None
    fields = stat_value[closing_parenthesis + 1 :].split()
    try:
        return int(fields[3])
    except (IndexError, ValueError):
        return None


def _matches_process(process_dir: Path, pid: int, wanted: str, own_uid: int) -> bool:
    try:
        if process_dir.stat().st_uid != own_uid:
            return False
    except (FileNotFoundError, PermissionError, OSError):
        return False
    if _session_id(process_dir) == pid:
        return False
    identities = _identities(process_dir)
    if identities & PROTECTED_NAMES_CASEFOLD:
        return False
    return wanted in identities


def matching_processes(name: str, proc_root: Path = Path("/proc")) -> list[int]:
    """Find exact process-name matches owned by the current user."""

    name = name.strip()
    if not validate_process_name(name):
        return []
    wanted = name.casefold()
    own_pid = os.getpid()
    own_uid = os.getuid()
    matches: list[int] = []
    for process_dir in proc_root.iterdir():
        if not process_dir.name.isdigit():
            continue
        pid = int(process_dir.name)
        if pid == own_pid:
            continue
        if _matches_process(process_dir, pid, wanted, own_uid):
            matches.append(pid)
    return sorted(matches)


def stop_application(name: str, proc_root: Path = Path("/proc")) -> list[int]:
    """Send SIGTERM to exact same-user matches and return affected PIDs."""

    normalized = name.strip()
    if not validate_process_name(normalized):
        return []
    wanted = normalized.casefold()
    own_uid = os.getuid()
    stopped: list[int] = []
    for pid in matching_processes(normalized, proc_root):
        pidfd: int | None = None
        try:
            if hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
                try:
                    pidfd = os.pidfd_open(pid)
                except OSError:
                    pidfd = None
            process_dir = proc_root / str(pid)
            if not _matches_process(process_dir, pid, wanted, own_uid):
                continue
            if pidfd is not None:
                signal.pidfd_send_signal(pidfd, signal.SIGTERM, None, 0)
            else:
                os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except (ProcessLookupError, PermissionError, OSError):
            continue
        finally:
            if pidfd is not None:
                os.close(pidfd)
    return stopped
