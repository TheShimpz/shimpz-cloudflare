"""List DNS records in one Cloudflare zone."""

from shimpz import Context, power

from lib.cloudflare import CloudflareApiClient, CloudflareId, DnsRecordResult, Page, PerPage, create_http_session


@power(accounts=["cloudflare"])
async def run(zone_id: CloudflareId, page: Page, per_page: PerPage, *, ctx: Context = None) -> DnsRecordResult:
    async with create_http_session() as session:
        return await CloudflareApiClient(session).list_dns_records(
            zone_id,
            page,
            per_page,
            ctx.accounts.cloudflare.access_token,
        )
