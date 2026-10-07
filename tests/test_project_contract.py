from __future__ import annotations

import importlib
import inspect
import json
import re
import tomllib
import unittest
from pathlib import Path

from shimpz._project import AssistantProject
from shimpz.action import ActionMetadata, get_action_metadata

ROOT = Path(__file__).resolve().parents[1]


class StaticAssistantProjectContractTests(unittest.TestCase):
    def test_manifest_is_a_complete_spec_v1_intent(self) -> None:
        manifest = tomllib.loads((ROOT / "shimpz.toml").read_text(encoding="utf-8"))

        self.assertEqual(
            set(manifest),
            {
                "shimpz",
                "network",
                "integrations",
            },
        )
        metadata = manifest["shimpz"]
        self.assertEqual(
            set(metadata),
            {"spec", "id", "version", "name", "summary", "creators", "github", "genesis"},
        )
        self.assertEqual(set(manifest["network"]), {"allowed_hosts"})
        self.assertEqual(metadata["spec"], 1)
        self.assertEqual(metadata["id"], "shimpz-cloudflare")
        self.assertIsNotNone(
            re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", metadata["version"])
        )
        self.assertEqual(metadata["version"], "0.5.1")
        self.assertEqual(metadata["creators"], ["@shimpz"])
        self.assertEqual(metadata["github"], "https://github.com/TheShimpz/shimpz-cloudflare")
        self.assertEqual(manifest["network"]["allowed_hosts"], ["api.cloudflare.com"])
        self.assertEqual(
            manifest["integrations"],
            {"cloudflare": {"scopes": ["zone.read", "dns.read", "dns.write", "offline_access"]}},
        )

    def test_each_action_is_one_direct_python_file(self) -> None:
        actions = ROOT / "actions"
        self.assertEqual(
            {path.name for path in actions.iterdir() if path.name != "__pycache__"},
            {
                "delete_dns_record.py",
                "ensure_dns_record.py",
                "get_dns_record.py",
                "get_zone.py",
                "list_dns_records.py",
                "list_zones.py",
                "replace_dns_record.py",
            },
        )
        declared_integrations = set(tomllib.loads((ROOT / "shimpz.toml").read_text(encoding="utf-8"))["integrations"])
        used_integrations: set[str] = set()
        for module_name in (
            "actions.delete_dns_record",
            "actions.ensure_dns_record",
            "actions.get_zone",
            "actions.get_dns_record",
            "actions.list_zones",
            "actions.list_dns_records",
            "actions.replace_dns_record",
        ):
            with self.subTest(module=module_name):
                body = importlib.import_module(module_name).run
                self.assertTrue(inspect.iscoroutinefunction(body))
                self.assertEqual(body.__name__, "run")
                context = inspect.signature(body).parameters["ctx"]
                self.assertEqual(context.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(context.default, inspect.Parameter.empty)
                metadata = get_action_metadata(body)
                self.assertIsInstance(metadata, ActionMetadata)
                expected_requests = (
                    ("auth:password",)
                    if module_name
                    in {"actions.delete_dns_record", "actions.ensure_dns_record", "actions.replace_dns_record"}
                    else ()
                )
                self.assertEqual(metadata.human_requests, expected_requests)
                integrations = set(metadata.integrations)
                self.assertLessEqual(integrations, declared_integrations)
                used_integrations.update(integrations)
        self.assertEqual(used_integrations, declared_integrations)

    def test_machine_contract_declares_reads_read_only_and_writes_mutating(self) -> None:
        contract = json.loads(AssistantProject.load(ROOT).contract())

        self.assertEqual(
            {action["id"]: action["effect"] for action in contract["actions"]},
            {
                "delete-dns-record": "mutating",
                "ensure-dns-record": "mutating",
                "get-dns-record": "read_only",
                "get-zone": "read_only",
                "list-dns-records": "read_only",
                "list-zones": "read_only",
                "replace-dns-record": "mutating",
            },
        )


if __name__ == "__main__":
    unittest.main()
