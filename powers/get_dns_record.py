"""Get one Cloudflare DNS record by its exact identifiers."""

from shimpz import Context, power

from lib.cloudflare import CloudflareApiClient, CloudflareId, DnsRecord, create_http_session


@power(integrations=["cloudflare"])
async def run(zone_id: CloudflareId, record_id: CloudflareId, *, ctx: Context) -> DnsRecord:
    async with create_http_session() as session:
        return await CloudflareApiClient(session).get_dns_record(
            zone_id,
            record_id,
            ctx.integrations.cloudflare.access_token,
        )
