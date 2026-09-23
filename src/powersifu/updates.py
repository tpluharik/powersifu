"""Authenticated in-app updates from PowerSifu's official GitHub releases."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


RELEASE_API_URL = "https://api.github.com/repos/tpluharik/powersifu/releases/latest"
RELEASES_URL = "https://github.com/tpluharik/powersifu/releases"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


class UpdateCheckError(RuntimeError):
    """Raised when the latest release cannot be checked safely."""


class UpdateInstallError(RuntimeError):
    """Raised when an update cannot be downloaded, verified, or installed."""


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    release_url: str
    download_url: str | None
    download_sha256: str | None = None
    download_size: int | None = None

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
    download_sha256: str | None = None
    download_size: int | None = None
    assets = data.get("assets", [])
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict) or not str(asset.get("name", "")).endswith("_all.deb"):
                continue
            download_url = _trusted_url(
                asset.get("browser_download_url"),
                {"github.com", "objects.githubusercontent.com"},
            )
            digest = str(asset.get("digest", ""))
            if digest.startswith("sha256:"):
                candidate = digest.removeprefix("sha256:").lower()
                if len(candidate) == 64 and all(
                    character in "0123456789abcdef" for character in candidate
                ):
                    download_sha256 = candidate
            try:
                size = int(asset.get("size"))
            except (TypeError, ValueError):
                size = 0
            if 0 < size <= MAX_PACKAGE_BYTES:
                download_size = size
            break

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        release_url=release_url,
        download_url=download_url,
        download_sha256=download_sha256,
        download_size=download_size,
    )


def _default_cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "powersifu" / "updates"


def verify_update_package(
    package_path: Path,
    info: UpdateInfo,
    runner: Any = subprocess.run,
) -> None:
    """Verify the identity of a downloaded Debian package before elevation."""

    if not package_path.is_file() or package_path.stat().st_size <= 0:
        raise UpdateInstallError("The downloaded package is empty or missing")
    if package_path.stat().st_size > MAX_PACKAGE_BYTES:
        raise UpdateInstallError("The downloaded package is unexpectedly large")

    try:
        result = runner(
            [
                "dpkg-deb",
                "--field",
                str(package_path),
                "Package",
                "Version",
                "Architecture",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError as error:
        raise UpdateInstallError("dpkg-deb is unavailable; the update cannot be verified") from error
    except subprocess.TimeoutExpired as error:
        raise UpdateInstallError("Package verification timed out") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip() or "invalid Debian package"
        raise UpdateInstallError(f"Package verification failed: {detail}") from error

    metadata: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()
    expected = {
        "Package": "powersifu",
        "Version": info.latest_version,
        "Architecture": "all",
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            raise UpdateInstallError(
                f"Package verification failed: expected {field} {value}"
            )


def download_update(
    info: UpdateInfo,
    destination_dir: Path | None = None,
    opener: Any = urlopen,
    package_runner: Any = subprocess.run,
) -> Path:
    """Download and verify an official release package into the user cache."""

    if not info.available or info.download_url is None:
        raise UpdateInstallError("This release does not provide an installable update")
    if info.download_sha256 is None or info.download_size is None:
        raise UpdateInstallError("The release package has no trusted SHA-256 digest or size")
    expected_name = f"powersifu_{info.latest_version}_all.deb"
    try:
        download_url = _trusted_url(info.download_url, DOWNLOAD_HOSTS)
    except UpdateCheckError as error:
        raise UpdateInstallError(str(error)) from error
    if Path(urlparse(download_url).path).name != expected_name:
        raise UpdateInstallError("The release package has an unexpected filename")

    target_dir = destination_dir or _default_cache_dir()
    temporary_path: Path | None = None
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_dir.chmod(0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="download-", suffix=".deb", dir=target_dir
        )
        temporary_path = Path(temporary_name)
        request = Request(
            download_url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": f"PowerSifu/{info.current_version}",
            },
        )
        with os.fdopen(descriptor, "wb") as stream:
            with opener(request, timeout=30) as response:
                final_url = getattr(response, "geturl", lambda: download_url)()
                _trusted_url(final_url, DOWNLOAD_HOSTS)
                header_value = getattr(response, "headers", {}).get("Content-Length")
                if header_value is not None and int(header_value) != info.download_size:
                    raise UpdateInstallError("The release package size does not match GitHub")

                total = 0
                digest = hashlib.sha256()
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_PACKAGE_BYTES:
                        raise UpdateInstallError("The release package is unexpectedly large")
                    digest.update(chunk)
                    stream.write(chunk)
                if total != info.download_size:
                    raise UpdateInstallError("The release package size does not match GitHub")
                if digest.hexdigest() != info.download_sha256:
                    raise UpdateInstallError("The release package SHA-256 digest does not match")

        destination = target_dir / expected_name
        verify_update_package(temporary_path, info, runner=package_runner)
        os.replace(temporary_path, destination)
        temporary_path = None
        return destination
    except UpdateInstallError:
        raise
    except UpdateCheckError as error:
        raise UpdateInstallError(str(error)) from error
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        raise UpdateInstallError(f"Could not download the update: {error}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def install_update(package_path: Path, runner: Any = subprocess.run) -> None:
    """Install a verified local package through the system authentication dialog."""

    try:
        runner(
            ["pkexec", "apt-get", "install", "--yes", str(package_path.resolve())],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as error:
        raise UpdateInstallError(
            "The system authentication helper (pkexec) is not installed"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise UpdateInstallError("The package installation timed out") from error
    except subprocess.CalledProcessError as error:
        if error.returncode in (126, 127):
            raise UpdateInstallError("Update authentication was cancelled or unavailable") from error
        detail = (error.stderr or "").strip() or (error.stdout or "").strip()
        raise UpdateInstallError(
            f"Package installation failed: {detail or 'unknown package manager error'}"
        ) from error
