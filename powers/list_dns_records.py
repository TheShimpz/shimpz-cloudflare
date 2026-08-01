"""List DNS records in one Cloudflare zone."""

from lib.cloudflare import CloudflareApiClient, CloudflareId, DnsRecordResult, Page, PerPage, create_http_session
from shimpz import Context, power


@power(integrations=["cloudflare"])
async def run(zone_id: CloudflareId, page: Page, per_page: PerPage, *, ctx: Context) -> DnsRecordResult:
    async with create_http_session() as session:
        return await CloudflareApiClient(session).list_dns_records(
            zone_id,
            page,
            per_page,
            ctx.integrations.cloudflare.access_token,
        )
