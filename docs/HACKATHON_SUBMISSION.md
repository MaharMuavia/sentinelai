# DataHub Agent Hackathon — Submission Guide & Materials

**Project Name**: Sentinel AI  
**Track**: Agents That Do Real Work  
**Repository**: [https://github.com/MaharMuavia/sentinelai](https://github.com/MaharMuavia/sentinelai)  

---

## 1. Devpost Project Description

### Tagline
Autonomous pre-merge data change control agent powered by DataHub Model Context Protocol (MCP). Verifies blast radius, enforces PR policy, generates AST-validated code patches, and writes investigation memory back into DataHub.

### Problem
Data engineering and analytics teams routinely suffer from silent production outages when upstream database schema changes (e.g. dropping a column, changing a data type, or altering nullability) are merged into main git branches. Existing tools alert engineers *after* the pipeline or executive dashboard breaks in production, forcing emergency firefighting and corrupting metrics.

### Solution
Sentinel AI operates **before merge**. When a developer opens a GitHub PR modifying a data model or schema, Sentinel:
1. **Extracts** the actual schema diff from git `BASE_SHA` vs `HEAD_SHA` revisions deterministically.
2. **Queries DataHub** through official Model Context Protocol (MCP) JSON-RPC 2.0 tools (`get_entities`, `list_schema_fields`, `get_lineage`, `get_lineage_paths_between`, `get_dataset_queries`).
3. **Distinguishes** confirmed downstream consumers (executive Looker dashboards, ML feature stores) from merely connected assets with explicit provenance.
4. **Calculates** transparent, rule-based severity, evidence coverage %, and evidence trust (`LIVE DATAHUB MCP` vs `DEMO FIXTURE — NOT LIVE VERIFIED` vs `DATAHUB UNAVAILABLE`).
5. **Generates & Validates** candidate SQLGlot AST remediation patches, enforcing strict semantic safety rules (requiring human engineer review if predicates in `WHERE`, `JOIN`, `HAVING`, or `GROUP BY` are affected).
6. **Enforces** PR policy in GitHub CI (failing closed with exit code 1 on `BLOCK` and `INSUFFICIENT_EVIDENCE`), gates external mutations behind authenticated human approval, and, when mutation tools are explicitly enabled, **writes the investigation outcome back into DataHub via MCP `save_document` and `add_tags` tools**.

---

## 2. 3-Minute Video Script (YouTube / Vimeo Compatible)

| Time | Scene | Voiceover / Action |
| --- | --- | --- |
| **0:00–0:20** | **Problem Statement** | "Data pipelines break in production because upstream schema changes are merged blindly. A developer drops a column like `customers.email`, and 2 hours later executive dashboards and ML churn models crash." |
| **0:20–0:35** | **Why DataHub Context** | "DataHub already knows what depends on your data. Sentinel AI takes that context and turns it into an autonomous pre-merge change control firewall using official DataHub Model Context Protocol." |
| **0:35–0:55** | **Show GitHub PR Change** | "Here is a real GitHub PR diff removing `raw_customers.email`. Sentinel's CI workflow extracts the diff between base and head commit SHAs deterministically." |
| **0:55–1:20** | **DataHub MCP Calls & Provenance** | "Sentinel queries DataHub GMS over MCP: calling `get_entities` for schema and owners, `get_lineage` for multi-hop graph traversal, and `get_dataset_queries` for execution log history. Notice how every item carries explicit MCP tool provenance." |
| **1:20–1:45** | **Impact Graph & BLOCK Decision** | "Sentinel constructs the blast-radius graph and returns BLOCK with evidence coverage derived from the run. It isolates confirmed executive dashboard and ML model consumers from unaffected billing assets." |
| **1:45–2:05** | **Remediation Safety & Human Review** | "Because the email column is used in a WHERE filter predicate, Sentinel's semantic safety engine flags it as REQUIRES HUMAN REVIEW rather than auto-deleting business filters." |
| **2:05–2:25** | **GitHub Gate & DataHub Writeback** | "GitHub Actions CI blocks the PR with exit code 1. I enter the demo operator token, approve the action, and click 'Persist to DataHub'. With mutation mode enabled, Sentinel executes MCP `save_document` and `add_tags`, then verifies the persisted document and tag in DataHub." |
| **2:25–2:45** | **SAFE Case / Differentiation** | "If we run a non-breaking additive change adding `signup_source`, Sentinel verifies zero downstream breaks, returns SAFE TO MERGE, and CI passes with exit code 0." |
| **2:45–3:00** | **Closing Value** | "DataHub knows your data stack. Sentinel AI uses that context to stop breaking changes before they ship. Thank you!" |

---

## 3. Judge Criteria & Implementation Evidence Mapping

### 1. Use of DataHub
- **Implementation**: Built on official DataHub Model Context Protocol (MCP) JSON-RPC 2.0 tools (`get_entities`, `list_schema_fields`, `get_lineage`, `get_lineage_paths_between`, `get_dataset_queries`, `save_document`, `add_tags`).
- **Code Evidence**: [`apps/api/app/datahub/mcp_client.py`](../apps/api/app/datahub/mcp_client.py) & [`apps/api/app/datahub/client.py`](../apps/api/app/datahub/client.py).
- **Truthfulness**: Strictly distinguishes `LIVE_DATAHUB` mode from `DEMO_FIXTURE` and `DATAHUB_UNAVAILABLE` modes with explicit evidence provenance tags.

### 2. Technical Execution
- **Implementation**: FastAPI backend, Next.js 16 frontend, SQLGlot AST engine, PostgreSQL/SQLAlchemy persistence, OIDC-scoped mutation authorization, and a pinned long-lived DataHub MCP HTTP sidecar.
- **Code Evidence**: Real git commit PR diff extraction (`extract_pr_diff.py`), deterministic CI exit code enforcement (`run_ci_check.py`), semantic remediation safety checks (`remediation/engine.py`), and non-interactive ESLint setup.
- **Testing**: The final local run passed 51 backend contract/regression tests, ESLint, the Next.js production build, PostgreSQL readiness/persistence, MCP sidecar health, and container startup. Live GitHub checks remain reported separately as PASS, FAIL, or UNVERIFIED.

### 3. Originality
- **Implementation**: Moves beyond passive metadata browsing by turning DataHub context into an **active pre-merge change firewall**.
- **Code Evidence**: Combines column-level lineage, query execution logs, AST transformation, CI policy enforcement, human approval gating, and DataHub MCP aspect mutation into a single closed loop.

### 4. Real-World Usefulness
- **Implementation**: Solves a major pain point for data engineering, analytics, and platform teams by blocking breaking schema changes before main branch merges.

---

## 4. Manual Checklist Before Devpost Submission

- [ ] Verify GitHub repository is public: `https://github.com/MaharMuavia/sentinelai`
- [ ] Configure a real test PR and GitHub token before claiming that a PR comment was posted live.
- [ ] Add the local DataHub service-account token as the `DATAHUB_GMS_TOKEN`
repository secret, register the Ubuntu self-hosted runner, and keep the local
DataHub/MCP Compose services running before treating the GitHub firewall check
as live-verified.
- [ ] Confirm Apache 2.0 license is visible in root `LICENSE`.
- [ ] Record <3 minute video following the script above.
- [ ] Upload video to YouTube or Vimeo and paste public URL into Devpost submission (Note: Loom is not an accepted target per Devpost rules).
- [ ] Copy Devpost description from Section 1 above into Devpost form.
- [ ] Select Track: **"Agents That Do Real Work"**.
- [ ] Submit Devpost entry before hackathon deadline.
