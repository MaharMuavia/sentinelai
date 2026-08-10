## Sentinel AI Change Impact Analysis

**Decision:** `BLOCK` | **Severity:** `CRITICAL` | **Evidence Coverage:** `85.0%` | **Trust:** `DEMO FIXTURE — NOT LIVE VERIFIED`

### Proposed Change:
`COLUMN_REMOVED: raw_customers.email`

**Confirmed Consumers Affected:** `4`

### Critical Lineage Paths:
- `raw_customers → customer_360 → marketing_dashboard`
- `raw_customers → churn_features → churn_model`

### Recommended Action:
Review affected downstream dbt models and dashboard field references before merging PR. Apply generated candidate remediation patch where semantic safety is validated.

```diff

```
