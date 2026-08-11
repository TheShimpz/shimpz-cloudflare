# Shimpz Cloudflare

Cloudflare Assistant with seven bounded Actions:

- `list-zones` lists Cloudflare zones, including their domain, status, type, and owning account;
- `get-zone` returns one zone selected by its exact identifier;
- `list-dns-records` lists DNS records from one exact zone identifier;
- `get-dns-record` returns one record selected by its exact zone and record identifiers;
- `ensure-dns-record` returns an existing exact A, AAAA, CNAME, or TXT record or creates it once when absent;
- `replace-dns-record` replaces one exact record with complete reviewed state;
- `delete-dns-record` deletes one exact record and reconciles an already absent target.

The Assistant receives a short-lived access token only while one of these Actions runs. It never
receives the OAuth client secret or refresh token. Read Actions require no human gate. Every mutation obtains
attributable approval and fresh Shimpz reauthentication before it can observe the access token. All requests use
fixed Cloudflare API paths, reject redirects and automatic connection retries, and bound request and response sizes.

The OAuth Integration requests only `zone.read`, `dns.read`, `dns.write`, and `offline_access`. Zones remain
read-only. DNS writes support only the four closed record shapes above; the Assistant accepts no arbitrary
Cloudflare endpoint or JSON body.

Each file in `actions/` is one Action. Shared provider code lives in `lib/cloudflare.py`. The Shimpz CLI
manages Python and the SDK, generates the machine contract in memory, and runs Actions without Docker.

The root `icon.png` presents the Cloudflare cloud mark alone on a transparent canvas, without a tile,
frame, or decorative background. Cloudflare and the Cloudflare logo are trademarks and/or registered
trademarks of Cloudflare, Inc. in the United States and other jurisdictions. Their use identifies the
provider integration and does not imply Cloudflare endorsement of this Assistant.

## Local checks

```console
shimpz check
```
