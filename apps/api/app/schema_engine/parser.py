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
    snapshot: Optional[SchemaSnapshot] = None
    explicit_renames: Dict[str, str] = {}


class SchemaParserEngine:
    """
    SQL DDL & Schema Parser Engine.
    Parses CREATE, ALTER, DROP, RENAME SQL statements using SQLGlot AST traversal.
    Mandates base schema context for ALTER operations to prevent bogus empty table states.
    Returns structured parse results with explicit error details on malformed SQL.
    """

    @staticmethod
    def parse_create_table(sql: str, dataset_name: str, dataset_urn: str) -> SchemaParseResult:
        """Parse CREATE TABLE statement into SchemaSnapshot."""
        if not sql or not sql.strip():
            return SchemaParseResult(success=False, error="Empty SQL DDL string")

        dataset_id = DatasetIdentifier(urn=dataset_urn, name=dataset_name)
        try:
            parsed = sqlglot.parse(sql, read="snowflake")
            if not parsed or not parsed[0]:
                return SchemaParseResult(success=False, error="Empty SQL AST")
            stmt = parsed[0]
            if isinstance(stmt, Create):
                fields = []
                for col in stmt.find_all(ColumnDef):
                    col_name = col.name
                    col_kind = col.args.get("kind")
                    type_str = col_kind.name.upper() if col_kind else "STRING"
                    fields.append(SchemaField(name=col_name, type=type_str, nullable=True))
                snap = SchemaSnapshot(dataset=dataset_id, fields=fields)
                return SchemaParseResult(success=True, snapshot=snap, after_snapshot=snap)
        except Exception as e:
            return SchemaParseResult(success=False, error=f"SQL Syntax Error: {str(e)}")

        return SchemaParseResult(success=False, error="Statement is not a CREATE TABLE DDL")

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
                after_snapshot=after_snap,
                snapshot=after_snap
            )

        # 2. Handle ALTER TABLE DDL
        elif isinstance(stmt, Alter):
            if not base_schema or not base_schema.fields:
                return SchemaParseResult(
                    success=False,
                    error="INSUFFICIENT_SCHEMA_CONTEXT: Base schema is mandatory for ALTER TABLE DDL processing. Retrieve current catalog schema from DataHub first."
                )

            before_snap = base_schema
            after_fields = list(before_snap.fields)
            explicit_renames: Dict[str, str] = {}

            # Check for DROP COLUMN
            drops = list(stmt.find_all(Drop))
            for drop in drops:
                if drop.args.get("kind") == "COLUMN":
                    dropped_col = drop.this.name.lower()
                    if not any(f.name.lower() == dropped_col for f in after_fields):
                        return SchemaParseResult(success=False, error=f"Cannot drop missing column '{drop.this.name}'")
                    after_fields = [f for f in after_fields if f.name.lower() != dropped_col]

            # Check for RENAME COLUMN
            renames = list(stmt.find_all(RenameColumn))
            for r in renames:
                old_col = r.this.name
                new_col = r.args["to"].name
                if not any(f.name.lower() == old_col.lower() for f in after_fields):
                    return SchemaParseResult(success=False, error=f"Cannot rename missing column '{old_col}'")
                if any(f.name.lower() == new_col.lower() for f in after_fields):
                    return SchemaParseResult(success=False, error=f"Cannot rename '{old_col}' to existing column '{new_col}'")
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
                if not any(f.name.lower() == added_col.lower() for f in after_fields):
                    after_fields.append(SchemaField(name=added_col, type=added_type, nullable=True))

            after_snap = SchemaSnapshot(dataset=dataset_id, fields=after_fields)
            return SchemaParseResult(
                success=True,
                before_snapshot=before_snap,
                after_snapshot=after_snap,
                snapshot=after_snap,
                explicit_renames=explicit_renames
            )

        else:
            return SchemaParseResult(
                success=False,
                error=f"Unsupported DDL statement type '{type(stmt).__name__}'. Sentinel supports CREATE TABLE and ALTER TABLE DDL."
            )


# Alias for compatibility
DDLParser = SchemaParserEngine
