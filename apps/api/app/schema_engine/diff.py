from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import datetime


class ChangeType(str, Enum):
    COLUMN_ADDED = "COLUMN_ADDED"
    COLUMN_REMOVED = "COLUMN_REMOVED"
    COLUMN_RENAMED = "COLUMN_RENAMED"
    TYPE_CHANGED = "TYPE_CHANGED"
    NULLABILITY_CHANGED = "NULLABILITY_CHANGED"


class SchemaField(BaseModel):
    name: str
    type: str
    nullable: bool = True
    description: Optional[str] = None


class DatasetIdentifier(BaseModel):
    urn: str
    platform: Optional[str] = "snowflake"
    name: str
    env: str = "PROD"


class SchemaSnapshot(BaseModel):
    dataset: DatasetIdentifier
    fields: List[SchemaField]


class SchemaChange(BaseModel):
    field: str
    change_type: ChangeType
    old_state: Optional[Dict[str, Any]] = None
    proposed_state: Optional[Dict[str, Any]] = None
    is_breaking: bool = False
    details: str


class ChangeSet(BaseModel):
    dataset_urn: str
    source: str = "manual"  # manual, github_pr, json_diff, sql_ddl
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    changes: List[SchemaChange]


class SchemaDiffEngine:
    """
    Deterministic Schema Diff Engine.
    Compares before and after SchemaSnapshots with strict semantic correctness.
    NEVER infers a column rename simply because a removed column and an added column share the same data type.
    Renames are recorded ONLY when explicitly declared in DDL or metadata mapping.
    """

    @staticmethod
    def diff(
        before: SchemaSnapshot,
        after: SchemaSnapshot,
        source: str = "manual",
        explicit_renames: Optional[Dict[str, str]] = None
    ) -> ChangeSet:
        before_fields: Dict[str, SchemaField] = {f.name.lower(): f for f in before.fields}
        after_fields: Dict[str, SchemaField] = {f.name.lower(): f for f in after.fields}
        renames = {k.lower(): v.lower() for k, v in (explicit_renames or {}).items()}

        changes: List[SchemaChange] = []

        removed_names = set(before_fields.keys()) - set(after_fields.keys())
        added_names = set(after_fields.keys()) - set(before_fields.keys())
        common_names = set(before_fields.keys()) & set(after_fields.keys())

        # 1. Process explicit renames first
        processed_renames: set = set()
        for r_name in list(removed_names):
            if r_name in renames and renames[r_name] in added_names:
                a_name = renames[r_name]
                b_field = before_fields[r_name]
                a_field = after_fields[a_name]

                changes.append(SchemaChange(
                    field=b_field.name,
                    change_type=ChangeType.COLUMN_RENAMED,
                    old_state={"name": b_field.name, "type": b_field.type, "nullable": b_field.nullable},
                    proposed_state={"name": a_field.name, "type": a_field.type, "nullable": a_field.nullable},
                    is_breaking=True,
                    details=f"Field '{b_field.name}' explicitly renamed to '{a_field.name}'"
                ))
                processed_renames.add(r_name)
                added_names.remove(a_name)

        removed_names -= processed_renames

        # 2. Record explicitly removed columns (never wrongly inferred as renames)
        for r_name in sorted(removed_names):
            f = before_fields[r_name]
            changes.append(SchemaChange(
                field=f.name,
                change_type=ChangeType.COLUMN_REMOVED,
                old_state={"name": f.name, "type": f.type, "nullable": f.nullable},
                proposed_state=None,
                is_breaking=True,
                details=f"Field '{f.name}' removed from dataset schema"
            ))

        # 3. Record newly added columns
        for a_name in sorted(added_names):
            f = after_fields[a_name]
            changes.append(SchemaChange(
                field=f.name,
                change_type=ChangeType.COLUMN_ADDED,
                old_state=None,
                proposed_state={"name": f.name, "type": f.type, "nullable": f.nullable},
                is_breaking=False,  # Additive change is non-breaking
                details=f"New field '{f.name}' added to dataset schema"
            ))

        # 4. Compare common columns for type and nullability modifications
        for c_name in sorted(common_names):
            b_field = before_fields[c_name]
            a_field = after_fields[c_name]

            # Type change
            if b_field.type.lower() != a_field.type.lower():
                changes.append(SchemaChange(
                    field=b_field.name,
                    change_type=ChangeType.TYPE_CHANGED,
                    old_state={"type": b_field.type},
                    proposed_state={"type": a_field.type},
                    is_breaking=True,
                    details=f"Type of field '{b_field.name}' changed from '{b_field.type}' to '{a_field.type}'"
                ))

            # Nullability change
            if b_field.nullable != a_field.nullable:
                # Making a column NOT NULL (nullable True -> False) is breaking
                is_breaking = (b_field.nullable is True and a_field.nullable is False)
                changes.append(SchemaChange(
                    field=b_field.name,
                    change_type=ChangeType.NULLABILITY_CHANGED,
                    old_state={"nullable": b_field.nullable},
                    proposed_state={"nullable": a_field.nullable},
                    is_breaking=is_breaking,
                    details=f"Nullability of field '{b_field.name}' changed from {b_field.nullable} to {a_field.nullable}"
                ))

        return ChangeSet(
            dataset_urn=before.dataset.urn,
            source=source,
            changes=changes
        )
