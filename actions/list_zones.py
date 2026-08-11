"""List Cloudflare zones."""

from shimpz import Context, action

from lib.cloudflare import CloudflareApiClient, Page, ZoneResult, ZonesPerPage, create_http_session


@action(integrations=["cloudflare"])
async def run(page: Page, per_page: ZonesPerPage, *, ctx: Context) -> ZoneResult:
    async with create_http_session() as session:
        return await CloudflareApiClient(session).list_zones(
            page,
            per_page,
            ctx.integrations.cloudflare.access_token,
        )
