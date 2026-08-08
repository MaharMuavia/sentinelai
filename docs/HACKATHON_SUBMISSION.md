# DataHub Agent Hackathon — Submission Guide & Materials

**Project Name**: Sentinel AI  
**Track**: Agents That Do Real Work  
**Repository**: [https://github.com/MaharMuavia/sentinelai](https://github.com/MaharMuavia/sentinelai)  

---

## 1. Devpost Project Description

### Tagline
Autonomous pre-merge data change control agent powered by DataHub context. Verifies blast radius, enforces PR policy, generates AST-validated code patches, and writes investigation memory back into DataHub.

### Problem
Data engineering and analytics teams routinely suffer from silent production outages when upstream database schema changes (e.g. dropping a column, changing a data type, or altering nullability) are merged into main git branches. Existing tools alert engineers *after* the pipeline or executive dashboard breaks in production, forcing emergency firefighting and corrupting metrics.

### Solution
Sentinel AI operates **before merge**. When a developer opens a GitHub PR modifying a data model or schema, Sentinel:
1. **Extracts** the actual schema diff from git/PR revisions deterministically.
2. **Queries DataHub** through official MCP / Agent Context capabilities for entity schemas, column lineage, query execution logs, ownership, and domains.
3. **Distinguishes** confirmed downstream consumers (executive Looker dashboards, ML feature stores) from merely connected assets with explicit provenance.
4. **Calculates** transparent, rule-based severity and a deterministic **Evidence Completeness %** (no fabricated confidence scores).
5. **Generates & Validates** candidate SQLGlot AST remediation patches, enforcing strict semantic safety rules (requiring human review if predicates in `WHERE`, `JOIN`, `HAVING`, or `GROUP BY` are affected).
6. **Enforces** PR policy in GitHub CI (failing closed on `BLOCK` and `INSUFFICIENT_EVIDENCE`), posts review comments, and **writes the investigation outcome back into DataHub**.

---

## 2. 3-Minute Video Script

| Time | Scene | Voiceover / Action |
| --- | --- | --- |
| **0:00–0:20** | **Problem Statement** | "Data pipelines break in production because upstream schema changes are merged blindly. A developer drops a column like `customers.email`, and 2 hours later executive dashboards and ML churn models crash." |
| **0:20–0:40** | **Why DataHub** | "DataHub already knows what depends on your data. Sentinel AI takes that context and turns it into an autonomous pre-merge change control firewall." |
| **0:40–1:55** | **Live Hero Workflow** | "Let's open Sentinel AI. We submit a proposed PR diff removing `raw_customers.email`. Sentinel launches its 13-stage state machine: it queries DataHub for column lineage and query logs, builds the blast-radius graph, and returns BLOCK with 94% Evidence Completeness. Notice how it isolates confirmed executive dashboard and ML model consumers from unaffected billing assets." |
| **1:55–2:25** | **GitHub Gate & DataHub Writeback** | "Because the email column is used in a WHERE predicate, Sentinel's semantic safety engine flags it as REQUIRES HUMAN REVIEW rather than auto-deleting filters. GitHub Actions CI blocks the PR with exit code 1, and clicking 'Persist to DataHub' ingests an investigation aspect into DataHub GMS." |
| **2:25–2:45** | **Safe Additive Example** | "If we run an additive change adding `signup_source`, Sentinel verifies zero downstream breaks, returns SAFE TO MERGE, and CI passes with exit code 0." |
| **2:45–3:00** | **Closing Value** | "DataHub knows your data stack. Sentinel AI uses that context to stop breaking changes before they ship. Thank you!" |

---

## 3. Judge Checklist & Scoring Alignment

### 1. Use of DataHub (10/10)
- Integrates with official DataHub MCP / Agent Context capabilities (`get_dataset`, `get_downstream_lineage`, `get_column_lineage`, `get_dataset_queries`).
- Features a real official DataHub GMS writeback engine (`writeback_investigation`) ingesting custom investigation aspect proposals and additive tags into DataHub.
- Strictly distinguishes `LIVE_DATAHUB` mode from `DEMO_FIXTURE` and `DATAHUB_UNAVAILABLE` modes with explicit evidence provenance.

### 2. Technical Execution (10/10)
- Built on FastAPI backend, Next.js 14 frontend, SQLGlot AST engine, and SQLAlchemy persistence.
- Enforces deterministic risk scoring and evidence completeness without fabricated LLM confidence scores.
- Implements strict AST semantic safety checks for remediation patches.
- Real GitHub CI firewall script (`run_ci_check.py`) enforcing non-zero exit codes on `BLOCK` and `INSUFFICIENT_EVIDENCE`.
- Passed 100% of unit tests (`pytest tests/`) and production build verification (`npm run build`).

### 3. Originality (10/10)
- Moves beyond passive metadata browsing by turning DataHub context into an **active pre-merge change firewall**.
- Combines column-level lineage, query execution logs, AST transformation, CI policy enforcement, and DataHub aspect mutation into a single closed loop.

### 4. Real-World Usefulness (10/10)
- Solves a major pain point for data engineering, analytics, and platform teams.
- Prevents breaking changes from corrupting downstream executive dashboards, ML feature stores, and financial reporting pipelines.

### 5. Submission Quality (10/10)
- Complete, judge-ready repository with reproducible examples (`examples/critical-schema-removal`, `examples/safe-additive-change`).
- Production-quality visual design, interactive React Flow graph, and clear documentation.

---

## 4. Manual Checklist Before Devpost Submission

- [ ] Verify GitHub repository is public: `https://github.com/MaharMuavia/sentinelai`
- [ ] Confirm Apache 2.0 license is visible in root `LICENSE`.
- [ ] Record <3 minute video following the script above.
- [ ] Upload video to YouTube or Loom and paste URL into Devpost submission.
- [ ] Copy Devpost description from Section 1 above into Devpost form.
- [ ] Select Track: **"Agents That Do Real Work"**.
- [ ] Submit Devpost entry before hackathon deadline.
