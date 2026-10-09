"""Replace one exact Cloudflare DNS record with complete desired state."""

from shimpz import Context, action, identifier, text

from lib.cloudflare import (
    CloudflareApiClient,
    CloudflareId,
    DnsRecord,
    WritableDnsContent,
    WritableDnsName,
    WritableDnsTtl,
    WritableDnsType,
)


@action(description="Replace one DNS record with new values.", integrations=["cloudflare"], human_requests=["auth:password"])
async def run(
    zone_id: CloudflareId,
    record_id: CloudflareId,
    record_type: WritableDnsType,
    name: WritableDnsName,
    content: WritableDnsContent,
    ttl: WritableDnsTtl,
    proxied: bool,
    *,
    ctx: Context,
) -> DnsRecord:
    ctx.request_auth(
        "password",
        title=text("Confirm with your Shimpz Supervisor password"),
        description=text(
            "Enter your current Shimpz Supervisor password before replacing record {record_id} in zone {zone_id}.",
            record_id=identifier(record_id, max_length=32),
            zone_id=identifier(zone_id, max_length=32),
        ),
    )
    return await CloudflareApiClient(ctx).replace_dns_record(
        zone_id,
        record_id,
        record_type,
        name,
        content,
        ttl,
        proxied,
    )
