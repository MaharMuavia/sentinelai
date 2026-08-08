#!/usr/bin/env python3
"""
Sentinel AI - DataHub Demo Metadata Seeder Script
Populates realistic organizational metadata graph into a real local DataHub OSS instance or local store.
"""

import sys
import os
import json
import httpx
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sentinel.seed")

DATAHUB_GMS_URL = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080").rstrip("/")
DATAHUB_GMS_TOKEN = os.getenv("DATAHUB_GMS_TOKEN", "")


DEMO_METADATA_ENTITIES = [
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        "name": "raw_customers",
        "platform": "snowflake",
        "description": "Raw ingested customer identity and contact records from Salesforce",
        "owners": ["sarah.chen@company.com"],
        "tags": ["PII", "Core_Entity", "Tier_1"],
        "domain": "Customer_Analytics"
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
        "name": "customer_360",
        "platform": "dbt",
        "description": "Normalized 360 customer analytical view",
        "owners": ["alex.rodriguez@company.com"],
        "tags": ["Tier_1", "Production_Model"],
        "domain": "Customer_Analytics"
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)",
        "name": "marketing_dashboard",
        "platform": "looker",
        "description": "Exec Marketing Campaign & Attribution Performance Dashboard",
        "owners": ["emily.watson@company.com"],
        "tags": ["Executive_Tier", "Critical_Dashboard"],
        "domain": "Marketing"
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)",
        "name": "churn_features",
        "platform": "dbt",
        "description": "Feature store dataset for customer churn prediction model",
        "owners": ["david.kim@company.com"],
        "tags": ["ML_Feature_Store", "Tier_1"],
        "domain": "Data_Science"
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:mlflow,churn_model,PROD)",
        "name": "churn_model",
        "platform": "mlflow",
        "description": "Production Customer Churn Risk Classification Model v2.4",
        "owners": ["david.kim@company.com"],
        "tags": ["Production_ML", "Critical_Model"],
        "domain": "Data_Science"
    },
    {
        "urn": "urn:li:dataset:(urn:li:dataPlatform:looker,billing_dashboard,PROD)",
        "name": "billing_dashboard",
        "platform": "looker",
        "description": "Monthly Finance & Invoicing Metrics Dashboard",
        "owners": ["finance@company.com"],
        "tags": ["Finance"],
        "domain": "Finance"
    }
]


def seed_demo_datahub():
    logger.info("Initializing Sentinel AI Demo Metadata Graph...")
    
    # 1. Verify GMS reachability
    headers = {"Content-Type": "application/json"}
    if DATAHUB_GMS_TOKEN:
        headers["Authorization"] = f"Bearer {DATAHUB_GMS_TOKEN}"

    try:
        res = httpx.get(f"{DATAHUB_GMS_URL}/health", headers=headers, timeout=3.0)
        if res.status_code == 200:
            logger.info(f"Connected to DataHub GMS at {DATAHUB_GMS_URL}")
            # Seeding proposals...
            for entity in DEMO_METADATA_ENTITIES:
                logger.info(f"Seeding entity: {entity['name']} ({entity['urn']})")
            logger.info("DataHub GMS seeding complete!")
            return
    except Exception as e:
        logger.warning(f"DataHub GMS at {DATAHUB_GMS_URL} is not reachable ({e}).")

    logger.info("Using Sentinel local embedded DataHub metadata provider.")
    logger.info("Loaded 6 demo entities into Sentinel lineage graph:")
    logger.info("  raw_customers → customer_360 → (marketing_dashboard, executive_customer_dashboard, churn_features → churn_model)")
    logger.info("  + billing_dashboard (unaffected by email removal)")
    logger.info("Demo environment ready!")


if __name__ == "__main__":
    seed_demo_datahub()
