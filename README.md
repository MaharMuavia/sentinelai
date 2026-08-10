# Sentinel AI

Sentinel is a pre-merge schema-change firewall. It extracts a real PR schema
diff, retrieves DataHub context through the official MCP Python SDK, builds
provenance-backed impact evidence, computes a deterministic policy decision,
and produces a SQL remediation candidate only when AST safety is demonstrable.

DataHub is essential: the changed schema alone cannot tell Sentinel whether a
field is used by a critical dashboard, model, query, or downstream column.

## Architecture

```text
BASE_SHA/HEAD_SHA
  -> mapped CREATE TABLE schema diff
  -> official DataHub MCP (schemas, owners, tags, lineage, paths, queries)
  -> normalized typed evidence + provenance
  -> deterministic risk and CI verdict
  -> SQLGlot safety classification
  -> authenticated approval
  -> optional GitHub/DataHub actions
  -> SQLite investigation and audit history
```

The MCP client uses `initialize`, `tools/list`, and the official SDK over either
Streamable HTTP or local stdio. Read tools are `get_entities`, `list_schema_fields`,
`get_lineage`, `get_lineage_paths_between`, and `get_dataset_queries`. Optional
write tools are `save_document` and `add_tags`.

## Data modes

- `SENTINEL_DATA_MODE=live` is the default. A live label requires MCP protocol
  negotiation and the required read tools; GMS health alone is insufficient.
- `SENTINEL_DATA_MODE=fixture` is explicit offline demo data. It is always
  labeled `DEMO FIXTURE - NOT LIVE VERIFIED`.
- A disconnected or malformed live MCP response is `DATAHUB_UNAVAILABLE` and
  fails closed for breaking changes. There is no implicit fixture fallback.

## Self-hosted DataHub setup

Sentinel works with DataHub Cloud or the open-source DataHub repository. A
DataHub Cloud free-trial form is not a self-service login: use the tenant URL
provided by DataHub after provisioning. For a fully local submission demo,
install the DataHub CLI and start the pinned quickstart release:

```bash
python -m pip install "acryl-datahub[datahub-rest]"
datahub docker quickstart --version v1.6.0
```

The local UI is `http://localhost:9002` (quickstart-only credentials:
`datahub` / `datahub`) and GMS is `http://localhost:8080`. To enable token-based
service accounts, apply the repository auth override after quickstart:

```powershell
docker compose -p datahub `
  -f "$HOME/.datahub/quickstart/docker-compose.yml" `
  -f datahub-auth.override.yml up -d
```

In DataHub, open **Settings > Users & Groups > Service Accounts**, create a
service account, assign it the **Editor** role, and create a personal access
token for that account. Put the token only in `.env`; never commit it.

Install `uv` so Sentinel can launch the pinned official MCP server:

```bash
python -m pip install uv
```

Then configure `.env`:

```dotenv
DATAHUB_GMS_URL=http://localhost:8080
DATAHUB_GMS_TOKEN=<service-account-token>
DATAHUB_MCP_COMMAND=uvx
DATAHUB_MCP_ARGS=["mcp-server-datahub@0.6.0"]
SENTINEL_DATA_MODE=live
```

On Windows, `DATAHUB_MCP_COMMAND` may need the absolute path to `uvx.exe`.

The canonical Query entity requires a one-time token with permission to create
Query metadata. Set `DATAHUB_SEED_TOKEN` only for `scripts/seed_demo.py`, then
remove or revoke it. Keep the lower-privilege service-account token in
`DATAHUB_GMS_TOKEN` for normal Sentinel reads and writeback.

## Configuration

Copy `.env.example` to `.env`. Configure `DATAHUB_MCP_ENDPOINT` for a managed
Streamable HTTP server. For self-hosted DataHub Core, set
`DATAHUB_MCP_COMMAND` and the JSON `DATAHUB_MCP_ARGS` array for a pinned
official `mcp-server-datahub` release. Configure `DATAHUB_GMS_URL` and its token, and keep
`DATAHUB_MUTATION_ENABLED=false` unless writeback is intentional. The MCP
server separately requires `TOOLS_IS_MUTATION_ENABLED=true` for mutation tools.
Set `SENTINEL_AUTH_TOKEN` before enabling authenticated approval or mutation
endpoints. `GITHUB_REPOSITORY` and `GITHUB_TOKEN` are optional.

For the GitHub Actions firewall, add repository secrets named
`DATAHUB_GMS_URL`, `DATAHUB_GMS_TOKEN`, and `DATAHUB_MCP_ENDPOINT`. The MCP
endpoint must be reachable from GitHub-hosted runners; `localhost` and a
private Docker-network address only work for the local demo. The workflow
fails at a configuration preflight when these secrets are absent.

## Reproducible demo

The mapped demo source files are in
`examples/demo-repository/schemas/`. The breaking scenario removes
`raw_customers.email`; the safe scenario adds an optional column such as
`signup_source`. `sentinel_config.json` maps only these explicit demo files to
DataHub URNs.

