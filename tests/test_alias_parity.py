"""Runtime validators derive from the public schema type aliases."""

from __future__ import annotations

import unittest
from typing import get_args

from lib import cloudflare as cf


def _pattern(annotation: object) -> object:
    return next(value["pattern"] for value in get_args(annotation) if isinstance(value, dict))


class AliasParityTests(unittest.TestCase):
    def test_runtime_type_sets_derive_from_literals(self) -> None:
        self.assertEqual(cf._DNS_TYPES, frozenset(get_args(cf.DnsType)))
        self.assertEqual(cf._ZONE_TYPES, frozenset(get_args(cf.ZoneType)))

    def test_runtime_patterns_and_schema_metadata_share_constants(self) -> None:
        self.assertEqual(cf._HEX_ID.pattern, cf._HEX_ID_PATTERN)
        self.assertEqual(cf._STATUS.pattern, cf._STATUS_PATTERN)
        self.assertEqual(_pattern(cf.CloudflareId), cf._HEX_ID_PATTERN)
        self.assertEqual(_pattern(cf.ZoneStatus), cf._STATUS_PATTERN)
