import datahub.emitter.rest_emitter as rest_emitter
import datahub.metadata.schema_classes as models
import argparse

def ingest(gms_url, token):
    emitter = rest_emitter.DatahubRestEmitter(gms_server=gms_url, token=token)
    
    # 7 datasets
    datasets = [
        "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
        "urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)",
        "urn:li:dataset:(urn:li:dataPlatform:looker,executive_customer_dashboard,PROD)",
        "urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)",
        "urn:li:dataset:(urn:li:dataPlatform:mlflow,churn_model,PROD)",
        "urn:li:dataset:(urn:li:dataPlatform:looker,billing_dashboard,PROD)"
    ]

    for d in datasets:
        print(f"Ingesting {d}")
        # Properties
        prop = models.DatasetPropertiesClass(
            name=d.split(",")[1],
            description=f"Description for {d}"
        )
        emitter.emit_mcp(models.MetadataChangeProposalWrapper(
            entityUrn=d,
            aspect=prop
        ))
        
        # Tags
        tags = models.GlobalTagsClass(tags=[
            models.TagAssociationClass(tag="urn:li:tag:PII"),
            models.TagAssociationClass(tag="urn:li:tag:Core_Entity"),
            models.TagAssociationClass(tag="urn:li:tag:Tier_1")
        ])
        emitter.emit_mcp(models.MetadataChangeProposalWrapper(
            entityUrn=d,
            aspect=tags
        ))
        
        # Ownership
        owners = models.OwnershipClass(owners=[
            models.OwnerClass(owner="urn:li:corpuser:admin", type="TECHNICAL_OWNER")
        ])
        emitter.emit_mcp(models.MetadataChangeProposalWrapper(
            entityUrn=d,
            aspect=owners
        ))
        
        # Schema
        schema = models.SchemaMetadataClass(
            schemaName="default",
            platform=d.split(",")[0].replace("urn:li:dataset:(", ""),
            version=1,
            hash="",
            platformSchema=models.OtherSchemaClass(rawSchema=""),
            fields=[
                models.SchemaFieldClass(fieldPath="customer_id", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="STRING"),
                models.SchemaFieldClass(fieldPath="email", type=models.SchemaFieldDataTypeClass(type=models.StringTypeClass()), nativeDataType="STRING"),
            ]
        )
        emitter.emit_mcp(models.MetadataChangeProposalWrapper(
            entityUrn=d,
            aspect=schema
        ))
        
    print("Ingestion complete")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gms-url", default="http://localhost:8080")
    parser.add_argument("--gms-token", default="")
    args = parser.parse_args()
    ingest(args.gms_url, args.gms_token)
