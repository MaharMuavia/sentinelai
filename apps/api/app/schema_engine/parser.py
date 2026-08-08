import sqlglot
from sqlglot.expressions import ColumnDef, Drop, Alter, Create, RenameColumn
from typing import Tuple, List, Optional, Dict, Any
from pydantic import BaseModel
from app.schema_engine.diff import SchemaSnapshot, DatasetIdentifier, SchemaField


class SchemaParseResult(BaseModel):
    success: bool
    error: Optional[str] = None
    before_snapshot: Optional[SchemaSnapshot] = None
    after_snapshot: Optional[SchemaSnapshot] = None
    explicit_renames: Dict[str, str] = {}


class SchemaParserEngine:
    """
    SQL DDL & Schema Parser Engine.
    Parses CREATE, ALTER, DROP, RENAME SQL statements using SQLGlot AST traversal.
    Does NOT depend on hardcoded base schemas.
    Returns structured parse results with explicit error details on malformed SQL.
    """

    @staticmethod
    def parse_sql_ddl_alter(
        ddl_statement: str,
        dataset_urn: str,
        base_schema: Optional[SchemaSnapshot] = None
    ) -> SchemaParseResult:
        dataset_id = DatasetIdentifier(
            urn=dataset_urn,
            name=dataset_urn.split(",")[-2] if "," in dataset_urn else dataset_urn
        )

        if not ddl_statement or not ddl_statement.strip():
            return SchemaParseResult(
                success=False,
                error="Empty DDL statement provided"
            )

        try:
            parsed = sqlglot.parse(ddl_statement, read="snowflake")
            if not parsed or not parsed[0]:
                return SchemaParseResult(
                    success=False,
                    error="SQLGlot failed to parse DDL statement (Empty AST)"
                )
            stmt = parsed[0]
        except Exception as e:
            return SchemaParseResult(
                success=False,
                error=f"SQL Syntax Error: {str(e)}"
            )

        # 1. Handle CREATE TABLE DDL
        if isinstance(stmt, Create):
            fields = []
            for col in stmt.find_all(ColumnDef):
                col_name = col.name
                col_kind = col.args.get("kind")
                type_str = col_kind.name.upper() if col_kind else "STRING"
                fields.append(SchemaField(
                    name=col_name,
                    type=type_str,
                    nullable=True
                ))

            after_snap = SchemaSnapshot(dataset=dataset_id, fields=fields)
            before_snap = base_schema or SchemaSnapshot(dataset=dataset_id, fields=[])
            return SchemaParseResult(
                success=True,
                before_snapshot=before_snap,
                after_snapshot=after_snap
            )

        # 2. Handle ALTER TABLE DDL
        elif isinstance(stmt, Alter):
            # Base snapshot must be provided or defaults to empty (no hardcoding)
            before_snap = base_schema or SchemaSnapshot(dataset=dataset_id, fields=[])
            after_fields = list(before_snap.fields)
            explicit_renames: Dict[str, str] = {}

            # Check for DROP COLUMN
            drops = list(stmt.find_all(Drop))
            for drop in drops:
                if drop.args.get("kind") == "COLUMN":
                    dropped_col = drop.this.name.lower()
                    after_fields = [f for f in after_fields if f.name.lower() != dropped_col]

            # Check for RENAME COLUMN
            renames = list(stmt.find_all(RenameColumn))
            for r in renames:
                old_col = r.this.name
                new_col = r.to.name
                explicit_renames[old_col] = new_col

                new_fields = []
                for f in after_fields:
                    if f.name.lower() == old_col.lower():
                        new_fields.append(SchemaField(name=new_col, type=f.type, nullable=f.nullable, description=f.description))
                    else:
                        new_fields.append(f)
                after_fields = new_fields

            # Check for ADD COLUMN
            for col in stmt.find_all(ColumnDef):
                added_col = col.name
                col_kind = col.args.get("kind")
                added_type = col_kind.name.upper() if col_kind else "STRING"
                # Avoid duplicate addition if already present
                if not any(f.name.lower() == added_col.lower() for f in after_fields):
                    after_fields.append(SchemaField(name=added_col, type=added_type, nullable=True))

            after_snap = SchemaSnapshot(dataset=dataset_id, fields=after_fields)
            return SchemaParseResult(
                success=True,
                before_snapshot=before_snap,
                after_snapshot=after_snap,
                explicit_renames=explicit_renames
            )

        else:
            return SchemaParseResult(
                success=False,
                error=f"Unsupported DDL statement type '{type(stmt).__name__}'. Sentinel supports CREATE TABLE and ALTER TABLE DDL."
            )
