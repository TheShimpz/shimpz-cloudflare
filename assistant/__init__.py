"""Fail-closed private Power contracts for the Cloudflare Account."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

MAX_ACCESS_TOKEN_BYTES = 16 * 1024
MAX_PER_PAGE = 100
POWER_IDS = frozenset({"list-zones", "list-dns-records"})
ZONE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class PrivateEnvelopeError(ValueError):
    """A private RPC envelope does not match the selected Power contract."""


@dataclass(frozen=True, slots=True)
class PowerEnvelope:
    input: dict[str, Any]
    access_token: str


def validate_power_envelope(payload: object, power_id: str) -> PowerEnvelope:
    if power_id not in POWER_IDS:
        raise PrivateEnvelopeError("undeclared Power")
    if not isinstance(payload, dict) or set(payload) != {"input", "secrets", "accounts", "answers"}:
        raise PrivateEnvelopeError("invalid private envelope")
    power_input = payload["input"]
    secrets = payload["secrets"]
    accounts = payload["accounts"]
    if not isinstance(power_input, dict) or secrets != {} or not isinstance(accounts, dict) or payload["answers"] != []:
        raise PrivateEnvelopeError("the declared Cloudflare Account is required")
    if set(accounts) != {"cloudflare"}:
        raise PrivateEnvelopeError("the declared Cloudflare Account is required")
    account = accounts["cloudflare"]
    if not isinstance(account, dict) or set(account) != {"type", "access_token"}:
        raise PrivateEnvelopeError("the Cloudflare Account envelope is invalid")
    token = account["access_token"]
    if account["type"] != "oauth2-bearer" or not _access_token(token):
        raise PrivateEnvelopeError("the Cloudflare Account envelope is invalid")
    return PowerEnvelope(input=power_input, access_token=token)


def validate_power_input(power_id: str, payload: dict[str, Any]) -> None:
    if power_id not in POWER_IDS:
        raise ValueError("undeclared Power")
    if power_id == "list-zones":
        if set(payload) != {"page", "per_page"}:
            raise ValueError("zone list input is invalid")
    else:
        if set(payload) != {"zone_id", "page", "per_page"}:
            raise ValueError("DNS record list input is invalid")
        zone_id = payload["zone_id"]
        if not isinstance(zone_id, str) or ZONE_ID_PATTERN.fullmatch(zone_id) is None:
            raise ValueError("zone id is invalid")
    _bounded_integer(payload["page"], 1, 100_000, "page")
    _bounded_integer(payload["per_page"], 1, MAX_PER_PAGE, "per_page")


def load_strict_json(raw: bytes | str) -> Any:
    return json.loads(raw, parse_constant=_reject_json_constant, object_pairs_hook=_unique_object)


def _bounded_integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} is invalid")
    return value


def _access_token(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return 16 <= len(encoded) <= MAX_ACCESS_TOKEN_BYTES and all(33 <= byte <= 126 for byte in encoded)


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
