"""Replace one exact Cloudflare DNS record with complete desired state."""

from shimpz import Context, power

from lib.cloudflare import (
    CloudflareApiClient,
    CloudflareId,
    DnsRecord,
    WritableDnsContent,
    WritableDnsName,
    WritableDnsTtl,
    WritableDnsType,
    create_http_session,
)


@power(integrations=["cloudflare"], human_requests=["approval", "auth:reauth"])
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
    ctx.request_approval(
        title="Replace this Cloudflare DNS record?",
        description=f"Replace record {record_id} with the reviewed {record_type} state for {name} in zone {zone_id}.",
    )
    ctx.request_auth(
        "reauth",
        title="Confirm the Cloudflare DNS replacement",
        description=f"Reauthenticate before replacing record {record_id} in zone {zone_id}.",
    )
    access_token = ctx.integrations.cloudflare.access_token
    async with create_http_session() as session:
        return await CloudflareApiClient(session).replace_dns_record(
            zone_id,
            record_id,
            record_type,
            name,
            content,
            ttl,
            proxied,
            access_token,
        )
