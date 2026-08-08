# Sentinel AI Investigation Report (a9bbcd00)

**Dataset:** `urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)`
**Decision:** `BLOCK`
**Severity:** `CRITICAL`
**Evidence Completeness:** `100.0%`

## Executive Summary
Proposed change to dataset 'raw_customers' modifies 1 field(s), including breaking change(s) to 'email'. Sentinel verified 4 confirmed downstream consumer(s) across DataHub lineage graph (DEMO_FIXTURE).

## Why It Matters
Altering column(s) 'email' risks breaking downstream analytical models and dashboards that reference this field. Impacted verified systems include Executive Dashboards and ML Feature Stores.
