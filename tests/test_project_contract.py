from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StaticAssistantProjectContractTests(unittest.TestCase):
    def test_manifest_declares_only_read_only_cloudflare_contract(self) -> None:
        manifest = tomllib.loads((ROOT / "shimpz.assistant.toml").read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["name"], "Shimpz Cloudflare")
        self.assertEqual(manifest["github"], "https://github.com/TheShimpz/shimpz-cloudflare")
        self.assertEqual(manifest["allowed_hosts"], ["api.cloudflare.com"])
        self.assertEqual(
            manifest["accounts"],
            {
                "cloudflare": {
                    "provider": "cloudflare",
                    "scopes": ["zone.read", "dns.read", "offline_access"],
                }
            },
        )
        self.assertEqual(set(manifest["powers"]), {"list-zones", "list-dns-records"})
        for power in manifest["powers"].values():
            self.assertEqual(power["approval"], "never")
            self.assertEqual(power["accounts"], ["cloudflare"])
        serialized = json.dumps(manifest)
        self.assertNotIn(".write", serialized)
        self.assertNotIn("secret", serialized.lower())

    def test_schemas_are_closed_and_bounded(self) -> None:
        schema_paths = sorted((ROOT / "schemas").glob("*.schema.json"))
        self.assertEqual(
            {path.name for path in schema_paths},
            {
                "list-zones.input.schema.json",
                "list-zones.output.schema.json",
                "list-dns-records.input.schema.json",
                "list-dns-records.output.schema.json",
            },
        )
        for path in schema_paths:
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(schema["type"], "object", path.name)
            self.assertIs(schema["additionalProperties"], False, path.name)
            self.assertLess(path.stat().st_size, 32 * 1024)

    def test_static_admission_documents_and_image_are_bounded_and_complete(self) -> None:
        for filename, maximum in (("GENESIS.md", 128 * 1024), ("CHANGELOG.md", 64 * 1024)):
            raw = (ROOT / filename).read_bytes()
            self.assertGreater(len(raw), 0)
            self.assertLessEqual(len(raw), maximum)
            self.assertNotIn(b"<script", raw.lower())

        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn('org.shimpz.assistant.id="shimpz-cloudflare"', dockerfile)
        self.assertIn("assistant/cloudflare_api.py", dockerfile)
        self.assertIn("--require-hashes", dockerfile)


if __name__ == "__main__":
    unittest.main()
