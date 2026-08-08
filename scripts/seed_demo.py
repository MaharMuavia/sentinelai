#!/usr/bin/env python3
"""
Sentinel AI — DataHub Canonical Demo Seeder
Seeds the canonical DataHub demo metadata graph using the official DataHub REST emitter.
Fails loudly with exit code 1 if GMS is offline or ingestion fails.
"""

import sys
import os
import logging
from typing import List

from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.emitter.mcp import MetadataChangeProposalWrapper
import datahub.metadata.schema_classes as models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel.seed")


def seed_demo_graph():
    gms_url = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080").rstrip("/")
    token = os.getenv("DATAHUB_GMS_TOKEN", "")

    logger.info(f"Connecting to DataHub GMS at {gms_url}...")
    emitter = DatahubRestEmitter(gms_server=gms_url, token=token if token else None)

    try:
        if not emitter.test_connection():
            logger.error("DataHub GMS connection test failed! Cannot seed demo metadata.")
            sys.exit(1)
    except Exception as e:
        logger.error(f"DataHub GMS connection error: {e}")
        sys.exit(1)

    mcps: List[MetadataChangeProposalWrapper] = []

    # 1. Dataset Schemas
    raw_customers_urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    customer_360_urn = "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)"
    marketing_dashboard_urn = "urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)"
    churn_features_urn = "urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)"
    churn_model_urn = "urn:li:dataset:(urn:li:dataPlatform:mlflow,churn_model,PROD)"

    # Schema Aspect for raw_customers
    schema_raw = models.SchemaMetadataClass(
        schemaName="raw_customers",
        platform="urn:li:dataPlatform:snowflake",
        version=0,
        hash="",
        platformSchema=models.OtherSchemaClass(rawSchema=""),
        fields=[
            models.SchemaFieldClass(fieldPath="customer_id", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="STRING", nullable=False, description="Primary customer key"),
            models.SchemaFieldClass(fieldPath="email", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="STRING", nullable=True, description="Customer primary email address"),
            models.SchemaFieldClass(fieldPath="country", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="STRING", nullable=True, description="ISO country code"),
            models.SchemaFieldClass(fieldPath="created_at", type=models.SchemaFieldDataTypeClass(type=models.TimeTypeClass()), nativeDataType="TIMESTAMP", nullable=False, description="Record creation timestamp"),
        ]
    )
    mcps.append(MetadataChangeProposalWrapper(entityUrn=raw_customers_urn, aspect=schema_raw))

    # Properties Aspect
    prop_raw = models.DatasetPropertiesClass(
        description="Raw ingested customer identity and contact records from Salesforce",
        customProperties={"tier": "1", "domain": "Customer_Analytics", "environment": "PROD"}
    )
    mcps.append(MetadataChangeProposalWrapper(entityUrn=raw_customers_urn, aspect=prop_raw))

    # Ownership Aspect
    owners_raw = models.OwnershipClass(
        owners=[
            models.OwnerClass(owner="urn:li:corpuser:sarah_chen", type=models.OwnershipTypeClass.TECHNICAL_OWNER)
        ]
    )
    mcps.append(MetadataChangeProposalWrapper(entityUrn=raw_customers_urn, aspect=owners_raw))

    # Tags Aspect
    tags_raw = models.GlobalTagsClass(
        tags=[
            models.TagAssociationClass(tag="urn:li:tag:PII"),
            models.TagAssociationClass(tag="urn:li:tag:Tier_1")
        ]
    )
    mcps.append(MetadataChangeProposalWrapper(entityUrn=raw_customers_urn, aspect=tags_raw))

    # Upstream Lineage (customer_360 -> raw_customers)
    lineage_c360 = models.UpstreamLineageClass(
        upstreams=[
            models.UpstreamClass(
                dataset=raw_customers_urn,
                type=models.DatasetLineageTypeClass.TRANSFORMED
            )
        ],
        fineGrainedLineages=[
            models.FineGrainedLineageClass(
                upstreamType=models.FineGrainedLineageUpstreamTypeClass.FIELD_SET,
                upstreams=["urn:li:schemaField:(" + raw_customers_urn + ",email)"],
                downstreamType=models.FineGrainedLineageDownstreamTypeClass.FIELD,
                downstreams=["urn:li:schemaField:(" + customer_360_urn + ",email)"]
            )
        ]
    )
    mcps.append(MetadataChangeProposalWrapper(entityUrn=customer_360_urn, aspect=lineage_c360))

    # Lineage for marketing_dashboard -> customer_360
    lineage_mkt = models.UpstreamLineageClass(
        upstreams=[
            models.UpstreamClass(
                dataset=customer_360_urn,
                type=models.DatasetLineageTypeClass.TRANSFORMED
            )
        ],
        fineGrainedLineages=[
            models.FineGrainedLineageClass(
                upstreamType=models.FineGrainedLineageUpstreamTypeClass.FIELD_SET,
                upstreams=["urn:li:schemaField:(" + customer_360_urn + ",email)"],
                downstreamType=models.FineGrainedLineageDownstreamTypeClass.FIELD,
                downstreams=["urn:li:schemaField:(" + marketing_dashboard_urn + ",customer_email)"]
            )
        ]
    )
    mcps.append(MetadataChangeProposalWrapper(entityUrn=marketing_dashboard_urn, aspect=lineage_mkt))

    # Tags for marketing_dashboard
    tags_mkt = models.GlobalTagsClass(
        tags=[
            models.TagAssociationClass(tag="urn:li:tag:Executive_Tier"),
            models.TagAssociationClass(tag="urn:li:tag:Critical_Dashboard")
        ]
    )
    mcps.append(MetadataChangeProposalWrapper(entityUrn=marketing_dashboard_urn, aspect=tags_mkt))

    # Emit all proposals to DataHub GMS
    success_count = 0
    for mcp in mcps:
        try:
            emitter.emit(mcp)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to emit proposal for {mcp.entityUrn}: {e}")
            sys.exit(1)

    logger.info(f"Successfully seeded {success_count}/{len(mcps)} DataHub metadata aspects!")


if __name__ == "__main__":
    seed_demo_graph()
