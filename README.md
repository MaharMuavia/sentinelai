# Sentinel AI

**Know what a data change will break before you merge it — then generate the fix.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Hackathon](https://img.shields.io/badge/Hackathon-Build_with_DataHub_2026-purple.svg)](https://datahubproject.io)
[![Track](https://img.shields.io/badge/Track-Agents_That_Do_Real_Work-emerald.svg)](https://datahub.devpost.com/)

> **Sentinel AI** is an autonomous pre-merge change firewall powered by DataHub Model Context Protocol (MCP). It investigates proposed schema changes before pull requests are merged, retrieves real organizational context through DataHub MCP tools, constructs provenance-backed evidence, enforces deterministic merge policy, proposes safely validated remediation, gates external mutations behind human engineer approval, blocks unsafe GitHub PRs, and writes persistent investigation memory back into DataHub.

---

## 1. Problem & Product Positioning

### Problem
Data engineering and analytics teams routinely face silent production outages when upstream database schema changes (e.g. dropping a column, altering a data type, or renaming a field) are merged into main git branches. Existing tools notify engineers *after* the pipeline or executive dashboard breaks in production, resulting in emergency firefighting and corrupted metrics.

### Solution & Positioning
- **DataHub**: The central system of organizational metadata truth. Provides entity schemas, technical/business ownership, column-level lineage, and query execution logs.
- **Sentinel AI**: Turns DataHub context into an **autonomous pre-merge change firewall**. Operates before merge, evaluates proposed schema diffs, computes deterministic risk, enforces CI merge policy, generates AST-validated code patches, and writes persistent investigation memory back into DataHub via Model Context Protocol (MCP).

---

## 2. System Architecture

```mermaid
graph TD
    A[Real GitHub PR: BASE_SHA vs HEAD_SHA] -->|1. Extract Diff & Repository Mapping| B[scripts/extract_pr_diff.py]
    B -->|2. Machine-Readable Diff Artifact| C[Sentinel Workflow Orchestrator]
    C -->|3. DataHub MCP Client (JSON-RPC 2.0)| D[(DataHub MCP Server / GMS Endpoint)]
    D -->|Tools: get_entities, list_schema_fields, get_lineage, get_lineage_paths_between, get_dataset_queries| C
    C -->|4. Build Provenanced Blast Radius Graph| E[Impact Evidence Engine]
    E -->|Classify Consumers & Provenance| F[Deterministic Risk Engine]
    F -->|5. Severity, Verdict & Evidence Coverage| G[Evidence-Grounded Reasoning Engine]
    C -->|6. AST Patch Generation & Semantic Safety Rules| H[SQLGlot Remediation Engine]
    H -->|7. Predicate Safety Check| I[Validated Patch / Human Review Required]
    C -->|8. Human Approval Gating| J[Human Authorization Check]
    J -->|9. Post PR Comment & Exit Code Enforcement| K[GitHub Actions API & CI Firewall]
    J -->|10. MCP save_document & add_tags| D
    C -->|11. Stage Audit History| L[(SQLite Audit DB)]
    L -->|12. Real-Time UX| M[Next.js Dashboard & Truth Badges]
```

---

## 3. Official DataHub Model Context Protocol (MCP) Integration

Sentinel AI interacts with DataHub strictly through official Model Context Protocol (MCP) JSON-RPC 2.0 tools:

| MCP Tool Name | Purpose in Sentinel AI |
| --- | --- |
| `get_entities` | Retrieves dataset schema fields, technical/business owners, tags, and domain metadata. |
| `list_schema_fields` | Fetches fine-grained column specifications for snapshot validation. |
| `get_lineage` | Traverses multi-hop downstream dataset, dashboard, and ML model dependencies. |
| `get_lineage_paths_between` | Traces exact field-to-field lineage paths from root dataset to consumer. |
| `get_dataset_queries` | Inspects historical SQL query execution logs referencing dataset columns. |
| `save_document` | Ingests persistent Sentinel investigation audit documents into DataHub. |
| `add_tags` | Applies additive Sentinel risk tags (`Sentinel_BLOCK`, `Sentinel_SAFE_TO_MERGE`) to datasets. |

Every evidence item carries an explicit `EvidenceProvenance` object tracking `source_mode`, `source_tool`, `entity_urn`, `field_path`, and `retrieved_at`.

---

## 4. Integration Modes & Strict Data Policy

Sentinel enforces strict evidence truthfulness across three explicit data modes:
- **`LIVE_DATAHUB`**: Connected to a live DataHub GMS instance over MCP. Every item carries live tool provenance.
- **`DEMO_FIXTURE`**: Activated explicitly via `SENTINEL_DATA_MODE=fixture` for offline evaluation. Labeled as `DEMO FIXTURE — NOT LIVE VERIFIED`.
- **`DATAHUB_UNAVAILABLE`**: DataHub GMS is offline and fixture fallback is disabled. Sentinel returns `0% Evidence Coverage`, `Trust: DATAHUB UNAVAILABLE`, and verdict `INSUFFICIENT_EVIDENCE` (failing closed). Silent switching to fixtures is completely eliminated.

---

## 5. Semantic Remediation Safety Engine

Sentinel's AST remediation engine (`SQLRemediationEngine`) enforces strict safety levels:
- `SYNTAX_VALID` / `STRUCTURALLY_VALID`: AST transformation passed static syntax and structural validation.
- `REQUIRES_HUMAN`: If a removed column is referenced in `WHERE`, `JOIN`, `HAVING`, `GROUP BY`, `ORDER BY`, or `CASE` predicates, automatic approval is **DENIED**. Business filters are NEVER silently deleted.
- `REMEDIATION_NOT_GENERATED`: Returned when downstream source SQL is unavailable.

---

## 6. Quickstart & Local Setup

### Prerequisites
- Python 3.11+
- Node.js 20+

### 1. Clone Repository & Install Backend
```bash
git clone https://github.com/MaharMuavia/sentinelai.git
cd sentinelai

cd apps/api
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### 2. Start Next.js Frontend
```bash
cd apps/web
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000).

### 3. Seed & Verify DataHub Demo Graph
```bash
python scripts/seed_demo.py
python scripts/verify_datahub_demo.py
```

---

## 7. Automated Test Suite & CI Enforcement

Run backend test suite:
```bash
cd apps/api
python -m pytest tests/
```

Run GitHub Actions CI policy check:
```bash
python scripts/extract_pr_diff.py --fixture examples/critical-schema-removal/input.json
python scripts/run_ci_check.py
```

---

## License

Licensed under the [Apache License 2.0](LICENSE).
