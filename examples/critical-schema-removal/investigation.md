# Sentinel AI Investigation Report (4a274eb9)

**Dataset:** `urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)`
**Decision:** `BLOCK`
**Severity:** `CRITICAL`
**Evidence Completeness:** `100.0%`

## Executive Summary
Proposed change to dataset 'raw_customers' modifies 1 field(s), including breaking change(s) to 'email'. Sentinel verified 4 confirmed downstream consumer(s) across DataHub lineage graph.

## Why It Matters
Removing or altering column(s) 'email' breaks downstream analytical models and dashboards that explicitly select this field. Impacted critical systems include Executive Looker Dashboards and ML Churn Prediction Models.
