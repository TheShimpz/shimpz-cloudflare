# Shimpz Cloudflare

Read-only Cloudflare Assistant with two bounded Powers:

- `list-zones` lists Cloudflare zones, including their domain, status, type, and owning account;
- `list-dns-records` lists DNS records from one exact zone identifier.

The Assistant receives a short-lived access token only while one of these Powers runs. It never
receives the OAuth client secret or refresh token. Both Powers are read-only, require no approval,
use fixed Cloudflare API paths, reject redirects, and limit response sizes and pagination.

Each file in `powers/` is one Power. Shared provider code lives in `lib/cloudflare.py`. The Shimpz CLI
manages Python and the SDK, generates the machine contract in memory, and runs Powers without Docker.

The root `icon.png` presents the Cloudflare cloud mark alone on a transparent canvas, without a tile,
frame, or decorative background. Cloudflare and the Cloudflare logo are trademarks and/or registered
trademarks of Cloudflare, Inc. in the United States and other jurisdictions. Their use identifies the
provider integration and does not imply Cloudflare endorsement of this Assistant.

## Local checks

```console
shimpz check
```
