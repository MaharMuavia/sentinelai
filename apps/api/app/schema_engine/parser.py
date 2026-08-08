import sqlglot
from sqlglot.expressions import ColumnDef, Drop, Alter, Create
from typing import Tuple, List, Optional
from app.schema_engine.diff import SchemaSnapshot, DatasetIdentifier, SchemaField


class SchemaParserEngine:
    @staticmethod
    def parse_sql_ddl_alter(
        ddl_statement: str,
        dataset_urn: str = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    ) -> Tuple[SchemaSnapshot, SchemaSnapshot]:
        """Parse raw SQL DDL statement (e.g. ALTER TABLE ... DROP COLUMN) into before and after SchemaSnapshots."""

        # Base snapshot fallback
        base_fields = [
            SchemaField(name="customer_id", type="STRING", nullable=False, description="Unique customer key"),
            SchemaField(name="email", type="STRING", nullable=True, description="Customer email address"),
            SchemaField(name="country", type="STRING", nullable=True, description="ISO country code"),
            SchemaField(name="created_at", type="TIMESTAMP", nullable=False, description="Account creation timestamp")
        ]
        
        dataset_id = DatasetIdentifier(urn=dataset_urn, name=dataset_urn.split(",")[-2] if "," in dataset_urn else dataset_urn)

        try:
            parsed = sqlglot.parse(ddl_statement)
            if not parsed:
                return SchemaSnapshot(dataset=dataset_id, fields=base_fields), SchemaSnapshot(dataset=dataset_id, fields=base_fields)

            stmt = parsed[0]
            
            if isinstance(stmt, Create):
                fields = []
                for col in stmt.find_all(ColumnDef):
                    fields.append(SchemaField(
                        name=col.name,
                        type=col.args.get("kind").name.upper() if col.args.get("kind") else "STRING",
                        nullable=True
                    ))
                return SchemaSnapshot(dataset=dataset_id, fields=fields), SchemaSnapshot(dataset=dataset_id, fields=fields)
                
            elif isinstance(stmt, Alter):
                before_snapshot = SchemaSnapshot(dataset=dataset_id, fields=base_fields)
                after_fields = list(base_fields)
                
                # Check for drop
                drops = list(stmt.find_all(Drop))
                for drop in drops:
                    if drop.args.get("kind") == "COLUMN":
                        dropped_col = drop.this.name.lower()
                        after_fields = [f for f in after_fields if f.name.lower() != dropped_col]
                        
                # Check for add
                for col in stmt.find_all(ColumnDef):
                    # In AlterTable ADD, ColumnDef is directly under it
                    added_col = col.name
                    added_type = col.args.get("kind").name.upper() if col.args.get("kind") else "STRING"
                    after_fields.append(SchemaField(name=added_col, type=added_type, nullable=True))
                    
                return before_snapshot, SchemaSnapshot(dataset=dataset_id, fields=after_fields)
                
        except Exception:
            pass
            
        before_snapshot = SchemaSnapshot(dataset=dataset_id, fields=base_fields)
        return before_snapshot, before_snapshot