With a running DataHub instance and the official MCP server:

```bash
python scripts/seed_demo.py
python scripts/verify_datahub_demo.py
```

The verifier requires MCP connectivity, required tools, the raw dataset schema,
owners/tags, downstream lineage, email column lineage, a matching result from
`get_lineage_paths_between`, and the explicitly seeded canonical Query entity.
It exits non-zero on missing evidence and never reports a fixture as live. The
seeded query is test metadata, not a claim of organic production traffic.

Mutation verification is deliberately restricted to localhost, requires
`DATAHUB_MUTATION_ENABLED=true` and MCP mutation tools, and writes a real
investigation document plus Sentinel tag. The verifier uses an ephemeral
operator token and checks the persisted entities after the write.

Run both policy outcomes against live MCP evidence:

```bash
python scripts/run_ci_check.py --diff-file examples/critical-schema-removal/input.json
python scripts/run_ci_check.py --diff-file examples/safe-additive-change/input.json
```

The breaking case must exit 1 with `BLOCK`; the additive case must exit 0 with
`SAFE_TO_MERGE`. Copy an investigation ID printed by either run to exercise the
authenticated mutation gate and verify the persisted DataHub document/tag:

```bash
python scripts/verify_datahub_demo.py --test-mutations --investigation-id <existing-investigation-id>
```

## Run locally

```bash
python -m pip install -r apps/api/requirements.txt
uvicorn app.main:app --app-dir apps/api --reload --port 8000

npm ci --prefix apps/web
npm run dev --prefix apps/web
```

Open `http://localhost:3000`. For an external action, enter the server's
`SENTINEL_AUTH_TOKEN` in the investigation page, approve the investigation,
then invoke DataHub writeback or the GitHub review action. The browser keeps
the token in component memory only; it is not persisted in local storage.

The production Compose profile runs PostgreSQL and the pinned DataHub MCP
server as dedicated services. The MCP service uses native stateless HTTP, so
API requests do not launch a new subprocess for each tool call. Set a strong
`POSTGRES_PASSWORD`, keep DataHub running on the host or set
`DATAHUB_DOCKER_GMS_URL`, then run:

```bash
docker compose up --build
```

The API waits for PostgreSQL and MCP health checks before starting. For an
external managed MCP server, override `DATAHUB_MCP_ENDPOINT`. For an external
managed PostgreSQL database, set `COMPOSE_DATABASE_URL`. Set
`NEXT_PUBLIC_API_URL` before `docker compose build web`; Next.js embeds this
public browser URL into the production bundle at build time.

### Production identity

Static bearer authentication remains the local demo default. For production,
configure an OIDC provider whose access tokens contain the
`sentinel:mutate` scope:

```dotenv
AUTH_MODE=oidc
OIDC_ISSUER=https://identity.example.com/
OIDC_AUDIENCE=sentinel-api
OIDC_JWKS_URL=https://identity.example.com/.well-known/jwks.json
OIDC_ALGORITHM=RS256
OIDC_REQUIRED_SCOPES=sentinel:mutate
```

The API validates signature, issuer, audience, expiry, issued-at time, subject,
and required scopes. The investigation page accepts the resulting access token
in memory without storing it in browser storage.

The analysis endpoints are side-effect-free. If an investigation needs an
external action, the server persists `AWAITING_APPROVAL`. An authenticated
`POST /api/investigations/{id}/approve` transitions that state; writeback and
GitHub action endpoints require the persisted approval and server auth token.
The request body cannot self-approve an investigation.

## Tests and CI

```bash
python -m pytest apps/api/tests/ -v
npm ci --prefix apps/web
npm run lint --prefix apps/web
npm run build --prefix apps/web
```

GitHub Actions runs backend tests from repository-root paths, builds the
frontend, extracts `BASE_SHA`/`HEAD_SHA`, and runs the firewall. `SAFE_TO_MERGE`
exits 0. `BLOCK`, `INSUFFICIENT_EVIDENCE`, unmapped, malformed, and unsupported
schema changes exit non-zero. `MERGE_WITH_CAUTION` is controlled by
`SENTINEL_STRICT_CAUTION` and defaults to a failing strict policy.

## Known limitations

Historical query usage is reported only when the connected DataHub deployment
returns it; Sentinel does not synthesize query IDs, timestamps, or users. The
canonical demo seeder creates one clearly named test Query entity so the MCP
query-evidence path is reproducibly testable.

The local self-hosted DataHub MCP read path, approval gate, `save_document`,
and `add_tags` writeback were verified against DataHub Core v1.6.0. A real
GitHub PR comment remains environment-dependent and must be treated as
`UNVERIFIED` until a repository, PR, and token are supplied. Production
deployments should use the provided OIDC and PostgreSQL configuration instead
of the local static-token and SQLite defaults.

Apache 2.0 licensed.
