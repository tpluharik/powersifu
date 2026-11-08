"""Signed in-app updates from PowerSifu's official GitHub releases."""

from __future__ import annotations

import hashlib
import json
import os
import stat
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
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SIGNATURE_BYTES = 4 * 1024
PUBLIC_KEY_PATH = Path("/usr/share/powersifu/update-signing-key.pem")
UPDATE_HELPER_PATH = Path("/usr/libexec/powersifu/powersifu-update-helper")
UPDATE_HELPER_INTERPRETER = "/usr/bin/python3"
OPENSSL_PATH = "/usr/bin/openssl"
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
    manifest_url: str | None = None
    signature_url: str | None = None
    download_sha256: str | None = None
    download_size: int | None = None
    manifest_size: int | None = None
    signature_size: int | None = None

    @property
    def available(self) -> bool:
        return _version_tuple(self.latest_version) > _version_tuple(self.current_version)

    @property
    def installable(self) -> bool:
        return bool(self.download_url and self.manifest_url and self.signature_url)


@dataclass(frozen=True)
class SignedManifest:
    version: str
    filename: str
    size: int
    sha256: str
    package: str = "powersifu"
    architecture: str = "all"
    schema: int = 1


@dataclass(frozen=True)
class DownloadedUpdate:
    package_path: Path
    manifest_path: Path
    signature_path: Path

    def cleanup(self) -> None:
        for path in (self.package_path, self.manifest_path, self.signature_path):
            path.unlink(missing_ok=True)


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


def _asset_metadata(
    assets: Any,
    expected_name: str,
    max_size: int,
) -> tuple[str | None, int | None, str | None]:
    if not isinstance(assets, list):
        return None, None, None
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") != expected_name:
            continue
        url = _trusted_url(asset.get("browser_download_url"), DOWNLOAD_HOSTS)
        try:
            size_value = int(asset.get("size"))
        except (TypeError, ValueError):
            size_value = 0
        size = size_value if 0 < size_value <= max_size else None
        digest_value = str(asset.get("digest", ""))
        digest: str | None = None
        if digest_value.startswith("sha256:"):
            candidate = digest_value.removeprefix("sha256:").lower()
            if len(candidate) == 64 and all(
                character in "0123456789abcdef" for character in candidate
            ):
                digest = candidate
        return url, size, digest
    return None, None, None


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
    package_name = f"powersifu_{latest_version}_all.deb"
    manifest_name = f"{package_name}.manifest.json"
    signature_name = f"{manifest_name}.sig"
    assets = data.get("assets", [])
    download_url, download_size, download_sha256 = _asset_metadata(
        assets, package_name, MAX_PACKAGE_BYTES
    )
    manifest_url, manifest_size, _manifest_digest = _asset_metadata(
        assets, manifest_name, MAX_MANIFEST_BYTES
    )
    signature_url, signature_size, _signature_digest = _asset_metadata(
        assets, signature_name, MAX_SIGNATURE_BYTES
    )

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        release_url=release_url,
        download_url=download_url,
        manifest_url=manifest_url,
        signature_url=signature_url,
        download_sha256=download_sha256,
        download_size=download_size,
        manifest_size=manifest_size,
        signature_size=signature_size,
    )


def _default_cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "powersifu" / "updates"


def _ensure_regular_file(path: Path, maximum: int, label: str) -> int:
    try:
        details = path.lstat()
    except OSError as error:
        raise UpdateInstallError(f"The {label} is missing: {error}") from error
    if not stat.S_ISREG(details.st_mode) or details.st_size <= 0:
        raise UpdateInstallError(f"The {label} is not a non-empty regular file")
    if details.st_size > maximum:
        raise UpdateInstallError(f"The {label} is unexpectedly large")
    return details.st_size


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate manifest field: {key}")
        value[key] = item
    return value


def parse_signed_manifest(payload: bytes) -> SignedManifest:
    try:
        data = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise UpdateInstallError("The signed update manifest is invalid") from error
    expected_fields = {
        "schema",
        "package",
        "version",
        "architecture",
        "filename",
        "size",
        "sha256",
    }
    if not isinstance(data, dict) or set(data) != expected_fields:
        raise UpdateInstallError("The signed update manifest has unexpected fields")
    if data.get("schema") != 1:
        raise UpdateInstallError("The signed update manifest uses an unsupported schema")
    if data.get("package") != "powersifu" or data.get("architecture") != "all":
        raise UpdateInstallError("The signed update manifest identifies the wrong package")

    version = str(data.get("version", ""))
    try:
        _version_tuple(version)
    except UpdateCheckError as error:
        raise UpdateInstallError(str(error)) from error
    filename = str(data.get("filename", ""))
    if filename != f"powersifu_{version}_all.deb":
        raise UpdateInstallError("The signed update manifest has an unexpected filename")
    size = data.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_PACKAGE_BYTES:
        raise UpdateInstallError("The signed update manifest has an invalid package size")
    sha256 = str(data.get("sha256", "")).lower()
    if len(sha256) != 64 or any(
        character not in "0123456789abcdef" for character in sha256
    ):
        raise UpdateInstallError("The signed update manifest has an invalid SHA-256 digest")
    return SignedManifest(version=version, filename=filename, size=size, sha256=sha256)


