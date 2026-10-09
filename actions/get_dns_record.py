"""Get one Cloudflare DNS record by its exact identifiers."""

from shimpz import Context, action

from lib.cloudflare import CloudflareApiClient, CloudflareId, DnsRecord


@action(integrations=["cloudflare"], effect="read_only")
async def run(zone_id: CloudflareId, record_id: CloudflareId, *, ctx: Context) -> DnsRecord:
    return await CloudflareApiClient(ctx).get_dns_record(
        zone_id,
        record_id,
    )
