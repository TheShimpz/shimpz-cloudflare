from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

from shimpz.contract import build_contract, canonical_json, load_app

ROOT = Path(__file__).resolve().parents[1]


class StaticAssistantProjectContractTests(unittest.TestCase):
    def test_manifest_declares_only_read_only_cloudflare_contract(self) -> None:
        manifest = tomllib.loads((ROOT / "shimpz.toml").read_text(encoding="utf-8"))

        self.assertEqual(
            set(manifest),
            {"name", "summary", "creators", "github", "allowed_hosts", "accounts"},
        )
        self.assertEqual(manifest["name"], "Shimpz Cloudflare")
        self.assertEqual(manifest["github"], "https://github.com/TheShimpz/shimpz-cloudflare")
        self.assertEqual(manifest["allowed_hosts"], ["api.cloudflare.com"])
        self.assertEqual(
            manifest["accounts"],
            {
                "cloudflare": {
                    "scopes": ["zone.read", "dns.read", "offline_access"],
                }
            },
        )
        serialized = json.dumps(manifest)
        self.assertNotIn(".write", serialized)
        self.assertNotIn("secret", serialized.lower())

    def test_sdk_contract_is_generated_closed_and_bounded(self) -> None:
        raw_contract = (ROOT / "shimpz.contract.json").read_text(encoding="utf-8")
        machine_contract = json.loads(raw_contract)
        load_app(ROOT / "app.py")
        self.assertEqual(raw_contract, canonical_json(build_contract()))
        self.assertEqual(machine_contract["version"], 1)
        self.assertEqual(
            {power["id"] for power in machine_contract["powers"]},
            {"list-zones", "list-dns-records"},
        )
        for power_contract in machine_contract["powers"]:
            self.assertEqual(power_contract["input_schema"]["type"], "object")
            self.assertIs(power_contract["input_schema"]["additionalProperties"], False)
            self.assertEqual(power_contract["output_schema"]["type"], "object")
            self.assertIs(power_contract["output_schema"]["additionalProperties"], False)
        self.assertLess(len(raw_contract.encode()), 32 * 1024)

    def test_static_admission_documents_and_image_are_bounded_and_complete(self) -> None:
        for filename, maximum in (("GENESIS.md", 128 * 1024), ("CHANGELOG.md", 64 * 1024)):
            raw = (ROOT / filename).read_bytes()
            self.assertGreater(len(raw), 0)
            self.assertLessEqual(len(raw), maximum)
            self.assertNotIn(b"<script", raw.lower())

        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn('org.shimpz.assistant.id="shimpz-cloudflare"', dockerfile)
        self.assertIn("shimpz-cloudflare/app.py", dockerfile)
        self.assertIn("shimpz-assistant-contract --app /opt/shimpz/app.py", dockerfile)
        self.assertNotIn("shimpz-cloudflare/shimpz.contract.json", dockerfile)
        self.assertIn('ENTRYPOINT ["shimpz-assistant"]', dockerfile)
        self.assertNotIn("assistant/main.py", dockerfile)
        self.assertIn("--require-hashes", dockerfile)


if __name__ == "__main__":
    unittest.main()
