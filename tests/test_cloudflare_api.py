from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import patch

from shimpz import Context

from lib.cloudflare import (
    MAX_RESPONSE_BYTES,
    CloudflareApiClient,
    CloudflareApiError,
)
from powers.get_dns_record import run as get_dns_record
from powers.get_zone import run as get_zone
from powers.list_dns_records import run as list_dns_records
from powers.list_zones import run as list_zones

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
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.requests.append((url, kwargs))
        return self.responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


def _page(result: list[object]) -> dict[str, object]:
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": result,
        "result_info": {"page": 1, "per_page": 25, "count": len(result), "total_count": len(result), "total_pages": 1},
    }


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
                self.assertNotIn(TEST_ACCESS_VALUE, str(caught.exception))

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
