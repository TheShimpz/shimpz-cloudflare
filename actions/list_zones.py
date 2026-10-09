"""List Cloudflare zones."""

from shimpz import Context, action

from lib.cloudflare import CloudflareApiClient, Page, ZoneResult, ZonesPerPage


@action(integrations=["cloudflare"], effect="read_only")
async def run(page: Page, per_page: ZonesPerPage, *, ctx: Context) -> ZoneResult:
    return await CloudflareApiClient(ctx).list_zones(
        page,
        per_page,
    )
