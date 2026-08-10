# Sentinel AI Investigation Report (0aa4896e-7e5b-43d0-82c3-8e496213513e)

**Dataset:** `urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)`
**Decision:** `BLOCK`
**Severity:** `CRITICAL`
**Evidence Coverage:** `85.0%`
**Evidence Trust:** `DEMO FIXTURE — NOT LIVE VERIFIED`

## Executive Summary
Proposed change to dataset 'raw_customers' modifies 1 field(s), including breaking change(s) to 'email'. Sentinel observed in the explicit demo scenario 4 confirmed downstream consumer(s) across DataHub lineage graph (DEMO_FIXTURE).

## Why It Matters
Altering column(s) 'email' risks breaking downstream analytical models and dashboards that reference this field. Impacted observed in the explicit demo scenario systems include Executive Dashboards and ML Feature Stores.
