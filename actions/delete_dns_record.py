"""Delete one exact Cloudflare DNS record with absence reconciliation."""

from shimpz import Context, action, identifier, text

from lib.cloudflare import CloudflareApiClient, CloudflareId, DeleteDnsRecordResult, create_http_session


@action(integrations=["cloudflare"], human_requests=["auth:password"])
async def run(zone_id: CloudflareId, record_id: CloudflareId, *, ctx: Context) -> DeleteDnsRecordResult:
    ctx.request_auth(
        "password",
        title=text("Confirm with your Shimpz Supervisor password"),
        description=text(
            "Enter your current Shimpz Supervisor password before permanently deleting record {record_id} "
            "from zone {zone_id}.",
            record_id=identifier(record_id, max_length=32),
            zone_id=identifier(zone_id, max_length=32),
        ),
    )
    access_token = ctx.integrations.cloudflare.access_token
    async with create_http_session() as session:
        return await CloudflareApiClient(session).delete_dns_record(zone_id, record_id, access_token)
