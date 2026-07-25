"""Cloudflare requests must finish before the Controller kills the Power."""

import unittest

from lib.cloudflare import HTTP_TIMEOUT


class HttpTimeoutTests(unittest.TestCase):
    def test_http_timeout_finishes_inside_the_power_deadline(self) -> None:
        self.assertIsNotNone(HTTP_TIMEOUT.total)
        self.assertLess(HTTP_TIMEOUT.total, 8)
        self.assertIsNotNone(HTTP_TIMEOUT.sock_read)
        self.assertLess(HTTP_TIMEOUT.sock_read, HTTP_TIMEOUT.total)


if __name__ == "__main__":
    unittest.main()
