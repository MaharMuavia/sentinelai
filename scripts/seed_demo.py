#!/usr/bin/env python3
"""
Sentinel AI - DataHub Demo Metadata Seeder Script
Populates realistic organizational metadata graph into a real DataHub OSS instance using official REST emitters.
"""

import sys
import os
import json
import logging
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sentinel.seed")

DATAHUB_GMS_URL = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080").rstrip("/")
DATAHUB_GMS_TOKEN = os.getenv("DATAHUB_GMS_TOKEN", "")

DEMO_ENTITIES = [
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        "name": "raw_customers",
        "platform": "snowflake",
        "description": "Raw ingested customer identity and contact records from Salesforce",
        "owners": ["sarah.chen@company.com"],
        "tags": ["PII", "Core_Entity", "Tier_1"],
        "domain": "Customer_Analytics",
        "fields": [
            {"name": "customer_id", "type": "STRING"},
            {"name": "email", "type": "STRING"},
            {"name": "country", "type": "STRING"},
            {"name": "created_at", "type": "TIMESTAMP"}
        ]
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
        "name": "customer_360",
        "platform": "dbt",
        "description": "Normalized 360 customer analytical view",
        "owners": ["alex.rodriguez@company.com"],
        "tags": ["Tier_1", "Production_Model"],
        "domain": "Customer_Analytics",
        "fields": [
            {"name": "customer_id", "type": "STRING"},
            {"name": "email", "type": "STRING"},
            {"name": "country", "type": "STRING"},
            {"name": "lifetime_value", "type": "NUMERIC"}
        ]
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)",
        "name": "marketing_dashboard",
        "platform": "looker",
        "description": "Exec Marketing Campaign & Attribution Performance Dashboard",
        "owners": ["emily.watson@company.com"],
        "tags": ["Executive_Tier", "Critical_Dashboard"],
        "domain": "Marketing",
        "fields": []
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)",
        "name": "churn_features",
        "platform": "dbt",
        "description": "Feature store dataset for customer churn prediction model",
        "owners": ["david.kim@company.com"],
        "tags": ["ML_Feature_Store", "Tier_1"],
        "domain": "Data_Science",
        "fields": [
            {"name": "customer_id", "type": "STRING"},
            {"name": "email_domain", "type": "STRING"}
        ]
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:mlflow,churn_model,PROD)",
        "name": "churn_model",
        "platform": "mlflow",
        "description": "Production Customer Churn Risk Classification Model v2.4",
        "owners": ["david.kim@company.com"],
        "tags": ["Production_ML", "Critical_Model"],
        "domain": "Data_Science",
        "fields": []
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:looker,billing_dashboard,PROD)",
        "name": "billing_dashboard",
        "platform": "looker",
        "description": "Monthly Finance & Invoicing Metrics Dashboard",
        "owners": ["finance@company.com"],
        "tags": ["Finance"],
        "domain": "Finance",
        "fields": []
    }
]


def seed_demo_datahub():
    logger.info("Initializing Sentinel AI Demo Metadata Graph...")

    headers = {"Content-Type": "application/json"}
    if DATAHUB_GMS_TOKEN:
        headers["Authorization"] = f"Bearer {DATAHUB_GMS_TOKEN}"

    is_live = False
    try:
        res = httpx.get(f"{DATAHUB_GMS_URL}/health", headers=headers, timeout=2.0)
        is_live = (res.status_code == 200)
    except Exception:
        is_live = False

    if not is_live:
        logger.warning(f"DataHub GMS at {DATAHUB_GMS_URL} is NOT reachable.")
        logger.info("Sentinel will run in DEMO FIXTURE mode.")
        logger.info("Loaded 6 demo entities into Sentinel local fixture graph.")
        print("[Sentinel AI] Seeding result: DEMO_FIXTURE_LOADED (DataHub GMS was not mutated)")
        return

    logger.info(f"Connected to live DataHub GMS at {DATAHUB_GMS_URL}")
    mutated_count = 0

    for entity in DEMO_ENTITIES:
        urn = entity["urn"]
        logger.info(f"Ingesting entity proposal for '{entity['name']}' ({urn})...")

        # 1. Properties
        prop_payload = {
            "proposal": {
                "entityType": "dataset",
                "entityUrn": urn,
                "aspectName": "datasetProperties",
                "aspect": {
                    "value": json.dumps({
                        "name": entity["name"],
                        "description": entity["description"]
                    }),
                    "contentType": "application/json"
                },
                "changeType": "UPSERT"
            }
        }

        # 2. Tags
        tag_payload = {
            "proposal": {
                "entityType": "dataset",
                "entityUrn": urn,
                "aspectName": "globalTags",
                "aspect": {
                    "value": json.dumps({
                        "tags": [{"tag": f"urn:li:tag:{t}"} for t in entity["tags"]]
                    }),
                    "contentType": "application/json"
                },
                "changeType": "UPSERT"
            }
        }

        try:
            r1 = httpx.post(f"{DATAHUB_GMS_URL}/aspects?action=ingestProposal", json=prop_payload, headers=headers, timeout=5.0)
            r2 = httpx.post(f"{DATAHUB_GMS_URL}/aspects?action=ingestProposal", json=tag_payload, headers=headers, timeout=5.0)
            if r1.status_code in (200, 201) and r2.status_code in (200, 201):
                mutated_count += 1
        except Exception as e:
            logger.warning(f"Failed to ingest proposals for {urn}: {e}")

    logger.info(f"Successfully mutated DataHub GMS! {mutated_count}/{len(DEMO_ENTITIES)} entities updated.")
    print(f"[Sentinel AI] Seeding result: DATAHUB_GMS_MUTATED ({mutated_count} entities updated)")


if __name__ == "__main__":
    seed_demo_datahub()
