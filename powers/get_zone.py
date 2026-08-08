"""Get one Cloudflare zone by its exact identifier."""

from shimpz import Context, power

from lib.cloudflare import CloudflareApiClient, CloudflareId, Zone, create_http_session


@power(integrations=["cloudflare"])
async def run(zone_id: CloudflareId, *, ctx: Context) -> Zone:
    async with create_http_session() as session:
        return await CloudflareApiClient(session).get_zone(
            zone_id,
            ctx.integrations.cloudflare.access_token,
        )
