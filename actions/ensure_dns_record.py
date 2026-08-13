"""Ensure one exact Cloudflare DNS record exists."""

from shimpz import Context, action

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


@action(integrations=["cloudflare"], human_requests=["auth:password"])
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
    ctx.request_auth(
        "password",
        title="Confirm with your Shimpz Supervisor password",
        description=(
            f"Enter your current Shimpz Supervisor password before creating the reviewed {record_type} record "
            f"for {name} if it is absent."
        ),
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
