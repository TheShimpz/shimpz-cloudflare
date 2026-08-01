"""List Cloudflare zones."""

from lib.cloudflare import CloudflareApiClient, Page, PerPage, ZoneResult, create_http_session
from shimpz import Context, power


@power(integrations=["cloudflare"])
async def run(page: Page, per_page: PerPage, *, ctx: Context) -> ZoneResult:
    async with create_http_session() as session:
        return await CloudflareApiClient(session).list_zones(
            page,
            per_page,
            ctx.integrations.cloudflare.access_token,
        )