def verify_signed_manifest(
    manifest_path: Path,
    signature_path: Path,
    public_key_path: Path = PUBLIC_KEY_PATH,
    runner: Any = subprocess.run,
) -> SignedManifest:
    """Authenticate a release manifest against the packaged Ed25519 public key."""

    _ensure_regular_file(manifest_path, MAX_MANIFEST_BYTES, "update manifest")
    _ensure_regular_file(signature_path, MAX_SIGNATURE_BYTES, "update signature")
    _ensure_regular_file(public_key_path, MAX_MANIFEST_BYTES, "update public key")
    try:
        runner(
            [
                OPENSSL_PATH,
                "pkeyutl",
                "-verify",
                "-rawin",
                "-pubin",
                "-inkey",
                str(public_key_path),
                "-sigfile",
                str(signature_path),
                "-in",
                str(manifest_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError as error:
        raise UpdateInstallError("OpenSSL is unavailable; the update cannot be authenticated") from error
    except OSError as error:
        raise UpdateInstallError(f"OpenSSL could not authenticate the update: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise UpdateInstallError("Update signature verification timed out") from error
    except subprocess.CalledProcessError as error:
        raise UpdateInstallError("The update manifest signature is invalid") from error
    try:
        payload = manifest_path.read_bytes()
    except OSError as error:
        raise UpdateInstallError(f"Could not read the signed update manifest: {error}") from error
    return parse_signed_manifest(payload)


def verify_package_digest(package_path: Path, manifest: SignedManifest) -> None:
    actual_size = _ensure_regular_file(package_path, MAX_PACKAGE_BYTES, "update package")
    if actual_size != manifest.size:
        raise UpdateInstallError("The update package size does not match its signed manifest")
    digest = hashlib.sha256()
    try:
        with package_path.open("rb") as stream:
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise UpdateInstallError(f"Could not read the update package: {error}") from error
    if digest.hexdigest() != manifest.sha256:
        raise UpdateInstallError("The update package SHA-256 does not match its signed manifest")


def verify_debian_package(
    package_path: Path,
    expected_version: str,
    expected_architecture: str = "all",
    runner: Any = subprocess.run,
    dpkg_deb: str = "dpkg-deb",
) -> None:
    """Verify Debian package identity and version without installing it."""

    _ensure_regular_file(package_path, MAX_PACKAGE_BYTES, "update package")
    try:
        result = runner(
            [
                dpkg_deb,
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
    except OSError as error:
        raise UpdateInstallError(f"dpkg-deb could not verify the update: {error}") from error
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
        "Version": expected_version,
        "Architecture": expected_architecture,
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            raise UpdateInstallError(
                f"Package verification failed: expected {field} {value}"
            )


def verify_update_package(
    package_path: Path,
    info: UpdateInfo,
    runner: Any = subprocess.run,
) -> None:
    """Compatibility wrapper for callers that already hold release information."""

    verify_debian_package(package_path, info.latest_version, runner=runner)


def _download_to_temporary(
    url: str,
    target_dir: Path,
    *,
    prefix: str,
    suffix: str,
    maximum: int,
    expected_size: int | None,
    current_version: str,
    opener: Any,
) -> Path:
    try:
        trusted_url = _trusted_url(url, DOWNLOAD_HOSTS)
    except UpdateCheckError as error:
        raise UpdateInstallError(str(error)) from error
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=target_dir)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        request = Request(
            trusted_url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": f"PowerSifu/{current_version}",
            },
        )
        with os.fdopen(descriptor, "wb") as stream:
            with opener(request, timeout=30) as response:
                final_url = getattr(response, "geturl", lambda: trusted_url)()
                _trusted_url(final_url, DOWNLOAD_HOSTS)
                header_value = getattr(response, "headers", {}).get("Content-Length")
                if header_value is not None:
                    header_size = int(header_value)
                    if header_size <= 0 or header_size > maximum:
                        raise UpdateInstallError("A release asset has an invalid size")
                    if expected_size is not None and header_size != expected_size:
                        raise UpdateInstallError("A release asset size does not match GitHub")
                total = 0
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > maximum:
                        raise UpdateInstallError("A release asset is unexpectedly large")
                    stream.write(chunk)
                if total <= 0:
                    raise UpdateInstallError("A release asset is empty")
                if expected_size is not None and total != expected_size:
                    raise UpdateInstallError("A release asset size does not match GitHub")
                stream.flush()
                os.fsync(stream.fileno())
        return temporary_path
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def download_update(
    info: UpdateInfo,
    destination_dir: Path | None = None,
    opener: Any = urlopen,
    package_runner: Any = subprocess.run,
    signature_runner: Any = subprocess.run,
    public_key_path: Path = PUBLIC_KEY_PATH,
) -> DownloadedUpdate:
    """Download and authenticate a signed PowerSifu release bundle."""

    if not info.available or not info.installable:
        raise UpdateInstallError("This release does not provide a signed installable update")
    package_name = f"powersifu_{info.latest_version}_all.deb"
    manifest_name = f"{package_name}.manifest.json"
    signature_name = f"{manifest_name}.sig"
    urls = {
        package_name: info.download_url,
        manifest_name: info.manifest_url,
        signature_name: info.signature_url,
    }
    for expected_name, url in urls.items():
        if url is None or Path(urlparse(url).path).name != expected_name:
            raise UpdateInstallError("The release contains an unexpectedly named update asset")

    target_dir = destination_dir or _default_cache_dir()
    temporary_paths: list[Path] = []
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_dir.chmod(0o700)
        manifest_path = _download_to_temporary(
            info.manifest_url,
            target_dir,
            prefix="manifest-",
            suffix=".json",
            maximum=MAX_MANIFEST_BYTES,
            expected_size=info.manifest_size,
            current_version=info.current_version,
            opener=opener,
        )
        temporary_paths.append(manifest_path)
        signature_path = _download_to_temporary(
            info.signature_url,
            target_dir,
            prefix="signature-",
            suffix=".sig",
            maximum=MAX_SIGNATURE_BYTES,
            expected_size=info.signature_size,
            current_version=info.current_version,
            opener=opener,
        )
        temporary_paths.append(signature_path)
        manifest = verify_signed_manifest(
            manifest_path,
            signature_path,
            public_key_path=public_key_path,
            runner=signature_runner,
        )
        if manifest.version != info.latest_version or manifest.filename != package_name:
            raise UpdateInstallError("The signed update manifest does not match the release")
        if info.download_size is not None and info.download_size != manifest.size:
            raise UpdateInstallError("GitHub and the signed manifest disagree about package size")
        if info.download_sha256 is not None and info.download_sha256 != manifest.sha256:
            raise UpdateInstallError("GitHub and the signed manifest disagree about package SHA-256")

        package_path = _download_to_temporary(
            info.download_url,
            target_dir,
            prefix="package-",
            suffix=".deb",
            maximum=MAX_PACKAGE_BYTES,
            expected_size=manifest.size,
            current_version=info.current_version,
            opener=opener,
        )
        temporary_paths.append(package_path)
        verify_package_digest(package_path, manifest)
        verify_debian_package(package_path, manifest.version, runner=package_runner)

        destinations = DownloadedUpdate(
            package_path=target_dir / package_name,
            manifest_path=target_dir / manifest_name,
            signature_path=target_dir / signature_name,
        )
        for source, destination in (
            (package_path, destinations.package_path),
            (manifest_path, destinations.manifest_path),
            (signature_path, destinations.signature_path),
        ):
            os.replace(source, destination)
            temporary_paths.remove(source)
        return destinations
    except UpdateInstallError:
        raise
    except UpdateCheckError as error:
        raise UpdateInstallError(str(error)) from error
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        raise UpdateInstallError(f"Could not download the update: {error}") from error
    finally:
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)


def install_update(update: DownloadedUpdate, runner: Any = subprocess.run) -> None:
    """Ask the fixed privileged helper to re-verify and install an update bundle."""

    arguments = [
        "pkexec",
        UPDATE_HELPER_INTERPRETER,
        str(UPDATE_HELPER_PATH),
        os.path.abspath(update.package_path),
        os.path.abspath(update.manifest_path),
        os.path.abspath(update.signature_path),
    ]
    try:
        runner(
            arguments,
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
            f"Package installation failed: {detail or 'unknown update-helper error'}"
        ) from error
