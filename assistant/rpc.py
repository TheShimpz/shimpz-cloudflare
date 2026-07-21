#!/usr/local/bin/python3
"""Fixed bounded RPC adapter used by the Team controller."""

from __future__ import annotations

import http.client
import json
import sys
from collections.abc import Callable
from typing import Any

from assistant import PrivateEnvelopeError, load_strict_json, validate_power_envelope

MAX_BODY_BYTES = 8 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
UPSTREAM_TIMEOUT_SECONDS = 8
ROUTES = {
    ("GET", "/healthz"): ("GET", "/health", None),
    ("GET", "/v1/help"): ("GET", "/v1/help", None),
    **{
        ("GET", f"/v1/help/{locale}"): ("GET", f"/v1/help/{locale}", None)
        for locale in ("en", "pt", "es", "zh", "fr", "de", "ja", "ar")
    },
    ("POST", "/v1/powers/list-zones"): ("POST", "/v1/powers/list-zones", "list-zones"),
    ("POST", "/v1/powers/list-dns-records"): ("POST", "/v1/powers/list-dns-records", "list-dns-records"),
}


class RpcInputError(ValueError):
    pass


class RpcUpstreamError(RuntimeError):
    pass


ConnectionFactory = Callable[..., http.client.HTTPConnection]


def invoke(
    method: str,
    path: str,
    raw: bytes,
    *,
    connection_factory: ConnectionFactory = http.client.HTTPConnection,
) -> bytes:
    route = ROUTES.get((method, path))
    if route is None or len(raw) > MAX_BODY_BYTES:
        raise RpcInputError("unsupported RPC input")
    try:
        payload = load_strict_json(raw or b"{}")
    except (UnicodeError, ValueError) as exc:
        raise RpcInputError("RPC body must be JSON") from exc
    if not isinstance(payload, dict):
        raise RpcInputError("RPC body must be an object")
    upstream_method, upstream_path, power_id = route
    if power_id is not None:
        try:
            validate_power_envelope(payload, power_id)
        except PrivateEnvelopeError as exc:
            raise RpcInputError("RPC private envelope is invalid") from exc
    encoded = json.dumps(payload, separators=(",", ":")).encode() if upstream_method == "POST" else None
    headers = {"Content-Type": "application/json", "Content-Length": str(len(encoded))} if encoded else {}
    connection = connection_factory("127.0.0.1", 8080, timeout=UPSTREAM_TIMEOUT_SECONDS)
    try:
        connection.request(upstream_method, upstream_path, body=encoded, headers=headers)
        response = connection.getresponse()
        media_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        raw_length = response.getheader("Content-Length", "")
        if response.status != 200 or media_type != "application/json" or not raw_length.isdigit():
            raise RpcUpstreamError("Assistant response metadata is invalid")
        length = int(raw_length)
        if not 1 <= length <= MAX_RESPONSE_BYTES:
            raise RpcUpstreamError("Assistant response is outside the accepted size")
        output = response.read(length + 1)
        if len(output) != length:
            raise RpcUpstreamError("Assistant response length is invalid")
        decoded: Any = json.loads(output)
        if not isinstance(decoded, dict):
            raise RpcUpstreamError("Assistant response must be an object")
        canonical = json.dumps(decoded, separators=(",", ":")).encode()
        if len(canonical) > MAX_RESPONSE_BYTES:
            raise RpcUpstreamError("Assistant response is outside the accepted size")
    except RpcUpstreamError:
        raise
    except (http.client.HTTPException, OSError, UnicodeError, ValueError) as exc:
        raise RpcUpstreamError("Assistant request failed") from exc
    finally:
        connection.close()
    return canonical


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    try:
        output = invoke(sys.argv[1], sys.argv[2], sys.stdin.buffer.read(MAX_BODY_BYTES + 1))
    except RpcInputError:
        return 2
    except RpcUpstreamError:
        return 3
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
