## Sentinel AI Change Impact Analysis

**Decision:** `BLOCK` | **Severity:** `CRITICAL` | **Evidence Completeness:** `100.0%`

### Proposed Change:
`COLUMN_REMOVED: raw_customers.email`

**Confirmed Consumers Affected:** `4`

### Critical Lineage Paths:
- `raw_customers → customer_360 → marketing_dashboard`
- `raw_customers → churn_features → churn_model`

### Recommended Action:
Update downstream dbt models and dashboard field references before merging PR. Apply the generated and validated SQLGlot remediation patch to remove references to 'email'.

```diff
--- a/models/marts/customer_360.sql
+++ b/models/marts/customer_360.sql
@@ -1 +1,4 @@
-SELECT customer_id, email, lifetime_value FROM customer_360 WHERE email IS NOT NULL;+SELECT
+  customer_id,
+  lifetime_value
+FROM customer_360
```
