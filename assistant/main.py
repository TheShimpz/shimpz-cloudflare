"""Bounded HTTP server exposing two read-only Cloudflare Powers."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from assistant import PrivateEnvelopeError, load_strict_json, validate_power_envelope, validate_power_input
from assistant.cloudflare_api import (
    CloudflareApiClient,
    CloudflareApiError,
    CloudflareReauthorizationRequiredError,
)

MAX_BODY_BYTES = 8 * 1024
MAX_HELP_BYTES = 32 * 1024
HELP_LOCALES = ("en", "pt", "es", "zh", "fr", "de", "ja", "ar")
HELP_DIR = Path(__file__).resolve().parents[1] / "help"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=3, sock_connect=3, sock_read=6)
HELP_KEY = web.AppKey("help_markdown", dict[str, str])
CLIENT_KEY = web.AppKey("cloudflare_client", CloudflareApiClient)


def _read_help(path: Path) -> str:
    try:
        raw = path.read_bytes()
        markdown = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"{path.name} is unavailable") from exc
    if not 1 <= len(raw) <= MAX_HELP_BYTES or not markdown.strip():
        raise RuntimeError(f"{path.name} is outside the accepted size")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in markdown):
        raise RuntimeError(f"{path.name} contains unsafe control characters")
    return markdown


def load_help(directory: Path = HELP_DIR) -> dict[str, str]:
    localized = {"en": _read_help(directory / "HELP-en.md")}
    for locale in HELP_LOCALES[1:]:
        try:
            localized[locale] = _read_help(directory / f"HELP-{locale}.md")
        except RuntimeError:
            continue
    return localized


@web.middleware
async def _json_errors(request: web.Request, handler: Any) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPRequestEntityTooLarge:
        return _error(400, "invalid_input")
    except web.HTTPNotFound:
        return _error(404, "not_found")


def create_http_session() -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(limit=16, limit_per_host=16, ttl_dns_cache=60)
    return aiohttp.ClientSession(
        auto_decompress=False,
        connector=connector,
        timeout=HTTP_TIMEOUT,
        trust_env=True,
        headers={"User-Agent": "shimpz-cloudflare/0.1.1"},
    )


async def _runtime_context(app: web.Application) -> AsyncIterator[None]:
    async with create_http_session() as session:
        if CLIENT_KEY not in app:
            app[CLIENT_KEY] = CloudflareApiClient(session)
        yield


def create_app(
    *,
    client: CloudflareApiClient | None = None,
    help_markdown: Mapping[str, str] | None = None,
) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY_BYTES, middlewares=[_json_errors])
    app[HELP_KEY] = load_help() if help_markdown is None else dict(help_markdown)
    if client is not None:
        app[CLIENT_KEY] = client
    else:
        app.cleanup_ctx.append(_runtime_context)
    app.router.add_get("/health", _health)
    app.router.add_get("/v1/help", _help)
    app.router.add_get(f"/v1/help/{{locale:{'|'.join(HELP_LOCALES)}}}", _help)
    app.router.add_post("/v1/powers/list-zones", _list_zones)
    app.router.add_post("/v1/powers/list-dns-records", _list_dns_records)
    return app


async def _health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _help(request: web.Request) -> web.Response:
    localized = request.app[HELP_KEY]
    locale = request.match_info.get("locale", "en")
    return web.json_response({"markdown": localized.get(locale, localized["en"])})


async def _list_zones(request: web.Request) -> web.Response:
    return await _invoke_power(request, "list-zones")


async def _list_dns_records(request: web.Request) -> web.Response:
    return await _invoke_power(request, "list-dns-records")


async def _invoke_power(request: web.Request, power_id: str) -> web.Response:
    try:
        envelope = await _private_envelope(request, power_id)
        validate_power_input(power_id, envelope.input)
    except (ValueError, PrivateEnvelopeError):
        return _error(400, "invalid_input")
    try:
        if power_id == "list-zones":
            result = await request.app[CLIENT_KEY].list_zones(
                envelope.input["page"], envelope.input["per_page"], envelope.access_token
            )
        else:
            result = await request.app[CLIENT_KEY].list_dns_records(
                envelope.input["zone_id"],
                envelope.input["page"],
                envelope.input["per_page"],
                envelope.access_token,
            )
    except CloudflareReauthorizationRequiredError:
        return _error(409, "cloudflare_reauthorization_required")
    except CloudflareApiError:
        return _error(502, "cloudflare_provider_unavailable")
    return web.json_response(result)


async def _private_envelope(request: web.Request, power_id: str):
    if request.content_type != "application/json":
        raise ValueError("content type must be JSON")
    try:
        payload = load_strict_json(await request.read())
    except (UnicodeError, ValueError, web.HTTPRequestEntityTooLarge) as exc:
        raise ValueError("body must be bounded JSON") from exc
    return validate_power_envelope(payload, power_id)


def _error(status: int, code: str) -> web.Response:
    return web.json_response({"error": code}, status=status)


def main() -> None:
    raw_port = os.environ.get("PORT", "8080")
    if not raw_port.isascii() or not raw_port.isdigit() or not 1 <= int(raw_port) <= 65535:
        raise SystemExit("PORT must be an integer from 1 to 65535")
    web.run_app(create_app(), host=os.environ.get("HOST"), port=int(raw_port), access_log=None)


if __name__ == "__main__":
    main()
