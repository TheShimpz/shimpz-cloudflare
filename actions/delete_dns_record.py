"""Delete one exact Cloudflare DNS record with absence reconciliation."""

from shimpz import Context, action

from lib.cloudflare import CloudflareApiClient, CloudflareId, DeleteDnsRecordResult, create_http_session


@action(integrations=["cloudflare"], human_requests=["approval", "auth:reauth"])
async def run(zone_id: CloudflareId, record_id: CloudflareId, *, ctx: Context) -> DeleteDnsRecordResult:
    ctx.request_approval(
        title="Delete this Cloudflare DNS record?",
        description=f"Permanently delete record {record_id} from zone {zone_id} if it still exists.",
    )
    ctx.request_auth(
        "reauth",
        title="Confirm with your Shimpz Supervisor password",
        description=(
            f"Enter your current Shimpz Supervisor password before permanently deleting record {record_id} "
            f"from zone {zone_id}."
        ),
    )
    access_token = ctx.integrations.cloudflare.access_token
    async with create_http_session() as session:
        return await CloudflareApiClient(session).delete_dns_record(zone_id, record_id, access_token)
