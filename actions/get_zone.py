"""Get one Cloudflare zone by its exact identifier."""

from shimpz import Context, action

from lib.cloudflare import CloudflareApiClient, CloudflareId, Zone


@action(integrations=["cloudflare"], effect="read_only")
async def run(zone_id: CloudflareId, *, ctx: Context) -> Zone:
    return await CloudflareApiClient(ctx).get_zone(
        zone_id,
    )
