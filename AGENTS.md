# Shimpz Cloudflare repository rules

## Authority

- This repository owns the independently published Shimpz Cloudflare Assistant: its manifest, Genesis, Powers,
  provider client, public result schemas, and component tests.
- It does not own Cloudflare OAuth-client custody, OAuth callback or token exchange, Team Integration state,
  Assistant publication authority, Team installation, or platform egress enforcement.
- Read the canonical [Shimpz architecture](https://github.com/TheShimpz/shimpz/blob/main/.context/ARCHITECTURE.md),
  [OAuth control-plane ADR](https://github.com/TheShimpz/shimpz/blob/main/.context/decisions/0010-oauth-integration-control-plane.md),
  and [Power human-request ADR](https://github.com/TheShimpz/shimpz/blob/main/.context/decisions/0038-power-human-requests.md)
  before changing Integration scopes, externally visible actions, credentials, or human authority.

## Delivery

- Work in the smallest independently reviewable task that produces a useful result.
- After a microtask succeeds, run the smallest relevant checks, commit it immediately, and push it immediately.
- Never batch unrelated successful microtasks into one commit.
- Write English conventional commit messages with a clear imperative subject.

## Engineering

- Keep every Power bounded, least-privilege, fail-closed, and limited to fixed Cloudflare API paths.
- Never receive an OAuth client secret or refresh token, choose OAuth endpoints, process callbacks, or persist an
  access token. Read the invocation-scoped access token only after every human request has completed.
- Reject redirects, oversized or malformed provider responses, undeclared fields that widen an operation, and any
  error path that could disclose a credential.
- Declare every human-request capability exactly. Use input for one missing value, approval for an externally
  visible action, and platform authentication only for fresh Shimpz assurance; never emulate authentication with
  input.
- Shimpz is pre-production. Change the current contract directly without compatibility aliases or old-format
  parsers.
- Use Python 3.14.

## Validation

- Run `shimpz check` for the complete Assistant contract and component suite.
- Run `.venv/bin/ruff check --config pyproject.toml .` after changing Python.
- Prefer focused unit tests while iterating, but do not claim provider behavior without the required real OAuth and
  least-privilege API proof.
