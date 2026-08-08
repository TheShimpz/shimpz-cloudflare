from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from shimpz import Context

from lib.cloudflare import (
    MAX_RESPONSE_BYTES,
    CloudflareApiClient,
    CloudflareApiError,
    create_http_session,
)
from powers.delete_dns_record import run as delete_dns_record
from powers.ensure_dns_record import run as ensure_dns_record
from powers.get_dns_record import run as get_dns_record
from powers.get_zone import run as get_zone
from powers.list_dns_records import run as list_dns_records
from powers.list_zones import run as list_zones
from powers.replace_dns_record import run as replace_dns_record

ZONE_ID = "a" * 32
ACCOUNT_ID = "b" * 32
RECORD_ID = "c" * 32
TEST_ACCESS_VALUE = "opaque-access-token"


class _Content:
    def __init__(self, raw: bytes, chunk_size: int | None = None) -> None:
        self.raw = raw
        self.chunk_size = chunk_size
        self.offset = 0

    async def read(self, size: int) -> bytes:
        limit = size if self.chunk_size is None else min(size, self.chunk_size)
        chunk = self.raw[self.offset : self.offset + limit]
        self.offset += len(chunk)
        return chunk


class _Response:
    def __init__(
        self,
        payload: object,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        chunk_size: int | None = None,
    ) -> None:
        self.raw = payload if isinstance(payload, bytes) else json.dumps(payload, separators=(",", ":")).encode()
        self.status = status
        self.headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(self.raw)),
            **(headers or {}),
        }
        self.content = _Content(self.raw, chunk_size)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Session:
    def __init__(self, responses: list[_Response], events: list[str] | None = None) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.events = events

    def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        self.requests.append((url, {"method": method, **kwargs}))
        if self.events is not None:
            self.events.append(f"provider:{method}")
        return self.responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


def _page(result: list[object], *, per_page: int = 25) -> dict[str, object]:
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": result,
        "result_info": {
            "page": 1,
            "per_page": per_page,
            "count": len(result),
            "total_count": len(result),
            "total_pages": 1,
        },
    }


def _record(
    *,
    record_id: str = RECORD_ID,
    record_type: str = "A",
    name: str = "api.shimpz.com",
    content: str = "192.0.2.1",
    ttl: int = 1,
    proxied: bool = True,
) -> dict[str, object]:
    return {
        "id": record_id,
        "type": record_type,
        "name": name,
        "content": content,
        "ttl": ttl,
        "proxied": proxied,
        "proxiable": record_type in {"A", "AAAA", "CNAME"},
    }


class _PowerContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.integrations = SimpleNamespace(cloudflare=self)

    def request_approval(self, *, title: str, description: str) -> None:
        self.assert_public_copy(title, description)
        self.events.append("approval")

    def request_auth(self, assurance: str, *, title: str, description: str) -> None:
        if assurance != "reauth":
            raise AssertionError("unexpected assurance")
        self.assert_public_copy(title, description)
        self.events.append("auth:reauth")

    @property
    def access_token(self) -> str:
        self.events.append("token")
        return TEST_ACCESS_VALUE

    @staticmethod
    def assert_public_copy(title: str, description: str) -> None:
        if TEST_ACCESS_VALUE in title or TEST_ACCESS_VALUE in description:
            raise AssertionError("token leaked into request copy")


class CloudflareApiClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_powers_read_the_invocation_scoped_cloudflare_account(self) -> None:
        zone = {
            "id": ZONE_ID,
            "name": "shimpz.com",
            "status": "active",
            "type": "full",
            "paused": False,
            "account": {"id": ACCOUNT_ID, "name": "Shimpz"},
        }
        record = {
            "id": RECORD_ID,
            "type": "A",
            "name": "shimpz.com",
            "content": "192.0.2.1",
            "ttl": 1,
            "proxied": True,
            "proxiable": True,
        }
        session = _Session(
            [
                _Response(_page([])),
                _Response({"success": True, "result": zone}),
                _Response(_page([])),
                _Response({"success": True, "result": record}),
            ]
        )
        context = Context({"cloudflare": TEST_ACCESS_VALUE})

        with (
            patch("powers.list_zones.create_http_session", return_value=session),
            patch("powers.get_zone.create_http_session", return_value=session),
            patch("powers.list_dns_records.create_http_session", return_value=session),
            patch("powers.get_dns_record.create_http_session", return_value=session),
        ):
            zones = await list_zones(1, 25, ctx=context)
            selected_zone = await get_zone(ZONE_ID, ctx=context)
            records = await list_dns_records(ZONE_ID, 1, 25, ctx=context)
            selected_record = await get_dns_record(ZONE_ID, RECORD_ID, ctx=context)

        self.assertEqual(zones["zones"], [])
        self.assertEqual(selected_zone["id"], ZONE_ID)
        self.assertEqual(records["records"], [])
        self.assertEqual(selected_record["id"], RECORD_ID)
        for _url, kwargs in session.requests:
            self.assertEqual(kwargs["method"], "GET")
            self.assertEqual(
                kwargs["headers"]["Authorization"],
                f"Bearer {TEST_ACCESS_VALUE}",
            )

    async def test_lists_zones_and_dns_through_exact_read_only_endpoints(self) -> None:
        session = _Session(
            [
                _Response(
                    _page(
                        [
                            {
                                "id": ZONE_ID,
                                "name": "shimpz.com",
                                "status": "active",
                                "type": "full",
                                "paused": False,
                                "account": {"id": ACCOUNT_ID, "name": "Shimpz"},
                                "ignored": "provider detail",
                            }
                        ]
                    )
                ),
                _Response(
                    _page(
                        [
                            {
                                "id": RECORD_ID,
                                "type": "A",
                                "name": "shimpz.com",
                                "content": "192.0.2.1",
                                "ttl": 1,
                                "proxied": True,
                                "proxiable": True,
                                "ignored": "provider detail",
                            }
                        ]
                    )
                ),
            ]
        )
        client = CloudflareApiClient(session)  # type: ignore[arg-type]

        zones = await client.list_zones(1, 25, TEST_ACCESS_VALUE)
        records = await client.list_dns_records(ZONE_ID, 1, 25, TEST_ACCESS_VALUE)

        self.assertEqual(zones["zones"][0]["name"], "shimpz.com")
        self.assertNotIn("ignored", zones["zones"][0])
        self.assertEqual(records["records"][0]["content"], "192.0.2.1")
        self.assertNotIn("ignored", records["records"][0])
        self.assertEqual(
            [url for url, _kwargs in session.requests],
            [
                "https://api.cloudflare.com/client/v4/zones",
                f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            ],
        )
        for _url, kwargs in session.requests:
            self.assertEqual(kwargs["method"], "GET")
            self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {TEST_ACCESS_VALUE}")
            self.assertEqual(kwargs["headers"]["Accept-Encoding"], "identity")
            self.assertIs(kwargs["allow_redirects"], False)
            self.assertEqual(kwargs["params"]["order"], "name")

    async def test_gets_zone_and_dns_record_through_exact_read_only_endpoints(self) -> None:
        zone = {
            "id": ZONE_ID,
            "name": "shimpz.com",
            "status": "active",
            "type": "full",
            "paused": False,
            "account": {"id": ACCOUNT_ID, "name": "Shimpz"},
        }
        record = {
            "id": RECORD_ID,
            "type": "TXT",
            "name": "_proof.shimpz.com",
            "content": "proof",
            "ttl": 300,
            "proxied": False,
            "proxiable": False,
        }
        session = _Session(
            [
                _Response({"success": True, "result": zone}),
                _Response({"success": True, "result": record}),
            ]
        )
        client = CloudflareApiClient(session)  # type: ignore[arg-type]

        self.assertEqual((await client.get_zone(ZONE_ID, TEST_ACCESS_VALUE))["id"], ZONE_ID)
        self.assertEqual(
            (await client.get_dns_record(ZONE_ID, RECORD_ID, TEST_ACCESS_VALUE))["id"],
            RECORD_ID,
        )
        self.assertEqual(
            [url for url, _kwargs in session.requests],
            [
                f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}",
                f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{RECORD_ID}",
            ],
        )
        self.assertTrue(all(kwargs["params"] == {} for _url, kwargs in session.requests))

    async def test_ensure_returns_an_exact_existing_record_without_post(self) -> None:
        session = _Session([_Response(_page([_record()], per_page=100))])
        client = CloudflareApiClient(session)  # type: ignore[arg-type]

        result = await client.ensure_dns_record(
            ZONE_ID,
            "A",
            "api.shimpz.com",
            "192.0.2.1",
            1,
            True,
            TEST_ACCESS_VALUE,
        )

        self.assertFalse(result["created"])
        self.assertEqual(result["record"]["id"], RECORD_ID)
        self.assertEqual([kwargs["method"] for _url, kwargs in session.requests], ["GET"])
        self.assertEqual(
            session.requests[0][1]["params"],
            {"type": "A", "name": "api.shimpz.com", "content": "192.0.2.1", "page": "1", "per_page": "100"},
        )

    async def test_ensure_creates_an_absent_record_once_with_canonical_json(self) -> None:
        session = _Session(
            [
                _Response(_page([], per_page=100)),
                _Response({"success": True, "result": _record()}),
            ]
        )
        client = CloudflareApiClient(session)  # type: ignore[arg-type]

        result = await client.ensure_dns_record(
            ZONE_ID,
            "A",
            "api.shimpz.com",
            "192.0.2.1",
            1,
            True,
            TEST_ACCESS_VALUE,
        )

        self.assertTrue(result["created"])
        self.assertEqual([kwargs["method"] for _url, kwargs in session.requests], ["GET", "POST"])
        self.assertEqual(
            json.loads(session.requests[1][1]["data"]),
            {"type": "A", "name": "api.shimpz.com", "content": "192.0.2.1", "ttl": 1, "proxied": True},
        )
        self.assertEqual(session.requests[1][1]["headers"]["Content-Type"], "application/json")

    async def test_ensure_canonicalizes_plain_txt_before_lookup_and_create(self) -> None:
        canonical = _record(
            record_type="TXT",
            name="_proof.shimpz.com",
            content='"proof"',
            ttl=300,
            proxied=False,
        )
        session = _Session(
            [
                _Response(_page([], per_page=100)),
                _Response({"success": True, "result": canonical}),
            ]
        )

        result = await CloudflareApiClient(session).ensure_dns_record(  # type: ignore[arg-type]
            ZONE_ID,
            "TXT",
            "_proof.shimpz.com",
            "proof",
            300,
            False,
            TEST_ACCESS_VALUE,
        )

        self.assertTrue(result["created"])
        self.assertEqual(session.requests[0][1]["params"]["content"], '"proof"')
        self.assertEqual(json.loads(session.requests[1][1]["data"])["content"], '"proof"')

    async def test_ensure_reuses_a_canonical_txt_record_without_post(self) -> None:
        existing = _record(
            record_type="TXT",
            name="_proof.shimpz.com",
            content='"proof"',
            ttl=300,
            proxied=False,
        )
        session = _Session([_Response(_page([existing], per_page=100))])

        result = await CloudflareApiClient(session).ensure_dns_record(  # type: ignore[arg-type]
            ZONE_ID,
            "TXT",
            "_proof.shimpz.com",
            "proof",
            300,
            False,
            TEST_ACCESS_VALUE,
        )

        self.assertFalse(result["created"])
        self.assertEqual([kwargs["method"] for _url, kwargs in session.requests], ["GET"])

    async def test_ensure_refuses_a_truncated_filtered_lookup_before_post(self) -> None:
        truncated = _page([], per_page=100)
        truncated["result_info"] = {
            "page": 1,
            "per_page": 100,
            "count": 0,
            "total_count": 101,
            "total_pages": 2,
        }
        session = _Session([_Response(truncated)])

        with self.assertRaisesRegex(CloudflareApiError, "truncated"):
            await CloudflareApiClient(session).ensure_dns_record(  # type: ignore[arg-type]
                ZONE_ID,
                "A",
                "api.shimpz.com",
                "192.0.2.1",
                1,
                True,
                TEST_ACCESS_VALUE,
            )

        self.assertEqual([kwargs["method"] for _url, kwargs in session.requests], ["GET"])

    async def test_replace_uses_full_put_and_rejects_result_drift(self) -> None:
        replacement = _record(
            record_type="TXT",
            name="_proof.shimpz.com",
            content='"proof"',
            ttl=300,
            proxied=False,
        )
        session = _Session([_Response({"success": True, "result": replacement})])
        client = CloudflareApiClient(session)  # type: ignore[arg-type]

        result = await client.replace_dns_record(
            ZONE_ID,
            RECORD_ID,
            "TXT",
            "_proof.shimpz.com",
            "proof",
            300,
            False,
            TEST_ACCESS_VALUE,
        )

        self.assertEqual(result["id"], RECORD_ID)
        self.assertEqual(session.requests[0][1]["method"], "PUT")
        self.assertEqual(
            session.requests[0][0],
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{RECORD_ID}",
        )
        self.assertEqual(json.loads(session.requests[0][1]["data"])["content"], '"proof"')
        drifted = _Session([_Response({"success": True, "result": {**replacement, "content": "changed"}})])
        with self.assertRaises(CloudflareApiError):
            await CloudflareApiClient(drifted).replace_dns_record(  # type: ignore[arg-type]
                ZONE_ID,
                RECORD_ID,
                "TXT",
                "_proof.shimpz.com",
                "proof",
                300,
                False,
                TEST_ACCESS_VALUE,
            )

    async def test_delete_reconciles_absence_and_deletes_an_existing_exact_record(self) -> None:
        absent = _Session([_Response({}, status=404)])
        self.assertEqual(
            await CloudflareApiClient(absent).delete_dns_record(ZONE_ID, RECORD_ID, TEST_ACCESS_VALUE),  # type: ignore[arg-type]
            {"record_id": RECORD_ID, "deleted": False},
        )
        self.assertEqual([kwargs["method"] for _url, kwargs in absent.requests], ["GET"])

        existing = _Session(
            [
                _Response({"success": True, "result": _record()}),
                _Response({"result": {"id": RECORD_ID}}),
            ]
        )
        self.assertEqual(
            await CloudflareApiClient(existing).delete_dns_record(ZONE_ID, RECORD_ID, TEST_ACCESS_VALUE),  # type: ignore[arg-type]
            {"record_id": RECORD_ID, "deleted": True},
        )
        self.assertEqual([kwargs["method"] for _url, kwargs in existing.requests], ["GET", "DELETE"])

        invalid = _Session([_Response({"success": False, "result": _record()})])
        with self.assertRaises(CloudflareApiError):
            await CloudflareApiClient(invalid).delete_dns_record(  # type: ignore[arg-type]
                ZONE_ID,
                RECORD_ID,
                TEST_ACCESS_VALUE,
            )
        self.assertEqual([kwargs["method"] for _url, kwargs in invalid.requests], ["GET"])

    async def test_write_inputs_are_closed_before_provider_io(self) -> None:
        invalid = (
            ("MX", "mail.shimpz.com", "mailhost.shimpz.com", 300, False),
            ("A", "Api.shimpz.com", "192.0.2.1", 300, False),
            ("A", "api.shimpz.com", "not-an-address", 300, False),
            ("AAAA", "api.shimpz.com", "192.0.2.1", 300, False),
            ("CNAME", "api.shimpz.com", "api.shimpz.com", 300, False),
            ("TXT", "_proof.shimpz.com", "proof", 1, True),
            ("TXT", "_proof.shimpz.com", 'bad"quote', 300, False),
            ("TXT", "_proof.shimpz.com", "bad\\escape", 300, False),
            ("TXT", "_proof.shimpz.com", "é", 300, False),
            ("A", "api.shimpz.com", "192.0.2.1", 30, False),
            ("A", "api.shimpz.com", "192.0.2.1", 300, True),
        )
        for values in invalid:
            session = _Session([])
            with self.subTest(values=values), self.assertRaises(CloudflareApiError):
                await CloudflareApiClient(session).ensure_dns_record(  # type: ignore[arg-type]
                    ZONE_ID,
                    *values,
                    TEST_ACCESS_VALUE,
                )
            self.assertEqual(session.requests, [])

    async def test_mutation_powers_request_approval_and_reauth_before_token_and_provider(self) -> None:
        scenarios = (
            (
                ensure_dns_record,
                (ZONE_ID, "A", "api.shimpz.com", "192.0.2.1", 1, True),
                [_Response(_page([_record()], per_page=100))],
                "powers.ensure_dns_record.create_http_session",
                "GET",
            ),
            (
                replace_dns_record,
                (ZONE_ID, RECORD_ID, "A", "api.shimpz.com", "192.0.2.1", 1, True),
                [_Response({"success": True, "result": _record()})],
                "powers.replace_dns_record.create_http_session",
                "PUT",
            ),
            (
                delete_dns_record,
                (ZONE_ID, RECORD_ID),
                [_Response({}, status=404)],
                "powers.delete_dns_record.create_http_session",
                "GET",
            ),
        )
        for power_body, arguments, responses, session_patch, provider_method in scenarios:
            events: list[str] = []
            session = _Session(responses, events)
            with self.subTest(power=power_body.__module__), patch(session_patch, return_value=session):
                await power_body(*arguments, ctx=_PowerContext(events))  # type: ignore[arg-type]
            self.assertEqual(events[:4], ["approval", "auth:reauth", "token", f"provider:{provider_method}"])

    async def test_http_session_disables_aiohttp_connection_retries(self) -> None:
        session = create_http_session()
        self.addAsyncCleanup(session.close)
        self.assertFalse(session._retry_connection)

    async def test_authentication_and_provider_failures_never_reflect_token(self) -> None:
        for response, error in (
            (_Response({}, status=401), CloudflareApiError),
            (_Response({}, status=403), CloudflareApiError),
            (_Response({}, status=302, headers={"Location": "https://evil.example"}), CloudflareApiError),
        ):
            with self.subTest(status=response.status):
                client = CloudflareApiClient(_Session([response]))  # type: ignore[arg-type]
                with self.assertRaises(error) as caught:
                    await client.list_zones(1, 25, TEST_ACCESS_VALUE)
                self.assertIs(type(caught.exception), error)
                failure: BaseException | None = caught.exception
                while failure is not None:
                    self.assertNotIn(TEST_ACCESS_VALUE, str(failure))
                    failure = failure.__cause__

    async def test_reassembles_a_bounded_chunked_provider_response(self) -> None:
        response = _Response(_page([]), chunk_size=7)
        response.headers.pop("Content-Length")
        client = CloudflareApiClient(_Session([response]))  # type: ignore[arg-type]

        result = await client.list_zones(1, 25, TEST_ACCESS_VALUE)

        self.assertEqual(result["zones"], [])
        self.assertEqual(result["pagination"]["count"], 0)

    async def test_malformed_duplicate_oversized_and_unbounded_results_fail_closed(self) -> None:
        bad = (
            _Response(b'{"success":true,"success":true}'),
            _Response(b"[]"),
            _Response(b"x" * (MAX_RESPONSE_BYTES + 1)),
            _Response(_page([{}])),
            _Response(
                {
                    **_page([]),
                    "result_info": {"page": 2, "per_page": 25, "count": 0, "total_count": 0, "total_pages": 0},
                }
            ),
        )
        for index, response in enumerate(bad):
            with self.subTest(index=index):
                client = CloudflareApiClient(_Session([response]))  # type: ignore[arg-type]
                with self.assertRaises(CloudflareApiError):
                    await client.list_zones(1, 25, TEST_ACCESS_VALUE)


if __name__ == "__main__":
    unittest.main()
