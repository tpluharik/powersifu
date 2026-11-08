#!/usr/bin/python3
"""Create the canonical manifest and Ed25519 signature for a release package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


OPENSSL = "/usr/bin/openssl"
DPKG_DEB = "/usr/bin/dpkg-deb"


def package_metadata(package: Path) -> dict[str, str]:
    result = subprocess.run(
        [DPKG_DEB, "--field", str(package), "Package", "Version", "Architecture"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    metadata: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()
    return metadata


def public_key_for(private_key: Path) -> bytes:
    return subprocess.run(
        [OPENSSL, "pkey", "-in", str(private_key), "-pubout"],
        check=True,
        capture_output=True,
        timeout=15,
    ).stdout.strip()


def main(arguments: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--public-key",
        type=Path,
        default=root / "data" / "update-signing-key.pem",
    )
    options = parser.parse_args(arguments)
    package = options.package.resolve()
    private_key = options.private_key.resolve()
    output_dir = (options.output_dir or package.parent).resolve()

    if not package.is_file() or not private_key.is_file() or not options.public_key.is_file():
        parser.error("package, private key, and public key must be regular files")
    private_mode = stat.S_IMODE(private_key.stat().st_mode)
    if private_mode & 0o077:
        parser.error("private key must not be accessible by group or other users")
    if public_key_for(private_key) != options.public_key.read_bytes().strip():
        parser.error("private key does not match PowerSifu's packaged public key")

    metadata = package_metadata(package)
    if metadata.get("Package") != "powersifu" or metadata.get("Architecture") != "all":
        parser.error("package must be the architecture-independent PowerSifu Debian package")
    version = metadata.get("Version", "")
    expected_name = f"powersifu_{version}_all.deb"
    if package.name != expected_name:
        parser.error(f"package filename must be {expected_name}")

    digest = hashlib.sha256()
    size = 0
    with package.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            size += len(chunk)
            digest.update(chunk)
    manifest = {
        "architecture": "all",
        "filename": package.name,
        "package": "powersifu",
        "schema": 1,
        "sha256": digest.hexdigest(),
        "size": size,
        "version": version,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"{package.name}.manifest.json"
    signature_path = output_dir / f"{manifest_path.name}.sig"
    temporary_manifest = output_dir / f".{manifest_path.name}.{os.getpid()}.tmp"
    temporary_signature = output_dir / f".{signature_path.name}.{os.getpid()}.tmp"
    try:
        temporary_manifest.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary_manifest.chmod(0o644)
        subprocess.run(
            [
                OPENSSL,
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(private_key),
                "-in",
                str(temporary_manifest),
                "-out",
                str(temporary_signature),
            ],
            check=True,
            timeout=15,
        )
        temporary_signature.chmod(0o644)
        os.replace(temporary_manifest, manifest_path)
        os.replace(temporary_signature, signature_path)
    finally:
        temporary_manifest.unlink(missing_ok=True)
        temporary_signature.unlink(missing_ok=True)
    print(manifest_path)
    print(signature_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Could not sign update: {error}", file=sys.stderr)
        raise SystemExit(1)
