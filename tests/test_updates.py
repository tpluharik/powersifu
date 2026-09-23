import json
import unittest

from powersifu.updates import UpdateCheckError, check_for_update


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


class UpdateTests(unittest.TestCase):
    def test_detects_new_debian_release(self):
        info = check_for_update(
            "0.2.0",
            opener=opener_for(
                {
                    "tag_name": "v0.3.0",
                    "html_url": "https://github.com/tpluharik/powersifu/releases/tag/v0.3.0",
                    "assets": [
                        {
                            "name": "powersifu_0.3.0_all.deb",
                            "browser_download_url": "https://github.com/tpluharik/powersifu/releases/download/v0.3.0/powersifu_0.3.0_all.deb",
                        }
                    ],
                }
            ),
        )
        self.assertTrue(info.available)
        self.assertEqual(info.latest_version, "0.3.0")
        self.assertTrue(info.download_url.endswith("powersifu_0.3.0_all.deb"))

    def test_current_release_is_up_to_date(self):
        info = check_for_update(
            "0.2.0",
            opener=opener_for(
                {
                    "tag_name": "v0.2.0",
                    "html_url": "https://github.com/tpluharik/powersifu/releases/tag/v0.2.0",
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


if __name__ == "__main__":
    unittest.main()
