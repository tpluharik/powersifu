"""Safe same-user process termination for application rules."""

from __future__ import annotations

import os
import re
import signal
from pathlib import Path


PROCESS_NAME = re.compile(r"^[A-Za-z0-9_.+@-]{1,64}$")
PROTECTED_NAMES = {
    "powersifu",
    "systemd",
    "init",
    "gnome-shell",
    "gnome-session-b",
    "gnome-session-binary",
    "gnome-session",
    "gdm",
    "Xorg",
    "Xwayland",
    "dbus-daemon",
    "dbus-broker",
    "pipewire",
    "wireplumber",
    "pulseaudio",
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
        try:
            if process_dir.stat().st_uid != own_uid:
                continue
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if wanted in _identities(process_dir):
            matches.append(pid)
    return sorted(matches)


def stop_application(name: str) -> list[int]:
    """Send SIGTERM to exact same-user matches and return affected PIDs."""

    stopped: list[int] = []
    for pid in matching_processes(name):
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except (ProcessLookupError, PermissionError):
            continue
    return stopped
