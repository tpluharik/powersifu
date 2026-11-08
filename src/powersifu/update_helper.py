"""Minimal privileged installer for signed PowerSifu update bundles."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .updates import (
    MAX_MANIFEST_BYTES,
    MAX_PACKAGE_BYTES,
    MAX_SIGNATURE_BYTES,
    PUBLIC_KEY_PATH,
    UpdateInstallError,
    verify_debian_package,
    verify_package_digest,
    verify_signed_manifest,
)


STAGING_ROOT = Path("/var/cache/powersifu/updates")
DPKG_DEB_PATH = "/usr/bin/dpkg-deb"
DPKG_QUERY_PATH = "/usr/bin/dpkg-query"
DPKG_PATH = "/usr/bin/dpkg"
APT_GET_PATH = "/usr/bin/apt-get"


def _validate_root_owned_path(path: Path, expected_uid: int = 0) -> None:
    try:
        details = path.lstat()
    except OSError as error:
        raise UpdateInstallError(f"Trusted update path is unavailable: {path}: {error}") from error
    if details.st_uid != expected_uid or details.st_mode & 0o022:
        raise UpdateInstallError(f"Trusted update path has unsafe ownership or permissions: {path}")


def _prepare_staging_root(path: Path, expected_uid: int = 0) -> None:
    try:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    except OSError as error:
        raise UpdateInstallError(f"Could not prepare the protected update staging area: {error}") from error
    _validate_root_owned_path(path, expected_uid)
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise UpdateInstallError("The protected update staging area is not a directory")
    try:
        os.chmod(path, 0o700, follow_symlinks=False)
    except OSError as error:
        raise UpdateInstallError(f"Could not secure the protected update staging area: {error}") from error


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write while staging update")
        view = view[written:]


def _copy_without_following_links(
    source: Path,
    destination_dir: Path,
    *,
    suffix: str,
    maximum: int,
) -> Path:
    if not source.is_absolute():
        raise UpdateInstallError("Update-helper inputs must use absolute paths")
    if not hasattr(os, "O_NOFOLLOW"):
        raise UpdateInstallError("This system cannot securely open update inputs")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        source_descriptor = os.open(source, flags)
    except OSError as error:
        raise UpdateInstallError(f"Could not securely open update input {source.name}: {error}") from error
    destination_descriptor = -1
    destination: Path | None = None
    try:
        source_details = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_details.st_mode) or not 0 < source_details.st_size <= maximum:
            raise UpdateInstallError(f"Update input {source.name} is not a valid regular file")
        destination_descriptor, destination_name = tempfile.mkstemp(
            prefix="staged-", suffix=suffix, dir=destination_dir
        )
        destination = Path(destination_name)
        os.fchmod(destination_descriptor, 0o600)
        copied = 0
        while True:
            chunk = os.read(source_descriptor, 64 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if copied > maximum:
                raise UpdateInstallError(f"Update input {source.name} grew beyond its size limit")
            _write_all(destination_descriptor, chunk)
        if copied != source_details.st_size:
            raise UpdateInstallError(f"Update input {source.name} changed while it was staged")
        os.fsync(destination_descriptor)
        return destination
    except UpdateInstallError:
        if destination is not None:
            destination.unlink(missing_ok=True)
        raise
    except OSError as error:
        if destination is not None:
            destination.unlink(missing_ok=True)
        raise UpdateInstallError(f"Could not stage update input {source.name}: {error}") from error
    finally:
        os.close(source_descriptor)
        if destination_descriptor >= 0:
            os.close(destination_descriptor)


def _installed_version(runner: Any) -> str:
    try:
        result = runner(
            [DPKG_QUERY_PATH, "--show", "--showformat=${Version}", "powersifu"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise UpdateInstallError("Could not determine the installed PowerSifu version") from error
    version = result.stdout.strip()
    if not version:
        raise UpdateInstallError("The installed PowerSifu version is empty")
    return version


def _require_upgrade(new_version: str, installed_version: str, runner: Any) -> None:
    try:
        result = runner(
            [DPKG_PATH, "--compare-versions", new_version, "gt", installed_version],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UpdateInstallError("Could not compare PowerSifu package versions") from error
    if result.returncode != 0:
        raise UpdateInstallError(
            f"Refusing to install PowerSifu {new_version} over {installed_version}"
        )


def install_signed_update(
    package_source: Path,
    manifest_source: Path,
    signature_source: Path,
    *,
    runner: Any = subprocess.run,
    staging_root: Path = STAGING_ROOT,
    public_key_path: Path = PUBLIC_KEY_PATH,
    expected_uid: int = 0,
    effective_uid: int | None = None,
) -> None:
    """Stage, authenticate, inspect, and install one signed update as root."""

    current_uid = os.geteuid() if effective_uid is None else effective_uid
    if current_uid != 0:
        raise UpdateInstallError("The PowerSifu update helper must run as root")
    _prepare_staging_root(staging_root, expected_uid)
    _validate_root_owned_path(public_key_path, expected_uid)
    if not stat.S_ISREG(public_key_path.lstat().st_mode):
        raise UpdateInstallError("The packaged update public key is not a regular file")

    try:
        stage = Path(tempfile.mkdtemp(prefix="transaction-", dir=staging_root))
        stage.chmod(0o700)
    except OSError as error:
        raise UpdateInstallError(f"Could not create the protected update transaction: {error}") from error
    try:
        staged_manifest = _copy_without_following_links(
            manifest_source,
            stage,
            suffix=".manifest.json",
            maximum=MAX_MANIFEST_BYTES,
        )
        staged_signature = _copy_without_following_links(
            signature_source,
            stage,
            suffix=".manifest.json.sig",
            maximum=MAX_SIGNATURE_BYTES,
        )
        staged_package = _copy_without_following_links(
            package_source,
            stage,
            suffix=".deb",
            maximum=MAX_PACKAGE_BYTES,
        )
        manifest = verify_signed_manifest(
            staged_manifest,
            staged_signature,
            public_key_path=public_key_path,
            runner=runner,
        )
        verify_package_digest(staged_package, manifest)
        verify_debian_package(
            staged_package,
            manifest.version,
            manifest.architecture,
            runner=runner,
            dpkg_deb=DPKG_DEB_PATH,
        )
        installed_version = _installed_version(runner)
        _require_upgrade(manifest.version, installed_version, runner)
        try:
            runner(
                [APT_GET_PATH, "install", "--yes", str(staged_package)],
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except FileNotFoundError as error:
            raise UpdateInstallError("apt-get is unavailable; the update cannot be installed") from error
        except OSError as error:
            raise UpdateInstallError(f"apt-get could not install the update: {error}") from error
        except subprocess.TimeoutExpired as error:
            raise UpdateInstallError("The package installation timed out") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or "").strip() or (error.stdout or "").strip()
            raise UpdateInstallError(
                f"Package installation failed: {detail or 'unknown package-manager error'}"
            ) from error
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main(arguments: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if arguments is None else arguments)
    if len(values) != 3:
        print(
            "Usage: powersifu-update-helper PACKAGE MANIFEST SIGNATURE",
            file=sys.stderr,
        )
        return 2
    try:
        install_signed_update(*(Path(value) for value in values))
    except UpdateInstallError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
