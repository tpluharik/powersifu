import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from powersifu.update_helper import (
    APT_GET_PATH,
    DPKG_DEB_PATH,
    DPKG_PATH,
    DPKG_QUERY_PATH,
    install_signed_update,
)
from powersifu.updates import OPENSSL_PATH, UpdateInstallError


class HelperRunner:
    def __init__(self, installed_version="0.3.6", package_version="0.4.0"):
        self.installed_version = installed_version
        self.package_version = package_version
        self.calls = []
        self.installed_payload = None

    def __call__(self, arguments, **options):
        self.calls.append(arguments)
        if arguments[0] == OPENSSL_PATH:
            return subprocess.run(arguments, **options)
        if arguments[0] == DPKG_DEB_PATH:
            return subprocess.CompletedProcess(
                arguments,
                0,
                f"Package: powersifu\nVersion: {self.package_version}\nArchitecture: all\n",
                "",
            )
        if arguments[0] == DPKG_QUERY_PATH:
            return subprocess.CompletedProcess(arguments, 0, self.installed_version, "")
        if arguments[0] == DPKG_PATH:
            return subprocess.run(arguments, **options)
        if arguments[0] == APT_GET_PATH:
            self.installed_payload = Path(arguments[-1]).read_bytes()
            return subprocess.CompletedProcess(arguments, 0, "", "")
        raise AssertionError(f"unexpected helper command: {arguments}")


class UpdateHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key_directory = tempfile.TemporaryDirectory()
        root = Path(cls.key_directory.name)
        cls.private_key = root / "private.pem"
        cls.public_key = root / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", cls.private_key],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                cls.private_key,
                "-pubout",
                "-out",
                cls.public_key,
            ],
            check=True,
            capture_output=True,
        )
        cls.public_key.chmod(0o644)

    @classmethod
    def tearDownClass(cls):
        cls.key_directory.cleanup()

    def create_bundle(self, root: Path, package=b"debian-package", version="0.4.0"):
        package_path = root / f"powersifu_{version}_all.deb"
        manifest_path = root / f"{package_path.name}.manifest.json"
        signature_path = root / f"{manifest_path.name}.sig"
        package_path.write_bytes(package)
        manifest_path.write_text(
            json.dumps(
                {
                    "architecture": "all",
                    "filename": package_path.name,
                    "package": "powersifu",
                    "schema": 1,
                    "sha256": hashlib.sha256(package).hexdigest(),
                    "size": len(package),
                    "version": version,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                self.private_key,
                "-in",
                manifest_path,
                "-out",
                signature_path,
            ],
            check=True,
            capture_output=True,
        )
        return package_path, manifest_path, signature_path

    def install(self, bundle, root, runner):
        install_signed_update(
            *bundle,
            runner=runner,
            staging_root=root / "protected-staging",
            public_key_path=self.public_key,
            expected_uid=os.getuid(),
            effective_uid=0,
        )

    def test_installs_only_the_root_staged_authenticated_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self.create_bundle(root)
            runner = HelperRunner()
            self.install(bundle, root, runner)
            self.assertEqual(runner.installed_payload, b"debian-package")
            apt_call = next(call for call in runner.calls if call[0] == APT_GET_PATH)
            self.assertIn("protected-staging/transaction-", apt_call[-1])
            self.assertFalse(Path(apt_call[-1]).exists())

    def test_rejects_package_replaced_after_desktop_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self.create_bundle(root)
            bundle[0].write_bytes(b"malicious-deb!")
            runner = HelperRunner()
            with self.assertRaisesRegex(UpdateInstallError, "SHA-256"):
                self.install(bundle, root, runner)
            self.assertIsNone(runner.installed_payload)

    def test_rejects_symlink_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = list(self.create_bundle(root))
            real_package = root / "real-package.deb"
            bundle[0].replace(real_package)
            bundle[0].symlink_to(real_package)
            with self.assertRaisesRegex(UpdateInstallError, "securely open"):
                self.install(tuple(bundle), root, HelperRunner())

    def test_rejects_signed_downgrade(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self.create_bundle(root, version="0.3.5")
            runner = HelperRunner(installed_version="0.3.6", package_version="0.3.5")
            with self.assertRaisesRegex(UpdateInstallError, "Refusing to install"):
                self.install(bundle, root, runner)
            self.assertIsNone(runner.installed_payload)

    def test_requires_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self.create_bundle(root)
            with self.assertRaisesRegex(UpdateInstallError, "must run as root"):
                install_signed_update(
                    *bundle,
                    runner=HelperRunner(),
                    staging_root=root / "stage",
                    public_key_path=self.public_key,
                    expected_uid=os.getuid(),
                    effective_uid=1000,
                )


if __name__ == "__main__":
    unittest.main()
