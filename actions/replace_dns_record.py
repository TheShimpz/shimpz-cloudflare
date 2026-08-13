"""Replace one exact Cloudflare DNS record with complete desired state."""

from shimpz import Context, action

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


@action(integrations=["cloudflare"], human_requests=["auth:password"])
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
        title="Confirm with your Shimpz Supervisor password",
        description=(
            f"Enter your current Shimpz Supervisor password before replacing record {record_id} in zone {zone_id}."
        ),
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
