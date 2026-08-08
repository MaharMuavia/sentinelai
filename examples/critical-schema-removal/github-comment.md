## Sentinel AI Change Impact Analysis

**Decision:** `INSUFFICIENT_EVIDENCE` | **Severity:** `HIGH` | **Evidence Coverage:** `0.0%` | **Trust:** `DATAHUB UNAVAILABLE`

### Proposed Change:
`COLUMN_REMOVED: raw_customers.email`

**Confirmed Consumers Affected:** `0`

### Critical Lineage Paths:
- `raw_customers → customer_360 → marketing_dashboard`
- `raw_customers → churn_features → churn_model`

### Recommended Action:
Verify DataHub connectivity or supply missing lineage metadata before merging PR.

```diff

```
