import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from powersifu.updates import (
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
    def update_info(self):
        return UpdateInfo(
            current_version="0.3.1",
            latest_version="0.4.0",
            release_url="https://github.com/tpluharik/powersifu/releases/tag/v0.4.0",
            download_url=(
                "https://github.com/tpluharik/powersifu/releases/download/"
                "v0.4.0/powersifu_0.4.0_all.deb"
            ),
            download_sha256=hashlib.sha256(b"debian-package").hexdigest(),
            download_size=len(b"debian-package"),
        )

    def test_detects_new_debian_release(self):
        info = check_for_update(
            "0.3.1",
            opener=opener_for(
                {
                    "tag_name": "v0.4.0",
                    "html_url": "https://github.com/tpluharik/powersifu/releases/tag/v0.4.0",
                    "assets": [
                        {
                            "name": "powersifu_0.4.0_all.deb",
                            "browser_download_url": "https://github.com/tpluharik/powersifu/releases/download/v0.4.0/powersifu_0.4.0_all.deb",
                            "digest": "sha256:" + "a" * 64,
                            "size": 12345,
                        }
                    ],
                }
            ),
        )
        self.assertTrue(info.available)
        self.assertEqual(info.latest_version, "0.4.0")
        self.assertTrue(info.download_url.endswith("powersifu_0.4.0_all.deb"))
        self.assertEqual(info.download_sha256, "a" * 64)
        self.assertEqual(info.download_size, 12345)

    def test_current_release_is_up_to_date(self):
        info = check_for_update(
            "0.3.1",
            opener=opener_for(
                {
                    "tag_name": "v0.3.1",
                    "html_url": "https://github.com/tpluharik/powersifu/releases/tag/v0.3.1",
                    "assets": [],
                }
            ),
        )
        self.assertFalse(info.available)
        self.assertIsNone(info.download_url)

    def test_untrusted_release_url_is_rejected(self):
        with self.assertRaisesRegex(UpdateCheckError, "untrusted URL"):
            check_for_update(
                "0.2.0",
                opener=opener_for(
                    {
                        "tag_name": "v0.3.0",
                        "html_url": "https://example.com/not-powersifu",
                        "assets": [],
                    }
                ),
            )

    def test_downloads_and_verifies_release_package(self):
        info = self.update_info()
        package_runner = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, "Package: powersifu\nVersion: 0.4.0\nArchitecture: all\n", ""
            )
        )

        with tempfile.TemporaryDirectory() as temporary:
            path = download_update(
                info,
                destination_dir=Path(temporary),
                opener=lambda _request, timeout: FakeDownloadResponse(
                    b"debian-package",
                    "https://release-assets.githubusercontent.com/powersifu_0.4.0_all.deb",
                ),
                package_runner=package_runner,
            )

            self.assertEqual(path.name, "powersifu_0.4.0_all.deb")
            self.assertEqual(path.read_bytes(), b"debian-package")
            package_runner.assert_called_once()

    def test_rejects_wrong_package_metadata(self):
        info = self.update_info()
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

    def test_rejects_download_with_wrong_sha256(self):
        info = self.update_info()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(UpdateInstallError, "SHA-256 digest"):
                download_update(
                    info,
                    destination_dir=Path(temporary),
                    opener=lambda _request, timeout: FakeDownloadResponse(
                        b"tamper-package",
                        "https://release-assets.githubusercontent.com/powersifu_0.4.0_all.deb",
                    ),
                )

    def test_rejects_download_redirect_to_untrusted_host(self):
        info = self.update_info()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(UpdateInstallError, "untrusted URL"):
                download_update(
                    info,
                    destination_dir=Path(temporary),
                    opener=lambda _request, timeout: FakeDownloadResponse(
                        b"debian-package",
                        "https://example.com/powersifu_0.4.0_all.deb",
                    ),
                )

    def test_installs_verified_package_with_system_authentication(self):
        runner = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "powersifu_0.4.0_all.deb"
            package.write_bytes(b"package")
            install_update(package, runner=runner)

        runner.assert_called_once_with(
            ["pkexec", "apt-get", "install", "--yes", str(package.resolve())],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )

    def test_reports_cancelled_authentication(self):
        runner = Mock(
            side_effect=subprocess.CalledProcessError(126, ["pkexec", "apt-get"])
        )
        with self.assertRaisesRegex(UpdateInstallError, "cancelled"):
            install_update(Path("/tmp/powersifu.deb"), runner=runner)


if __name__ == "__main__":
    unittest.main()
