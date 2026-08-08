"""Ensure one exact Cloudflare DNS record exists."""

from shimpz import Context, power

from lib.cloudflare import (
    CloudflareApiClient,
    CloudflareId,
    EnsureDnsRecordResult,
    WritableDnsContent,
    WritableDnsName,
    WritableDnsTtl,
    WritableDnsType,
    create_http_session,
)


@power(integrations=["cloudflare"], human_requests=["approval", "auth:reauth"])
async def run(
    zone_id: CloudflareId,
    record_type: WritableDnsType,
    name: WritableDnsName,
    content: WritableDnsContent,
    ttl: WritableDnsTtl,
    proxied: bool,
    *,
    ctx: Context,
) -> EnsureDnsRecordResult:
    ctx.request_approval(
        title="Ensure this Cloudflare DNS record?",
        description=f"Ensure the reviewed {record_type} record for {name} exists in zone {zone_id}.",
    )
    ctx.request_auth(
        "reauth",
        title="Confirm the Cloudflare DNS creation",
        description=f"Reauthenticate before creating the reviewed {record_type} record for {name} if it is absent.",
    )
    access_token = ctx.integrations.cloudflare.access_token
    async with create_http_session() as session:
        return await CloudflareApiClient(session).ensure_dns_record(
            zone_id,
            record_type,
            name,
            content,
            ttl,
            proxied,
            access_token,
        )
