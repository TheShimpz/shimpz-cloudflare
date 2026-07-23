from __future__ import annotations

import json
import unittest
from pathlib import Path

from shimpz._runner import RpcInputError, invoke

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


def _envelope(power_input: dict[str, object], *, account: bool = True) -> bytes:
    accounts = (
        {
            "cloudflare": {
                "type": "oauth2-bearer",
                "access_token": "opaque-access-token",
            }
        }
        if account
        else {}
    )
    return json.dumps(
        {
            "input": power_input,
            "secrets": {},
            "accounts": accounts,
            "answers": [],
        },
        separators=(",", ":"),
    ).encode()


class SdkRuntimeTests(unittest.TestCase):
    def test_fixed_health_and_localized_help_use_the_sdk_rpc(self) -> None:
        empty = _envelope({}, account=False)

        self.assertEqual(
            json.loads(invoke("GET", "/healthz", empty, app_path=APP)),
            {"result": {"status": "ok"}},
        )
        self.assertEqual(
            json.loads(invoke("GET", "/v1/help/pt", empty, app_path=APP)),
            {"result": {"markdown": (ROOT / "help" / "HELP-pt.md").read_text(encoding="utf-8")}},
        )

    def test_runner_rejects_undeclared_routes_accounts_and_bounded_fields(self) -> None:
        invalid = (
            ("POST", "/v1/powers/shell", _envelope({})),
            ("POST", "/v1/powers/list-zones", _envelope({"page": 1, "per_page": 25}, account=False)),
            ("POST", "/v1/powers/list-zones", _envelope({"page": 0, "per_page": 25})),
            (
                "POST",
                "/v1/powers/list-dns-records",
                _envelope({"zone_id": "../escape", "page": 1, "per_page": 25}),
            ),
        )

        for method, path, payload in invalid:
            with self.subTest(path=path, payload=payload), self.assertRaises(RpcInputError):
                invoke(method, path, payload, app_path=APP)


if __name__ == "__main__":
    unittest.main()
