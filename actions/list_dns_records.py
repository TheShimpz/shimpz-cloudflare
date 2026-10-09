"""List DNS records in one Cloudflare zone."""

from shimpz import Context, action

from lib.cloudflare import CloudflareApiClient, CloudflareId, DnsRecordResult, Page, PerPage


@action(integrations=["cloudflare"], effect="read_only")
async def run(zone_id: CloudflareId, page: Page, per_page: PerPage, *, ctx: Context) -> DnsRecordResult:
    return await CloudflareApiClient(ctx).list_dns_records(
        zone_id,
        page,
        per_page,
    )
