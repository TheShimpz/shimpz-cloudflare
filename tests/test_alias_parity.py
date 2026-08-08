"""Runtime validators derive from the public schema type aliases."""

from __future__ import annotations

import unittest
from typing import get_args, get_type_hints

from lib import cloudflare as cf
from powers.list_zones import run as list_zones


def _pattern(annotation: object) -> object:
    return next(value["pattern"] for value in get_args(annotation) if isinstance(value, dict))


def _bounds(annotation: object) -> dict[str, int]:
    return next(value for value in get_args(annotation) if isinstance(value, dict))


class AliasParityTests(unittest.TestCase):
    def test_runtime_type_sets_derive_from_literals(self) -> None:
        self.assertEqual(cf._DNS_TYPES, frozenset(get_args(cf.DnsType)))
        self.assertEqual(cf._WRITABLE_DNS_TYPES, frozenset(get_args(cf.WritableDnsType)))
        self.assertEqual(cf._ZONE_TYPES, frozenset(get_args(cf.ZoneType)))

    def test_runtime_patterns_and_schema_metadata_share_constants(self) -> None:
        self.assertEqual(cf._HEX_ID.pattern, cf._HEX_ID_PATTERN)
        self.assertEqual(cf._STATUS.pattern, cf._STATUS_PATTERN)
        self.assertEqual(_pattern(cf.CloudflareId), cf._HEX_ID_PATTERN)
        self.assertEqual(_pattern(cf.ZoneStatus), cf._STATUS_PATTERN)

    def test_list_zones_uses_the_provider_exact_page_bounds(self) -> None:
        self.assertEqual(_bounds(cf.ZonesPerPage), {"minimum": 5, "maximum": 50})
        self.assertEqual(get_type_hints(list_zones, include_extras=True)["per_page"], cf.ZonesPerPage)
