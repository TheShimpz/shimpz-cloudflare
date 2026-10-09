"""Delete one exact Cloudflare DNS record with absence reconciliation."""

from shimpz import Context, action, identifier, text

from lib.cloudflare import CloudflareApiClient, CloudflareId, DeleteDnsRecordResult


@action(description="Delete one DNS record.", integrations=["cloudflare"], human_requests=["auth:password"])
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
    return await CloudflareApiClient(ctx).delete_dns_record(zone_id, record_id)
