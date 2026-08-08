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
    source: str = "manual"  # manual, github_pr, json_diff
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    changes: List[SchemaChange]


class SchemaDiffEngine:
    @staticmethod
    def diff(before: SchemaSnapshot, after: SchemaSnapshot, source: str = "manual") -> ChangeSet:
        before_fields: Dict[str, SchemaField] = {f.name.lower(): f for f in before.fields}
        after_fields: Dict[str, SchemaField] = {f.name.lower(): f for f in after.fields}

        changes: List[SchemaChange] = []

        # Check removed fields or potential renames
        removed_names = set(before_fields.keys()) - set(after_fields.keys())
        added_names = set(after_fields.keys()) - set(before_fields.keys())
        common_names = set(before_fields.keys()) & set(after_fields.keys())

        # Simple rename detection heuristic: if 1 removed and 1 added with same type, check if it's a rename
        renamed_pairs: Dict[str, str] = {}
        for r_name in list(removed_names):
            r_field = before_fields[r_name]
            for a_name in list(added_names):
                a_field = after_fields[a_name]
                if r_field.type.lower() == a_field.type.lower() and r_field.nullable == a_field.nullable:
                    # Treat as candidate rename if names are somewhat similar or exact match in type
                    # For safety, if there's an explicit rename hint or 1-to-1 match:
                    renamed_pairs[r_name] = a_name
                    break

        # Record explicitly removed columns (not detected as renames)
        for r_name in sorted(removed_names):
            if r_name in renamed_pairs:
                a_name = renamed_pairs[r_name]
                changes.append(SchemaChange(
                    field=before_fields[r_name].name,
                    change_type=ChangeType.COLUMN_RENAMED,
                    old_state={"name": before_fields[r_name].name, "type": before_fields[r_name].type},
                    proposed_state={"name": after_fields[a_name].name, "type": after_fields[a_name].type},
                    is_breaking=True,
                    details=f"Field '{before_fields[r_name].name}' renamed to '{after_fields[a_name].name}'"
                ))
                added_names.remove(a_name)
            else:
                f = before_fields[r_name]
                changes.append(SchemaChange(
                    field=f.name,
                    change_type=ChangeType.COLUMN_REMOVED,
                    old_state={"name": f.name, "type": f.type, "nullable": f.nullable},
                    proposed_state=None,
                    is_breaking=True,
                    details=f"Field '{f.name}' removed from dataset"
                ))

        # Record newly added columns
        for a_name in sorted(added_names):
            f = after_fields[a_name]
            changes.append(SchemaChange(
                field=f.name,
                change_type=ChangeType.COLUMN_ADDED,
                old_state=None,
                proposed_state={"name": f.name, "type": f.type, "nullable": f.nullable},
                is_breaking=False,  # Additive change is non-breaking
                details=f"New field '{f.name}' added to dataset"
            ))

        # Compare common columns for type and nullability changes
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
                    details=f"Type of '{b_field.name}' changed from '{b_field.type}' to '{a_field.type}'"
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
                    details=f"Nullability of '{b_field.name}' changed from {b_field.nullable} to {a_field.nullable}"
                ))

        return ChangeSet(
            dataset_urn=before.dataset.urn,
            source=source,
            changes=changes
        )
