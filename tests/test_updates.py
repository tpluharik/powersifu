import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from powersifu.updates import (
    UPDATE_HELPER_INTERPRETER,
    UPDATE_HELPER_PATH,
    DownloadedUpdate,
    UpdateCheckError,
    UpdateInfo,
    UpdateInstallError,
    check_for_update,
    download_update,
    install_update,
    verify_update_package,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.payload


def opener_for(data):
    payload = json.dumps(data).encode("utf-8")

    def opener(_request, timeout):
        if timeout != 8:
            raise AssertionError("unexpected timeout")
        return FakeResponse(payload)

    return opener


class FakeDownloadResponse:
    def __init__(self, payload, url):
        self.payload = payload
        self.url = url
        self.offset = 0
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self, limit):
        chunk = self.payload[self.offset : self.offset + limit]
        self.offset += len(chunk)
        return chunk


class UpdateTests(unittest.TestCase):
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

    @classmethod
    def tearDownClass(cls):
        cls.key_directory.cleanup()

    def signed_bundle(self, package=b"debian-package"):
        version = "0.4.0"
        package_name = f"powersifu_{version}_all.deb"
        manifest_name = f"{package_name}.manifest.json"
        signature_name = f"{manifest_name}.sig"
        manifest = json.dumps(
            {
                "architecture": "all",
                "filename": package_name,
                "package": "powersifu",
                "schema": 1,
                "sha256": hashlib.sha256(package).hexdigest(),
                "size": len(package),
                "version": version,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        with tempfile.TemporaryDirectory() as temporary:
            manifest_file = Path(temporary) / manifest_name
            signature_file = Path(temporary) / signature_name
            manifest_file.write_bytes(manifest)
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-sign",
                    "-rawin",
                    "-inkey",
                    self.private_key,
                    "-in",
                    manifest_file,
                    "-out",
                    signature_file,
                ],
                check=True,
                capture_output=True,
            )
            signature = signature_file.read_bytes()
        base = "https://github.com/tpluharik/powersifu/releases/download/v0.4.0/"
        info = UpdateInfo(
            current_version="0.3.6",
            latest_version=version,
            release_url="https://github.com/tpluharik/powersifu/releases/tag/v0.4.0",
            download_url=base + package_name,
            manifest_url=base + manifest_name,
            signature_url=base + signature_name,
            download_sha256=hashlib.sha256(package).hexdigest(),
            download_size=len(package),
            manifest_size=len(manifest),
            signature_size=len(signature),
        )
        return info, {
            package_name: package,
            manifest_name: manifest,
            signature_name: signature,
        }

    @staticmethod
    def bundle_opener(assets, final_host="release-assets.githubusercontent.com"):
        def opener(request, timeout):
            if timeout != 30:
                raise AssertionError("unexpected timeout")
            name = Path(request.full_url).name
            return FakeDownloadResponse(assets[name], f"https://{final_host}/{name}")

        return opener

    def test_detects_new_signed_debian_release(self):
        package_name = "powersifu_0.4.0_all.deb"
        manifest_name = f"{package_name}.manifest.json"
        signature_name = f"{manifest_name}.sig"
        info = check_for_update(
            "0.3.6",
            opener=opener_for(
                {
                    "tag_name": "v0.4.0",
                    "html_url": "https://github.com/tpluharik/powersifu/releases/tag/v0.4.0",
                    "assets": [
                        {
                            "name": package_name,
                            "browser_download_url": f"https://github.com/release/{package_name}",
                            "digest": "sha256:" + "a" * 64,
                            "size": 12345,
                        },
                        {
                            "name": manifest_name,
                            "browser_download_url": f"https://github.com/release/{manifest_name}",
                            "size": 250,
                        },
                        {
                            "name": signature_name,
                            "browser_download_url": f"https://github.com/release/{signature_name}",
                            "size": 64,
                        },
                    ],
                }
            ),
        )
        self.assertTrue(info.available)
        self.assertTrue(info.installable)
        self.assertEqual(info.latest_version, "0.4.0")
        self.assertEqual(info.download_sha256, "a" * 64)

    def test_current_release_is_up_to_date(self):
        info = check_for_update(
            "0.3.6",
            opener=opener_for(
                {
                    "tag_name": "v0.3.6",
                    "html_url": "https://github.com/tpluharik/powersifu/releases/tag/v0.3.6",
                    "assets": [],
                }
            ),
        )
        self.assertFalse(info.available)
        self.assertFalse(info.installable)

    def test_untrusted_release_url_is_rejected(self):
        with self.assertRaisesRegex(UpdateCheckError, "untrusted URL"):
            check_for_update(
                "0.3.6",
                opener=opener_for(
                    {
                        "tag_name": "v0.4.0",
                        "html_url": "https://example.com/not-powersifu",
                        "assets": [],
                    }
                ),
            )

    def test_downloads_and_authenticates_release_bundle(self):
        info, assets = self.signed_bundle()
        package_runner = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, "Package: powersifu\nVersion: 0.4.0\nArchitecture: all\n", ""
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            update = download_update(
                info,
                destination_dir=Path(temporary),
                opener=self.bundle_opener(assets),
                package_runner=package_runner,
                public_key_path=self.public_key,
            )
            self.assertEqual(update.package_path.read_bytes(), b"debian-package")
            self.assertTrue(update.manifest_path.is_file())
            self.assertTrue(update.signature_path.is_file())
            package_runner.assert_called_once()

    def test_rejects_wrong_package_metadata(self):
        info, _assets = self.signed_bundle()
        runner = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, "Package: impostor\nVersion: 0.4.0\nArchitecture: all\n", ""
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "powersifu_0.4.0_all.deb"
            package.write_bytes(b"not-empty")
            with self.assertRaisesRegex(UpdateInstallError, "expected Package powersifu"):
                verify_update_package(package, info, runner=runner)

    def test_rejects_package_tampered_after_manifest_was_signed(self):
        info, assets = self.signed_bundle()
        assets["powersifu_0.4.0_all.deb"] = b"debian-packagf"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(UpdateInstallError, "SHA-256"):
                download_update(
                    info,
                    destination_dir=Path(temporary),
                    opener=self.bundle_opener(assets),
                    public_key_path=self.public_key,
                )

    def test_rejects_tampered_signed_manifest(self):
        info, assets = self.signed_bundle()
        manifest_name = "powersifu_0.4.0_all.deb.manifest.json"
        assets[manifest_name] = assets[manifest_name].replace(b"0.4.0", b"0.4.1")
        info = UpdateInfo(**{**info.__dict__, "manifest_size": len(assets[manifest_name])})
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(UpdateInstallError, "signature is invalid"):
                download_update(
                    info,
                    destination_dir=Path(temporary),
                    opener=self.bundle_opener(assets),
                    public_key_path=self.public_key,
                )

    def test_rejects_download_redirect_to_untrusted_host(self):
        info, assets = self.signed_bundle()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(UpdateInstallError, "untrusted URL"):
                download_update(
                    info,
                    destination_dir=Path(temporary),
                    opener=self.bundle_opener(assets, final_host="example.com"),
                    public_key_path=self.public_key,
                )

    def test_installs_only_through_fixed_privileged_helper(self):
        runner = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            update = DownloadedUpdate(
                root / "package.deb",
                root / "manifest.json",
                root / "manifest.sig",
            )
            install_update(update, runner=runner)
        runner.assert_called_once_with(
            [
                "pkexec",
                UPDATE_HELPER_INTERPRETER,
                str(UPDATE_HELPER_PATH),
                str(update.package_path),
                str(update.manifest_path),
                str(update.signature_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )

    def test_reports_cancelled_authentication(self):
        runner = Mock(side_effect=subprocess.CalledProcessError(126, ["pkexec"]))
        update = DownloadedUpdate(
            Path("/tmp/package.deb"),
            Path("/tmp/manifest.json"),
            Path("/tmp/manifest.sig"),
        )
        with self.assertRaisesRegex(UpdateInstallError, "cancelled"):
            install_update(update, runner=runner)


if __name__ == "__main__":
    unittest.main()
