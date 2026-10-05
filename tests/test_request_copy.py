"""Mutation authorizations are declared catalog copy whose parameters Team can admit and render."""

from __future__ import annotations

import hashlib
import io
import json
import unittest
from pathlib import Path

from shimpz._bridge import dispatch

ROOT = Path(__file__).resolve().parents[1]
ZONE_ID = "a" * 32
RECORD_ID = "c" * 32
TITLE = "Confirm with your Shimpz Supervisor password"
PREFIX = "Enter your current Shimpz Supervisor password before "
OPERATION_ID = "0b1f6c1e-3d6a-4f7e-9a2b-5c8d7e6f1a20"


def _bridge(*arguments: str, payload: object | None = None) -> dict[str, object]:
    """Call the bridge the CLI uses for `shimpz assistant run` and its English rendering."""
    source = io.StringIO("" if payload is None else json.dumps(payload))
    return json.loads(dispatch(list(arguments), source))


def _invocation(action_input: dict[str, object]) -> dict[str, object]:
    return {
        "input": action_input,
        "integrations": {"cloudflare": "unused"},
        "stored_inputs": {},
        "files": {},
        "operation_id": OPERATION_ID,
    }


def _request(action: str, action_input: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    outcome = _bridge(
        "invoke",
        str(ROOT),
        action,
        payload=_invocation(action_input),
    )
    if outcome["type"] != "request":
        raise AssertionError("the Action did not request authorization first")
    request = outcome["request"]
    return request, _bridge("render", str(ROOT), payload={"request": request})


def _ensure_input(name: str, record_type: str = "TXT") -> dict[str, object]:
    return {
        "zone_id": ZONE_ID,
        "record_type": record_type,
        "name": name,
        "content": "proof",
        "ttl": 1,
        "proxied": False,
    }


class RequestCopyTests(unittest.TestCase):
    def test_catalog_declares_every_authorization_message_with_typed_parameters(self) -> None:
        catalog = _bridge("catalog", str(ROOT))

        descriptions = [message for message in catalog["messages"] if message["msgid"].startswith(PREFIX)]
        self.assertEqual(len(descriptions), 3)
        for message in catalog["messages"]:
            with self.subTest(msgid=message["msgid"]):
                self.assertEqual(message["id"], hashlib.sha256(message["msgid"].encode()).hexdigest())
                kinds = {param["name"]: (param["kind"], param["max_length"]) for param in message["params"]}
                for name in {"zone_id", "record_id"} & set(kinds):
                    self.assertEqual(kinds[name], ("identifier", 32))
                if "record_type" in kinds:
                    self.assertEqual(kinds["record_type"], ("identifier", 5))
                if "name" in kinds:
                    self.assertEqual(kinds["name"], ("dns_name", 253))

    def test_ids_are_identifier_parameters_of_delete_and_replace(self) -> None:
        replace_input = {**_ensure_input("api.shimpz.com", "A"), "record_id": RECORD_ID, "content": "192.0.2.1"}
        for action, action_input, verb in (
            ("delete-dns-record", {"zone_id": ZONE_ID, "record_id": RECORD_ID}, "permanently deleting"),
            ("replace-dns-record", replace_input, "replacing"),
        ):
            with self.subTest(action=action):
                request, rendered = _request(action, action_input)

                self.assertEqual(request["kind"], "auth:password")
                self.assertEqual(request["description"]["params"], {"record_id": RECORD_ID, "zone_id": ZONE_ID})
                self.assertEqual(rendered["title"], TITLE)
                self.assertTrue(rendered["description"].startswith(f"{PREFIX}{verb} record {RECORD_ID}"))
                self.assertIn(f"zone {ZONE_ID}.", rendered["description"])
                self.assertEqual(rendered["fingerprint"], request["fingerprint"])

    def test_ensure_always_shows_the_exact_record_name(self) -> None:
        longest = ".".join(["a_" + "x" * 61, "y" * 63, "z" * 63, "_" + "w" * 60])
        self.assertEqual(len(longest), 253)
        for name, record_type in (
            ("api.shimpz.com", "A"),
            ("s1._domainkey.shimpz.com", "TXT"),
            ("_acme-challenge.shimpz.com", "TXT"),
            ("_dmarc.shimpz.com", "TXT"),
            ("_dmarc", "TXT"),
            (longest, "TXT"),
        ):
            with self.subTest(name=name):
                content = "192.0.2.1" if record_type == "A" else "proof"
                request, rendered = _request(
                    "ensure-dns-record", {**_ensure_input(name, record_type), "content": content}
                )

                self.assertEqual(request["description"]["params"], {"name": name, "record_type": record_type})
                self.assertEqual(
                    rendered["description"],
                    f"{PREFIX}creating the reviewed {record_type} record {name} if it is absent.",
                )
                self.assertEqual(rendered["fingerprint"], request["fingerprint"])

    def test_ensure_refuses_a_name_the_write_would_refuse_before_asking(self) -> None:
        for name in ("Api.shimpz.com", "api..shimpz.com", "*.shimpz.com", "-api.shimpz.com", "shimpz.com."):
            with self.subTest(name=name):
                outcome = _bridge("invoke", str(ROOT), "ensure-dns-record", payload=_invocation(_ensure_input(name)))

                self.assertEqual(outcome["type"], "failure")
                self.assertEqual(outcome["failure"]["error_type"], "lib.cloudflare.CloudflareApiError")


if __name__ == "__main__":
    unittest.main()
