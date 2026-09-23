"""Opt-in update checks against PowerSifu's official GitHub releases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


RELEASE_API_URL = "https://api.github.com/repos/tpluharik/powersifu/releases/latest"
RELEASES_URL = "https://github.com/tpluharik/powersifu/releases"
MAX_RESPONSE_BYTES = 256 * 1024


class UpdateCheckError(RuntimeError):
    """Raised when the latest release cannot be checked safely."""


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    release_url: str
    download_url: str | None

    @property
    def available(self) -> bool:
        return _version_tuple(self.latest_version) > _version_tuple(self.current_version)


def _version_tuple(value: str) -> tuple[int, ...]:
    normalized = value.strip().removeprefix("v")
    parts = normalized.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise UpdateCheckError(f"Unsupported release version: {value}")
    return tuple(int(part) for part in parts)


def _trusted_url(value: Any, allowed_hosts: set[str]) -> str:
    url = str(value or "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise UpdateCheckError("The release service returned an untrusted URL")
    return url


def check_for_update(current_version: str, opener: Any = urlopen) -> UpdateInfo:
    """Return the newest published release without downloading or installing it."""

    request = Request(
        RELEASE_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"PowerSifu/{current_version}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener(request, timeout=8) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise UpdateCheckError(f"Could not contact GitHub: {error}") from error
    if len(payload) > MAX_RESPONSE_BYTES:
        raise UpdateCheckError("The release response was unexpectedly large")

    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateCheckError("GitHub returned an invalid release response") from error
    if not isinstance(data, dict):
        raise UpdateCheckError("GitHub returned an invalid release response")

    latest_version = str(data.get("tag_name", "")).removeprefix("v")
    _version_tuple(current_version)
    _version_tuple(latest_version)
    release_url = _trusted_url(data.get("html_url"), {"github.com"})

    download_url: str | None = None
    assets = data.get("assets", [])
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict) or not str(asset.get("name", "")).endswith("_all.deb"):
                continue
            download_url = _trusted_url(
                asset.get("browser_download_url"),
                {"github.com", "objects.githubusercontent.com"},
            )
            break

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        release_url=release_url,
        download_url=download_url,
    )
