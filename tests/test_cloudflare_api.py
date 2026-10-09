from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from shimpz import FetchError, Response, Text

from actions.delete_dns_record import run as delete_dns_record
from actions.ensure_dns_record import run as ensure_dns_record
from actions.get_dns_record import run as get_dns_record
from actions.get_zone import run as get_zone
from actions.list_dns_records import run as list_dns_records
from actions.list_zones import run as list_zones
from actions.replace_dns_record import run as replace_dns_record
from lib.cloudflare import (
    MAX_RESPONSE_BYTES,
    CloudflareApiClient,
    CloudflareApiError,
)

ZONE_ID = "a" * 32
ACCOUNT_ID = "b" * 32
RECORD_ID = "c" * 32


class _Response:
    """One queued answer: Cloudflare's response, or the Team's closed error when ``error`` is set."""

    def __init__(
        self,
        payload: object,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        error: str | None = None,
    ) -> None:
        self.raw = payload if isinstance(payload, bytes) else json.dumps(payload, separators=(",", ":")).encode()
        self.status = status
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.error = error


class _Session:
    """Records every Team-made call and answers from a queue."""

    def __init__(self, responses: list[_Response], events: list[str] | None = None) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.events = events

    async def fetch(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] = (),
        body: str | None = None,
        timeout_ms: int | None = None,
    ) -> Response:
        parts = urlsplit(url)
        self.requests.append(
            (
                f"{parts.scheme}://{parts.netloc}{parts.path}",
                {
                    "method": method,
                    "headers": dict(headers),
                    "params": dict(parse_qsl(parts.query)),
                    "data": body,
                    "timeout_ms": timeout_ms,
                },
            )
        )
        if self.events is not None:
            self.events.append(f"provider:{method}")
        answer = self.responses.pop(0)
        if answer.error is not None:
            raise FetchError(answer.error)
        return Response(answer.status, tuple(answer.headers.items()), answer.raw)


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


class _ActionContext:
    def __init__(self, events: list[str], session: _Session) -> None:
        self.events = events
        self.session = session

    async def fetch(self, method: str, url: str, **options: Any) -> Response:
        return await self.session.fetch(method, url, **options)

    def request_auth(self, authentication: str, *, title: Text, description: Text) -> None:
        if authentication != "password":
            raise AssertionError("unexpected authentication mechanism")
        if not isinstance(title, Text) or not isinstance(description, Text):
            raise AssertionError("authentication copy is not catalog copy")
        if title.template != "Confirm with your Shimpz Supervisor password":
            raise AssertionError("authentication title does not identify the Shimpz Supervisor password")
        if not description.template.startswith("Enter your current Shimpz Supervisor password before "):
            raise AssertionError("authentication description does not identify the Shimpz Supervisor password")
        self.events.append("auth:password")


class CloudflareApiClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_actions_ask_the_team_for_every_call_without_a_token(self) -> None:
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
        context = _ActionContext([], session)

        zones = await list_zones(1, 25, ctx=context)  # type: ignore[arg-type]
        selected_zone = await get_zone(ZONE_ID, ctx=context)  # type: ignore[arg-type]
        records = await list_dns_records(ZONE_ID, 1, 25, ctx=context)  # type: ignore[arg-type]
        selected_record = await get_dns_record(ZONE_ID, RECORD_ID, ctx=context)  # type: ignore[arg-type]

        self.assertEqual(zones["zones"], [])
        self.assertEqual(selected_zone["id"], ZONE_ID)
        self.assertEqual(records["records"], [])
        self.assertEqual(selected_record["id"], RECORD_ID)
        for _url, kwargs in session.requests:
            self.assertEqual(kwargs["method"], "GET")
            self.assertEqual(kwargs["headers"], {"Accept": "application/json"})

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

        zones = await client.list_zones(1, 25)
        records = await client.list_dns_records(ZONE_ID, 1, 25)

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
            self.assertNotIn("Authorization", kwargs["headers"])
            self.assertEqual(kwargs["timeout_ms"], 6000)
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

        self.assertEqual((await client.get_zone(ZONE_ID))["id"], ZONE_ID)
        self.assertEqual(
            (await client.get_dns_record(ZONE_ID, RECORD_ID))["id"],
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
            )

    async def test_delete_reconciles_absence_and_deletes_an_existing_exact_record(self) -> None:
        absent = _Session([_Response({}, status=404)])
        self.assertEqual(
            await CloudflareApiClient(absent).delete_dns_record(ZONE_ID, RECORD_ID),  # type: ignore[arg-type]
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
            await CloudflareApiClient(existing).delete_dns_record(ZONE_ID, RECORD_ID),  # type: ignore[arg-type]
            {"record_id": RECORD_ID, "deleted": True},
        )
        self.assertEqual([kwargs["method"] for _url, kwargs in existing.requests], ["GET", "DELETE"])

        invalid = _Session([_Response({"success": False, "result": _record()})])
        with self.assertRaises(CloudflareApiError):
            await CloudflareApiClient(invalid).delete_dns_record(  # type: ignore[arg-type]
                ZONE_ID,
                RECORD_ID,
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
                )
            self.assertEqual(session.requests, [])

    async def test_mutation_actions_request_password_authorization_before_any_provider_call(self) -> None:
        scenarios = (
            (
                ensure_dns_record,
                (ZONE_ID, "A", "api.shimpz.com", "192.0.2.1", 1, True),
                [_Response(_page([_record()], per_page=100))],
                "GET",
            ),
            (
                replace_dns_record,
                (ZONE_ID, RECORD_ID, "A", "api.shimpz.com", "192.0.2.1", 1, True),
                [_Response({"success": True, "result": _record()})],
                "PUT",
            ),
            (
                delete_dns_record,
                (ZONE_ID, RECORD_ID),
                [_Response({}, status=404)],
                "GET",
            ),
        )
        for action_body, arguments, responses, provider_method in scenarios:
            events: list[str] = []
            session = _Session(responses, events)
            with self.subTest(action=action_body.__module__):
                await action_body(*arguments, ctx=_ActionContext(events, session))  # type: ignore[arg-type]
            self.assertEqual(events[:2], ["auth:password", f"provider:{provider_method}"])

    async def test_team_refusals_fail_closed(self) -> None:
        for code in ("refused", "credential-missing", "unavailable", "failed"):
            client = CloudflareApiClient(_Session([_Response({}, error=code)]))  # type: ignore[arg-type]
            with self.subTest(code=code), self.assertRaises(CloudflareApiError):
                await client.list_zones(1, 25)

    async def test_authentication_and_provider_failures_fail_closed(self) -> None:
        for response, error in (
            (_Response({}, status=401), CloudflareApiError),
            (_Response({}, status=403), CloudflareApiError),
            (_Response({}, status=302, headers={"Location": "https://evil.example"}), CloudflareApiError),
        ):
            with self.subTest(status=response.status):
                client = CloudflareApiClient(_Session([response]))  # type: ignore[arg-type]
                with self.assertRaises(error) as caught:
                    await client.list_zones(1, 25)
                self.assertIs(type(caught.exception), error)

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
                    await client.list_zones(1, 25)


if __name__ == "__main__":
    unittest.main()
