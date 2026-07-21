# Shimpz Cloudflare

Read-only Cloudflare Assistant for the Shimpz local Admin. It declares one OAuth Account and two
bounded Powers:

- `list-zones` lists Cloudflare zones, including their domain, status, type, and owning account;
- `list-dns-records` lists DNS records from one exact zone identifier.

The Assistant receives a short-lived access token only while one of these Powers runs. It never
receives the OAuth client secret or refresh token. Both Powers are read-only, require no approval,
use fixed Cloudflare API paths, reject redirects, and limit response sizes and pagination.

## Local checks

```console
uv sync --frozen
uv run python -m unittest discover -s tests -v
```

