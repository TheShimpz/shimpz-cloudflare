"""Bounded access to the Cloudflare zones and DNS record APIs."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal, TypedDict, get_args
from urllib.parse import quote

import aiohttp

CLOUDFLARE_API_ORIGIN = "https://api.cloudflare.com"
MAX_RESPONSE_BYTES = 512 * 1024
MAX_REQUEST_BYTES = 96 * 1024
MAX_TXT_CHARACTER_STRING_BYTES = 255
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=6, connect=3, sock_connect=3, sock_read=4)
_HEX_ID_PATTERN = "^[0-9a-f]{32}$"
_STATUS_PATTERN = "^[a-z][a-z0-9_-]{0,31}$"
_HEX_ID = re.compile(_HEX_ID_PATTERN)
_STATUS = re.compile(_STATUS_PATTERN)

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
WritableDnsType = Literal["A", "AAAA", "CNAME", "TXT"]
_DNS_TYPES = frozenset(get_args(DnsType))
_WRITABLE_DNS_TYPES = frozenset(get_args(WritableDnsType))
_ZONE_TYPES = frozenset(get_args(ZoneType))

Page = Annotated[int, "Cloudflare result page, starting at 1.", {"minimum": 1, "maximum": 100_000}]
PerPage = Annotated[int, "Number of results to return, from 1 to 100.", {"minimum": 1, "maximum": 100}]
CloudflareId = Annotated[str, "The 32-character hexadecimal Cloudflare zone id.", {"pattern": _HEX_ID_PATTERN}]
ZoneName = Annotated[str, {"minLength": 1, "maxLength": 255}]
AccountName = Annotated[str, {"minLength": 1, "maxLength": 160}]
ZoneStatus = Annotated[str, {"pattern": _STATUS_PATTERN}]
DnsContent = Annotated[str, {"minLength": 1, "maxLength": 65_535}]
DnsTtl = Annotated[int, {"minimum": 1, "maximum": 2_147_483_647}]
WritableDnsTtl = Annotated[int, "Use 1 for automatic TTL or 60–86400 seconds.", {"minimum": 1, "maximum": 86_400}]
WritableDnsName = Annotated[str, "Complete DNS record name in ASCII or Punycode.", {"minLength": 1, "maxLength": 253}]
WritableDnsContent = Annotated[
    str,
    "DNS record content for the selected record type; TXT must be plain unquoted text up to 255 UTF-8 bytes.",
    {"minLength": 1, "maxLength": 255},
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


class EnsureDnsRecordResult(TypedDict):
    record: DnsRecord
    created: bool


class DeleteDnsRecordResult(TypedDict):
    record_id: CloudflareId
    deleted: bool


class CloudflareApiError(RuntimeError):
    """Cloudflare did not satisfy the declared Power contract."""


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

    async def get_zone(self, zone_id: str, access_token: str) -> Zone:
        payload = await self._get(
            f"/client/v4/zones/{quote(zone_id, safe='')}",
            access_token,
            {},
        )
        return _zone(_object_result(payload))

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

    async def get_dns_record(self, zone_id: str, record_id: str, access_token: str) -> DnsRecord:
        payload = await self._get(
            f"/client/v4/zones/{quote(zone_id, safe='')}/dns_records/{quote(record_id, safe='')}",
            access_token,
            {},
        )
        return _dns_record(_object_result(payload))

    async def ensure_dns_record(
        self,
        zone_id: str,
        record_type: str,
        name: str,
        content: str,
        ttl: int,
        proxied: bool,
        access_token: str,
    ) -> EnsureDnsRecordResult:
        desired = _write_record(record_type, name, content, ttl, proxied)
        payload = await self._get(
            f"/client/v4/zones/{quote(zone_id, safe='')}/dns_records",
            access_token,
            {
                "type": desired["type"],
                "name": desired["name"],
                "content": desired["content"],
                "page": "1",
                "per_page": "100",
            },
        )
        items = _result(payload, 100)
        pagination = _pagination(payload, 1, 100, len(items))
        if pagination["total_count"] != len(items) or pagination["total_pages"] > 1:
            raise CloudflareApiError("Cloudflare DNS record lookup is truncated")
        matches = sorted(
            (
                record
                for item in items
                if _record_matches(record := _dns_record(item), desired)
            ),
            key=lambda record: record["id"],
        )
        if matches:
            return {"record": matches[0], "created": False}
        created = await self._write(
            "POST",
            f"/client/v4/zones/{quote(zone_id, safe='')}/dns_records",
            access_token,
            desired,
        )
        record = _dns_record(_object_result(created))
        if not _record_matches(record, desired):
            raise CloudflareApiError("Cloudflare DNS record result is invalid")
        return {"record": record, "created": True}

    async def replace_dns_record(
        self,
        zone_id: str,
        record_id: str,
        record_type: str,
        name: str,
        content: str,
        ttl: int,
        proxied: bool,
        access_token: str,
    ) -> DnsRecord:
        desired = _write_record(record_type, name, content, ttl, proxied)
        payload = await self._write(
            "PUT",
            f"/client/v4/zones/{quote(zone_id, safe='')}/dns_records/{quote(record_id, safe='')}",
            access_token,
            desired,
        )
        record = _dns_record(_object_result(payload))
        if record["id"] != record_id or not _record_matches(record, desired):
            raise CloudflareApiError("Cloudflare DNS record result is invalid")
        return record

    async def delete_dns_record(
        self,
        zone_id: str,
        record_id: str,
        access_token: str,
    ) -> DeleteDnsRecordResult:
        path = f"/client/v4/zones/{quote(zone_id, safe='')}/dns_records/{quote(record_id, safe='')}"
        existing = await self._request("GET", path, access_token, {}, absent_ok=True)
        if existing is None:
            return {"record_id": record_id, "deleted": False}
        if existing.get("success") is not True:
            raise CloudflareApiError("Cloudflare response is invalid")
        record = _dns_record(_object_result(existing))
        if record["id"] != record_id:
            raise CloudflareApiError("Cloudflare DNS record result is invalid")
        deleted = await self._request("DELETE", path, access_token, {})
        if deleted is None or _deleted_id(deleted) != record_id:
            raise CloudflareApiError("Cloudflare DNS deletion result is invalid")
        return {"record_id": record_id, "deleted": True}

    async def _get(self, path: str, access_token: str, params: Mapping[str, str]) -> dict[str, Any]:
        payload = await self._request("GET", path, access_token, params)
        if payload is None or payload.get("success") is not True:
            raise CloudflareApiError("Cloudflare response is invalid")
        return payload

    async def _write(
        self,
        method: str,
        path: str,
        access_token: str,
        body: Mapping[str, object],
    ) -> dict[str, Any]:
        encoded = json.dumps(body, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        if not 1 <= len(encoded) <= MAX_REQUEST_BYTES:
            raise CloudflareApiError("Cloudflare request size is invalid")
        payload = await self._request(method, path, access_token, {}, body=encoded)
        if payload is None or payload.get("success") is not True:
            raise CloudflareApiError("Cloudflare response is invalid")
        return payload

    async def _request(
        self,
        method: str,
        path: str,
        access_token: str,
        params: Mapping[str, str],
        *,
        body: bytes | None = None,
        absent_ok: bool = False,
    ) -> dict[str, Any] | None:
        if method not in {"DELETE", "GET", "POST", "PUT"}:
            raise CloudflareApiError("undeclared Cloudflare method")
        if not path.startswith("/client/v4/") or "?" in path or "#" in path:
            raise CloudflareApiError("undeclared Cloudflare endpoint")
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Authorization": f"Bearer {access_token}",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            async with self._session.request(
                method,
                f"{CLOUDFLARE_API_ORIGIN}{path}",
                headers=headers,
                params=params,
                data=body,
                allow_redirects=False,
            ) as response:
                if absent_ok and response.status == 404:
                    return None
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
        if not isinstance(payload, dict):
            raise CloudflareApiError("Cloudflare response is invalid")
        return payload


def create_http_session() -> aiohttp.ClientSession:
    session = aiohttp.ClientSession(
        auto_decompress=False,
        timeout=HTTP_TIMEOUT,
        trust_env=True,
        headers={"User-Agent": "shimpz-cloudflare/0.4.0"},
    )
    session._retry_connection = False
    return session


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


def _object_result(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise CloudflareApiError("Cloudflare result is invalid")
    return result


def _deleted_id(payload: Mapping[str, Any]) -> str:
    result = _object_result(payload)
    return _id(result.get("id"))


def _write_record(record_type: str, name: str, content: str, ttl: int, proxied: bool) -> dict[str, object]:
    if record_type not in _WRITABLE_DNS_TYPES:
        raise CloudflareApiError("Cloudflare DNS record type is invalid")
    normalized_name = _dns_name(name)
    normalized_content = _dns_content(record_type, content, normalized_name)
    if type(ttl) is not int or (ttl != 1 and not 60 <= ttl <= 86_400):
        raise CloudflareApiError("Cloudflare DNS record TTL is invalid")
    if type(proxied) is not bool or (proxied and (record_type == "TXT" or ttl != 1)):
        raise CloudflareApiError("Cloudflare DNS proxy mode is invalid")
    return {
        "type": record_type,
        "name": normalized_name,
        "content": normalized_content,
        "ttl": ttl,
        "proxied": proxied,
    }


def _dns_name(value: object) -> str:
    name = _text(value, 253)
    if not name.isascii() or name != name.lower() or name.startswith(".") or name.endswith(".") or ".." in name:
        raise CloudflareApiError("Cloudflare DNS record name is invalid")
    labels = name.split(".")
    if any(
        len(label) > 63
        or re.fullmatch(r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?", label) is None
        for label in labels
    ):
        raise CloudflareApiError("Cloudflare DNS record name is invalid")
    return name


def _dns_content(record_type: str, value: object, name: str) -> str:
    content = _text(value, 255)
    if record_type == "A":
        try:
            return str(ipaddress.IPv4Address(content))
        except ipaddress.AddressValueError as exc:
            raise CloudflareApiError("Cloudflare DNS record content is invalid") from exc
    if record_type == "AAAA":
        try:
            return str(ipaddress.IPv6Address(content))
        except ipaddress.AddressValueError as exc:
            raise CloudflareApiError("Cloudflare DNS record content is invalid") from exc
    if record_type == "CNAME":
        target = _dns_name(content)
        if target == name:
            raise CloudflareApiError("Cloudflare DNS record content is invalid")
        return target
    if '"' in content or "\\" in content or len(content.encode("utf-8")) > MAX_TXT_CHARACTER_STRING_BYTES:
        raise CloudflareApiError("Cloudflare DNS record content is invalid")
    return f'"{content}"'


def _record_matches(record: DnsRecord, desired: Mapping[str, object]) -> bool:
    return all(record[key] == desired[key] for key in ("type", "name", "content", "ttl", "proxied"))


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
