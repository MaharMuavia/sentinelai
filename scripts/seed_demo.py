#!/usr/bin/env python3
"""
Sentinel AI — DataHub Canonical Demo Seeder
Seeds the canonical DataHub demo metadata graph using the official DataHub REST emitter.
Fails loudly with exit code 1 if GMS is offline or ingestion fails.
"""

import sys
import os
import logging
import time
from pathlib import Path
from typing import List

from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.emitter.mcp import MetadataChangeProposalWrapper
import datahub.metadata.schema_classes as models
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinel.seed")


def seed_demo_graph():
    gms_url = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080").rstrip("/")
    token = os.getenv("DATAHUB_SEED_TOKEN") or os.getenv("DATAHUB_GMS_TOKEN", "")

    logger.info(f"Connecting to DataHub GMS at {gms_url}...")
    emitter = DatahubRestEmitter(gms_server=gms_url, token=token if token else None)

    try:
        emitter.test_connection()
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
    demo_query_urn = "urn:li:query:sentinel_demo_customer_email_usage"

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

    schema_c360 = models.SchemaMetadataClass(
        schemaName="customer_360", platform="urn:li:dataPlatform:dbt", version=0, hash="",
        platformSchema=models.OtherSchemaClass(rawSchema=""),
        fields=[
            models.SchemaFieldClass(fieldPath="customer_id", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="VARCHAR", nullable=False),
            models.SchemaFieldClass(fieldPath="email", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="VARCHAR", nullable=True),
            models.SchemaFieldClass(fieldPath="country", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="VARCHAR", nullable=True),
            models.SchemaFieldClass(fieldPath="lifetime_value", type=models.SchemaFieldDataTypeClass(type=models.NumberTypeClass()), nativeDataType="NUMBER", nullable=True),
        ],
    )
    schema_churn = models.SchemaMetadataClass(
        schemaName="churn_features", platform="urn:li:dataPlatform:dbt", version=0, hash="",
        platformSchema=models.OtherSchemaClass(rawSchema=""),
        fields=[
            models.SchemaFieldClass(fieldPath="customer_id", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="VARCHAR", nullable=False),
            models.SchemaFieldClass(fieldPath="email_domain", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="VARCHAR", nullable=True),
            models.SchemaFieldClass(fieldPath="churn_score", type=models.SchemaFieldDataTypeClass(type=models.NumberTypeClass()), nativeDataType="NUMBER", nullable=True),
        ],
    )
    mcps.extend([
        MetadataChangeProposalWrapper(entityUrn=customer_360_urn, aspect=schema_c360),
        MetadataChangeProposalWrapper(entityUrn=churn_features_urn, aspect=schema_churn),
    ])

    # A real Query entity makes MCP query-usage evidence testable without
    # pretending the seeded demo represents organic production traffic.
    now_millis = int(time.time() * 1000)
    audit_stamp = models.AuditStampClass(
        time=now_millis,
        actor="urn:li:corpuser:sentinel_demo",
    )
    mcps.extend([
        MetadataChangeProposalWrapper(
            entityUrn=demo_query_urn,
            aspect=models.QueryPropertiesClass(
                statement=models.QueryStatementClass(
                    value="SELECT customer_id, email FROM raw_customers WHERE email IS NOT NULL",
                    language=models.QueryLanguageClass.SQL,
                ),
                source=models.QuerySourceClass.SYSTEM,
                created=audit_stamp,
                lastModified=audit_stamp,
                name="Sentinel canonical email-impact query",
                description="Explicitly seeded query for the Sentinel hackathon acceptance dataset",
                origin="sentinel-demo-seed",
            ),
        ),
        MetadataChangeProposalWrapper(
            entityUrn=demo_query_urn,
            aspect=models.QuerySubjectsClass(
                subjects=[
                    models.QuerySubjectClass(entity=raw_customers_urn),
                    models.QuerySubjectClass(
                        entity=f"urn:li:schemaField:({raw_customers_urn},email)"
                    ),
                ]
            ),
        ),
    ])

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

    lineage_churn = models.UpstreamLineageClass(
        upstreams=[models.UpstreamClass(dataset=raw_customers_urn, type=models.DatasetLineageTypeClass.TRANSFORMED)],
        fineGrainedLineages=[models.FineGrainedLineageClass(
            upstreamType=models.FineGrainedLineageUpstreamTypeClass.FIELD_SET,
            upstreams=["urn:li:schemaField:(" + raw_customers_urn + ",email)"],
            downstreamType=models.FineGrainedLineageDownstreamTypeClass.FIELD,
            downstreams=["urn:li:schemaField:(" + churn_features_urn + ",email_domain)"],
        )],
    )
    lineage_model = models.UpstreamLineageClass(
        upstreams=[models.UpstreamClass(dataset=churn_features_urn, type=models.DatasetLineageTypeClass.TRANSFORMED)]
    )
    mcps.extend([
        MetadataChangeProposalWrapper(entityUrn=churn_features_urn, aspect=lineage_churn),
        MetadataChangeProposalWrapper(entityUrn=churn_model_urn, aspect=lineage_model),
    ])

    # Metadata for every important consumer is seeded explicitly; the verifier
    # can therefore distinguish missing live metadata from a fixture default.
    mcps.extend([
        MetadataChangeProposalWrapper(entityUrn=customer_360_urn, aspect=models.DatasetPropertiesClass(description="Customer 360 derived model", customProperties={"domain": "Customer_Analytics"})),
        MetadataChangeProposalWrapper(entityUrn=customer_360_urn, aspect=models.OwnershipClass(owners=[models.OwnerClass(owner="urn:li:corpuser:alex_lead", type=models.OwnershipTypeClass.TECHNICAL_OWNER)])),
        MetadataChangeProposalWrapper(entityUrn=customer_360_urn, aspect=models.GlobalTagsClass(tags=[models.TagAssociationClass(tag="urn:li:tag:Tier_1")])),
        MetadataChangeProposalWrapper(entityUrn=churn_features_urn, aspect=models.DatasetPropertiesClass(description="Churn model feature dataset", customProperties={"domain": "Data_Science"})),
        MetadataChangeProposalWrapper(entityUrn=churn_features_urn, aspect=models.OwnershipClass(owners=[models.OwnerClass(owner="urn:li:corpuser:david_ml", type=models.OwnershipTypeClass.TECHNICAL_OWNER)])),
        MetadataChangeProposalWrapper(entityUrn=churn_features_urn, aspect=models.GlobalTagsClass(tags=[models.TagAssociationClass(tag="urn:li:tag:Tier_1")])),
        MetadataChangeProposalWrapper(entityUrn=churn_model_urn, aspect=models.DatasetPropertiesClass(description="Customer churn model", customProperties={"domain": "Data_Science"})),
        MetadataChangeProposalWrapper(entityUrn=churn_model_urn, aspect=models.OwnershipClass(owners=[models.OwnerClass(owner="urn:li:corpuser:david_ml", type=models.OwnershipTypeClass.TECHNICAL_OWNER)])),
        MetadataChangeProposalWrapper(entityUrn=churn_model_urn, aspect=models.GlobalTagsClass(tags=[models.TagAssociationClass(tag="urn:li:tag:Production_ML")])),
    ])

    # Tags for marketing_dashboard
    tags_mkt = models.GlobalTagsClass(
        tags=[
            models.TagAssociationClass(tag="urn:li:tag:Executive_Tier"),
            models.TagAssociationClass(tag="urn:li:tag:Critical_Dashboard")
        ]
    )
    mcps.append(MetadataChangeProposalWrapper(entityUrn=marketing_dashboard_urn, aspect=tags_mkt))

    # Emit all proposals to DataHub GMS
    mcps.extend([
        MetadataChangeProposalWrapper(entityUrn="urn:li:tag:Sentinel_BLOCK", aspect=models.TagPropertiesClass(name="Sentinel_BLOCK", description="Sentinel pre-merge policy block")),
        MetadataChangeProposalWrapper(entityUrn="urn:li:tag:Sentinel_SAFE_TO_MERGE", aspect=models.TagPropertiesClass(name="Sentinel_SAFE_TO_MERGE", description="Sentinel verified safe additive change")),
    ])
    success_count = 0
    for mcp in mcps:
        try:
            emitter.emit(mcp)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to emit proposal for {mcp.entityUrn}: {e}")
            if mcp.entityUrn.startswith("urn:li:query:"):
                logger.error(
                    "Query entities require an ingestion/admin seed credential. "
                    "Set DATAHUB_SEED_TOKEN for this one-time operation; do not use it as the runtime token."
                )
            sys.exit(1)

    logger.info(f"Successfully seeded {success_count}/{len(mcps)} DataHub metadata aspects!")


if __name__ == "__main__":
    seed_demo_graph()
