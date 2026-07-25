"""List Cloudflare zones."""

from lib.cloudflare import CloudflareApiClient, Page, PerPage, ZoneResult, create_http_session
from shimpz import Context, power


@power(accounts=["cloudflare"])
async def run(page: Page, per_page: PerPage, *, ctx: Context = None) -> ZoneResult:
    async with create_http_session() as session:
        return await CloudflareApiClient(session).list_zones(
            page,
            per_page,
            ctx.accounts.cloudflare.access_token,
        )
