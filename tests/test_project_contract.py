from __future__ import annotations

import importlib
import inspect
import tomllib
import unittest
from pathlib import Path

from shimpz.power import PowerMetadata, get_power_metadata

ROOT = Path(__file__).resolve().parents[1]


class StaticAssistantProjectContractTests(unittest.TestCase):
    def test_manifest_is_a_complete_spec_v1_intent(self) -> None:
        manifest = tomllib.loads((ROOT / "shimpz.toml").read_text(encoding="utf-8"))

        self.assertEqual(
            set(manifest),
            {"spec", "version", "name", "summary", "creators", "github", "allowed_hosts", "genesis", "accounts"},
        )
        self.assertEqual(manifest["spec"], 1)
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["github"], "https://github.com/TheShimpz/shimpz-cloudflare")
        self.assertEqual(manifest["allowed_hosts"], ["api.cloudflare.com"])
        self.assertEqual(
            manifest["accounts"],
            {"cloudflare": {"scopes": ["zone.read", "dns.read", "offline_access"]}},
        )

    def test_each_power_is_one_direct_python_file(self) -> None:
        powers = ROOT / "powers"
        self.assertEqual(
            {path.name for path in powers.iterdir() if path.name != "__pycache__"},
            {"list_zones.py", "list_dns_records.py"},
        )
        declared_accounts = set(tomllib.loads((ROOT / "shimpz.toml").read_text(encoding="utf-8"))["accounts"])
        used_accounts: set[str] = set()
        for module_name in ("powers.list_zones", "powers.list_dns_records"):
            with self.subTest(module=module_name):
                body = importlib.import_module(module_name).run
                self.assertTrue(inspect.iscoroutinefunction(body))
                self.assertEqual(body.__name__, "run")
                metadata = get_power_metadata(body)
                self.assertIsInstance(metadata, PowerMetadata)
                accounts = set(metadata.accounts)
                self.assertLessEqual(accounts, declared_accounts)
                used_accounts.update(accounts)
        self.assertEqual(used_accounts, declared_accounts)

    def test_repository_contains_no_generated_or_container_files(self) -> None:
        absent = {
            ".dockerignore",
            "CHANGELOG.md",
            "Dockerfile",
            "GENESIS.md",
            "requirements.lock",
            "shimpz.contract.json",
            "uv.lock",
        }
        self.assertFalse({name for name in absent if (ROOT / name).exists()})


if __name__ == "__main__":
    unittest.main()
