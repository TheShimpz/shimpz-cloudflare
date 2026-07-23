"""Read-only Cloudflare Powers authored with the Shimpz Python SDK."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal, TypedDict
from urllib.parse import quote

import aiohttp
from shimpz import field, power

CLOUDFLARE_API_ORIGIN = "https://api.cloudflare.com"
MAX_RESPONSE_BYTES = 512 * 1024
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=3, sock_connect=3, sock_read=6)
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

Page = Annotated[int, {"minimum": 1, "maximum": 100_000}]
PerPage = Annotated[int, {"minimum": 1, "maximum": 100}]
CloudflareId = Annotated[str, {"pattern": "^[0-9a-f]{32}$"}]
ZoneName = Annotated[str, {"minLength": 1, "maxLength": 255}]
AccountName = Annotated[str, {"minLength": 1, "maxLength": 160}]
ZoneStatus = Annotated[str, {"pattern": "^[a-z][a-z0-9_-]{0,31}$"}]
DnsContent = Annotated[str, {"minLength": 1, "maxLength": 65_535}]
DnsTtl = Annotated[int, {"minimum": 1, "maximum": 2_147_483_647}]
ZoneType = Literal["full", "internal", "partial", "secondary"]
DnsType = Literal[
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
]


class Pagination(TypedDict):
    page: Annotated[int, {"minimum": 1}]
    per_page: PerPage
    count: Annotated[int, {"minimum": 0, "maximum": 100}]
    total_count: Annotated[int, {"minimum": 0}]
    total_pages: Annotated[int, {"minimum": 0}]


class CloudflareAccount(TypedDict):
    id: CloudflareId
    name: AccountName


class Zone(TypedDict):
    id: CloudflareId
    name: ZoneName
    status: ZoneStatus
    type: ZoneType
    paused: bool
    account: CloudflareAccount


class DnsRecord(TypedDict):
    id: CloudflareId
    type: DnsType
    name: ZoneName
    content: DnsContent
    ttl: DnsTtl
    proxied: bool
    proxiable: bool


class ZoneResult(TypedDict):
    zones: Annotated[list[Zone], {"maxItems": 100}]
    pagination: Pagination


class DnsRecordResult(TypedDict):
    records: Annotated[list[DnsRecord], {"maxItems": 100}]
    pagination: Pagination


class CloudflareApiError(RuntimeError):
    """Cloudflare did not satisfy the declared read-only Power contract."""


class CloudflareReauthorizationRequiredError(CloudflareApiError):
    """The OAuth access token is no longer accepted."""


class CloudflareApiClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def list_zones(self, page: int, per_page: int, access_token: str) -> ZoneResult:
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
    ) -> DnsRecordResult:
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
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Authorization": f"Bearer {access_token}",
        }
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
                raw = await _read_bounded(response.content)
        except CloudflareApiError:
            raise
        except Exception as exc:
            raise CloudflareApiError("Cloudflare request failed") from exc
        if not 1 <= len(raw) <= MAX_RESPONSE_BYTES:
            raise CloudflareApiError("Cloudflare response size is invalid")
        try:
            payload = json.loads(raw, parse_constant=_reject_json_constant, object_pairs_hook=_unique_object)
        except (UnicodeError, ValueError) as exc:
            raise CloudflareApiError("Cloudflare response JSON is invalid") from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise CloudflareApiError("Cloudflare response is invalid")
        return payload


def create_http_session() -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(limit=16, limit_per_host=16, ttl_dns_cache=60)
    return aiohttp.ClientSession(
        auto_decompress=False,
        connector=connector,
        timeout=HTTP_TIMEOUT,
        trust_env=True,
        headers={"User-Agent": "shimpz-cloudflare/0.2.0"},
    )


@power(accounts=["cloudflare"])
async def list_zones(
    page=field(Page, prompt="Cloudflare result page, starting at 1."),
    per_page=field(PerPage, prompt="Number of zones to return, from 1 to 100."),
    ctx=None,
) -> ZoneResult:
    async with create_http_session() as session:
        return await CloudflareApiClient(session).list_zones(
            page,
            per_page,
            ctx.accounts.cloudflare.access_token,
        )


@power(accounts=["cloudflare"])
async def list_dns_records(
    zone_id=field(CloudflareId, prompt="The 32-character hexadecimal Cloudflare zone id."),
    page=field(Page, prompt="Cloudflare result page, starting at 1."),
    per_page=field(PerPage, prompt="Number of DNS records to return, from 1 to 100."),
    ctx=None,
) -> DnsRecordResult:
    async with create_http_session() as session:
        return await CloudflareApiClient(session).list_dns_records(
            zone_id,
            page,
            per_page,
            ctx.accounts.cloudflare.access_token,
        )


async def _read_bounded(content: Any) -> bytes:
    raw = bytearray()
    while True:
        chunk = await content.read(min(64 * 1024, (MAX_RESPONSE_BYTES + 1) - len(raw)))
        if not chunk:
            return bytes(raw)
        raw.extend(chunk)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise CloudflareApiError("Cloudflare response size is invalid")


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
) -> Pagination:
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


def _zone(value: Mapping[str, Any]) -> Zone:
    account = value.get("account")
    if not isinstance(account, dict):
        raise CloudflareApiError("Cloudflare zone is invalid")
    return {
        "id": _id(value.get("id")),
        "name": _text(value.get("name"), 255),
        "status": _matching_text(value.get("status"), _STATUS),
        "type": _enum(value.get("type"), _ZONE_TYPES),  # type: ignore[typeddict-item]
        "paused": _boolean(value.get("paused")),
        "account": {"id": _id(account.get("id")), "name": _text(account.get("name"), 160)},
    }


def _dns_record(value: Mapping[str, Any]) -> DnsRecord:
    ttl = value.get("ttl")
    if type(ttl) is not int or not 1 <= ttl <= 2_147_483_647:
        raise CloudflareApiError("Cloudflare DNS record is invalid")
    return {
        "id": _id(value.get("id")),
        "type": _enum(value.get("type"), _DNS_TYPES),  # type: ignore[typeddict-item]
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


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
