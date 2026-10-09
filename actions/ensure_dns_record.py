"""Ensure one exact Cloudflare DNS record exists."""

from shimpz import Context, action, text

from lib.cloudflare import (
    CloudflareApiClient,
    CloudflareId,
    EnsureDnsRecordResult,
    WritableDnsContent,
    WritableDnsName,
    WritableDnsTtl,
    WritableDnsType,
    ensure_authorization_description,
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
        title=text("Confirm with your Shimpz Supervisor password"),
        description=ensure_authorization_description(zone_id, record_type, name),
    )
    return await CloudflareApiClient(ctx).ensure_dns_record(
        zone_id,
        record_type,
        name,
        content,
        ttl,
        proxied,
    )
