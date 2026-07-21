"""Bounded fixed-host adapter for the read-only Cloudflare API Powers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from aiohttp import ClientSession

from assistant import load_strict_json

CLOUDFLARE_API_ORIGIN = "https://api.cloudflare.com"
MAX_RESPONSE_BYTES = 512 * 1024
_HEX_ID = re.compile(r"^[0-9a-f]{32}$")
_STATUS = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_DNS_TYPES = frozenset(
    {
        "A",
        "AAAA",
        "CAA",
        "CERT",
        "CNAME",
        "DNSKEY",
        "DS",
        "HTTPS",
        "LOC",
        "MX",
        "NAPTR",
        "NS",
        "OPENPGPKEY",
        "PTR",
        "SMIMEA",
        "SRV",
        "SSHFP",
        "SVCB",
        "TLSA",
        "TXT",
        "URI",
    }
)
_ZONE_TYPES = frozenset({"full", "partial", "secondary", "internal"})


class CloudflareApiError(RuntimeError):
    """Cloudflare did not satisfy the declared read-only Power contract."""


class CloudflareReauthorizationRequiredError(CloudflareApiError):
    """The OAuth access token is no longer accepted."""


class CloudflareApiClient:
    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list_zones(self, page: int, per_page: int, access_token: str) -> dict[str, Any]:
        payload = await self._get(
            "/client/v4/zones",
            access_token,
            {"page": str(page), "per_page": str(per_page), "order": "name", "direction": "asc"},
        )
        zones = [_zone(item) for item in _result(payload, per_page)]
        return {"zones": zones, "pagination": _pagination(payload, page, per_page, len(zones))}

    async def list_dns_records(
        self,
        zone_id: str,
        page: int,
        per_page: int,
        access_token: str,
    ) -> dict[str, Any]:
        payload = await self._get(
            f"/client/v4/zones/{quote(zone_id, safe='')}/dns_records",
            access_token,
            {"page": str(page), "per_page": str(per_page), "order": "name", "direction": "asc"},
        )
        records = [_dns_record(item) for item in _result(payload, per_page)]
        return {"records": records, "pagination": _pagination(payload, page, per_page, len(records))}

    async def _get(self, path: str, access_token: str, params: Mapping[str, str]) -> dict[str, Any]:
        if not path.startswith("/client/v4/") or "?" in path or "#" in path:
            raise CloudflareApiError("undeclared Cloudflare endpoint")
        headers = {"Accept": "application/json", "Authorization": f"Bearer {access_token}"}
        try:
            async with self._session.get(
                f"{CLOUDFLARE_API_ORIGIN}{path}",
                headers=headers,
                params=params,
                allow_redirects=False,
            ) as response:
                if response.status == 401:
                    raise CloudflareReauthorizationRequiredError("Cloudflare reauthorization is required")
                if response.status != 200:
                    raise CloudflareApiError("Cloudflare rejected the request")
                media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                content_encoding = response.headers.get("Content-Encoding", "").strip()
                raw_length = response.headers.get("Content-Length")
                if media_type != "application/json" or content_encoding:
                    raise CloudflareApiError("Cloudflare response metadata is invalid")
                if raw_length is not None and (
                    not raw_length.isascii() or not raw_length.isdigit() or int(raw_length) > MAX_RESPONSE_BYTES
                ):
                    raise CloudflareApiError("Cloudflare response size is invalid")
                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
        except CloudflareApiError:
            raise
        except Exception as exc:
            raise CloudflareApiError("Cloudflare request failed") from exc
        if not 1 <= len(raw) <= MAX_RESPONSE_BYTES:
            raise CloudflareApiError("Cloudflare response size is invalid")
        try:
            payload = load_strict_json(raw)
        except (UnicodeError, ValueError) as exc:
            raise CloudflareApiError("Cloudflare response JSON is invalid") from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise CloudflareApiError("Cloudflare response is invalid")
        return payload


def _result(payload: Mapping[str, Any], maximum: int) -> list[Mapping[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, list) or len(result) > maximum or not all(isinstance(item, dict) for item in result):
        raise CloudflareApiError("Cloudflare result is invalid")
    return result


def _pagination(
    payload: Mapping[str, Any],
    expected_page: int,
    expected_per_page: int,
    expected_count: int,
) -> dict[str, int]:
    info = payload.get("result_info")
    if not isinstance(info, dict):
        raise CloudflareApiError("Cloudflare pagination is invalid")
    values = {key: info.get(key) for key in ("page", "per_page", "count", "total_count", "total_pages")}
    if any(type(value) is not int or value < 0 for value in values.values()):
        raise CloudflareApiError("Cloudflare pagination is invalid")
    if (
        values["page"] != expected_page
        or values["per_page"] != expected_per_page
        or values["count"] != expected_count
        or values["total_count"] < expected_count
        or values["total_pages"] < (1 if values["total_count"] else 0)
    ):
        raise CloudflareApiError("Cloudflare pagination is invalid")
    return values  # type: ignore[return-value]


def _zone(value: Mapping[str, Any]) -> dict[str, Any]:
    account = value.get("account")
    if not isinstance(account, dict):
        raise CloudflareApiError("Cloudflare zone is invalid")
    return {
        "id": _id(value.get("id")),
        "name": _text(value.get("name"), 255),
        "status": _matching_text(value.get("status"), _STATUS),
        "type": _enum(value.get("type"), _ZONE_TYPES),
        "paused": _boolean(value.get("paused")),
        "account": {"id": _id(account.get("id")), "name": _text(account.get("name"), 160)},
    }


def _dns_record(value: Mapping[str, Any]) -> dict[str, Any]:
    ttl = value.get("ttl")
    if type(ttl) is not int or not 1 <= ttl <= 2_147_483_647:
        raise CloudflareApiError("Cloudflare DNS record is invalid")
    return {
        "id": _id(value.get("id")),
        "type": _enum(value.get("type"), _DNS_TYPES),
        "name": _text(value.get("name"), 255),
        "content": _text(value.get("content"), 65_535),
        "ttl": ttl,
        "proxied": _boolean(value.get("proxied")),
        "proxiable": _boolean(value.get("proxiable")),
    }


def _id(value: object) -> str:
    if not isinstance(value, str) or _HEX_ID.fullmatch(value) is None:
        raise CloudflareApiError("Cloudflare identifier is invalid")
    return value


def _text(value: object, maximum: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise CloudflareApiError("Cloudflare text is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise CloudflareApiError("Cloudflare text is invalid")
    return value


def _matching_text(value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise CloudflareApiError("Cloudflare status is invalid")
    return value


def _enum(value: object, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise CloudflareApiError("Cloudflare enum is invalid")
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise CloudflareApiError("Cloudflare boolean is invalid")
    return value
