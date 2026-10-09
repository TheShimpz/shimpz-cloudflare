"""Cloudflare calls must finish before the Controller kills the Action."""

import unittest

from lib.cloudflare import CALL_TIMEOUT_MS


class CallTimeoutTests(unittest.TestCase):
    def test_a_call_finishes_inside_the_action_deadline(self) -> None:
        self.assertLess(CALL_TIMEOUT_MS, 8000)


if __name__ == "__main__":
    unittest.main()
