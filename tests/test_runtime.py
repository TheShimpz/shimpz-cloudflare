from __future__ import annotations

import unittest

from aiohttp.test_utils import TestClient, TestServer

from assistant import PrivateEnvelopeError, validate_power_envelope, validate_power_input
from assistant.cloudflare_api import CloudflareApiError, CloudflareReauthorizationRequiredError
from assistant.main import create_app

TEST_ACCESS_VALUE = "opaque-access-token"
ZONE_ID = "a" * 32


def _envelope(power_input: dict[str, object]) -> dict[str, object]:
    return {
        "input": power_input,
        "secrets": {},
        "accounts": {"cloudflare": {"type": "oauth2-bearer", "access_token": TEST_ACCESS_VALUE}},
    }


class _CloudflareClient:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.failure: Exception | None = None

    async def list_zones(self, page: int, per_page: int, token: str):
        if self.failure:
            raise self.failure
        self.calls.append(("zones", page, per_page, token))
        return {
            "zones": [],
            "pagination": {"page": page, "per_page": per_page, "count": 0, "total_count": 0, "total_pages": 0},
        }

    async def list_dns_records(self, zone_id: str, page: int, per_page: int, token: str):
        if self.failure:
            raise self.failure
        self.calls.append(("dns", zone_id, page, per_page, token))
        return {
            "records": [],
            "pagination": {"page": page, "per_page": per_page, "count": 0, "total_count": 0, "total_pages": 0},
        }


class PrivateContractTests(unittest.TestCase):
    def test_requires_exact_cloudflare_account_envelope_and_bounded_inputs(self) -> None:
        envelope = validate_power_envelope(_envelope({"page": 1, "per_page": 25}), "list-zones")
        self.assertEqual(envelope.access_token, TEST_ACCESS_VALUE)
        validate_power_input("list-zones", envelope.input)
        validate_power_input("list-dns-records", {"zone_id": ZONE_ID, "page": 1, "per_page": 100})

        invalid = (
            {**_envelope({}), "secrets": {"token": "must-not-cross"}},
            {**_envelope({}), "accounts": {}},
            {**_envelope({}), "accounts": {"cloudflare": {"type": "oauth2-bearer", "access_token": "short"}}},
        )
        for payload in invalid:
            with self.assertRaises(PrivateEnvelopeError):
                validate_power_envelope(payload, "list-zones")
        for payload in (
            {"page": 0, "per_page": 25},
            {"page": 1, "per_page": 101},
            {"zone_id": "not-an-id", "page": 1, "per_page": 25},
        ):
            with self.assertRaises(ValueError):
                validate_power_input("list-dns-records" if "zone_id" in payload else "list-zones", payload)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.cloudflare = _CloudflareClient()
        self.client = TestClient(
            TestServer(
                create_app(
                    client=self.cloudflare,  # type: ignore[arg-type]
                    help_markdown={"en": "# Help", "pt": "# Ajuda"},
                )
            )
        )
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_health_help_and_both_powers(self) -> None:
        health = await self.client.get("/health")
        self.assertEqual(await health.json(), {"status": "ok"})
        help_response = await self.client.get("/v1/help/pt")
        self.assertEqual(await help_response.json(), {"markdown": "# Ajuda"})

        zones = await self.client.post("/v1/powers/list-zones", json=_envelope({"page": 1, "per_page": 25}))
        dns = await self.client.post(
            "/v1/powers/list-dns-records",
            json=_envelope({"zone_id": ZONE_ID, "page": 1, "per_page": 50}),
        )
        self.assertEqual(zones.status, 200)
        self.assertEqual(dns.status, 200)
        self.assertEqual(
            self.cloudflare.calls,
            [
                ("zones", 1, 25, TEST_ACCESS_VALUE),
                ("dns", ZONE_ID, 1, 50, TEST_ACCESS_VALUE),
            ],
        )

    async def test_invalid_private_input_and_provider_failures_are_stable(self) -> None:
        invalid = await self.client.post("/v1/powers/list-zones", json={"input": {}, "secrets": {}, "accounts": {}})
        self.assertEqual(invalid.status, 400)
        self.assertEqual(await invalid.json(), {"error": "invalid_input"})

        self.cloudflare.failure = CloudflareReauthorizationRequiredError("private")
        auth = await self.client.post("/v1/powers/list-zones", json=_envelope({"page": 1, "per_page": 25}))
        self.assertEqual(auth.status, 409)
        self.assertEqual(await auth.json(), {"error": "cloudflare_reauthorization_required"})

        self.cloudflare.failure = CloudflareApiError("private")
        provider = await self.client.post("/v1/powers/list-zones", json=_envelope({"page": 1, "per_page": 25}))
        self.assertEqual(provider.status, 502)
        self.assertEqual(await provider.json(), {"error": "cloudflare_provider_unavailable"})


if __name__ == "__main__":
    unittest.main()
