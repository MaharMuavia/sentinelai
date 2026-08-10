from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import datetime
import re


class ChangeType(str, Enum):
    COLUMN_ADDED = "COLUMN_ADDED"
    COLUMN_REMOVED = "COLUMN_REMOVED"
    COLUMN_RENAMED = "COLUMN_RENAMED"
    TYPE_CHANGED = "TYPE_CHANGED"
    NULLABILITY_CHANGED = "NULLABILITY_CHANGED"


class SchemaField(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    type: Optional[str] = Field(default=None, max_length=256)
    nullable: bool = True
    description: Optional[str] = Field(default=None, max_length=4096)


class DatasetIdentifier(BaseModel):
    urn: str = Field(min_length=1, max_length=2048)
    platform: Optional[str] = Field(default=None, max_length=128)
    name: str = Field(min_length=1, max_length=512)
    env: str = Field(default="PROD", min_length=1, max_length=64)


class SchemaSnapshot(BaseModel):
    dataset: DatasetIdentifier
    fields: List[SchemaField] = Field(max_length=10_000)


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
    Ensures before/after snapshots match the same target dataset.
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
        if before.dataset.urn.lower() != after.dataset.urn.lower():
            raise ValueError(f"Dataset URN mismatch in schema diff: '{before.dataset.urn}' vs '{after.dataset.urn}'")

        before_fields: Dict[str, SchemaField] = {}
        for f in before.fields:
            if f.name.lower() in before_fields:
                raise ValueError(f"Duplicate case-insensitive field name '{f.name}' in before schema snapshot")
            before_fields[f.name.lower()] = f

        after_fields: Dict[str, SchemaField] = {}
        for f in after.fields:
            if f.name.lower() in after_fields:
                raise ValueError(f"Duplicate case-insensitive field name '{f.name}' in after schema snapshot")
            after_fields[f.name.lower()] = f

        renames = {k.lower(): v.lower() for k, v in (explicit_renames or {}).items()}
        changes: List[SchemaChange] = []

        removed_names = set(before_fields.keys()) - set(after_fields.keys())
        added_names = set(after_fields.keys()) - set(before_fields.keys())
        common_names = set(before_fields.keys()) & set(after_fields.keys())
        for old_name, new_name in renames.items():
            if old_name not in before_fields:
                raise ValueError(f"Explicit rename source '{old_name}' does not exist in the before schema")
            if new_name not in after_fields:
                raise ValueError(f"Explicit rename target '{new_name}' does not exist in the after schema")
            if old_name not in removed_names or new_name not in added_names:
                raise ValueError(f"Explicit rename '{old_name}' -> '{new_name}' is not a pure removed/added pair")

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
            if b_field.type != a_field.type and (b_field.type is not None or a_field.type is not None):
                compatible = (
                    SchemaDiffEngine.is_type_compatible(b_field.type, a_field.type)
                    if b_field.type is not None and a_field.type is not None
                    else False
                )
                changes.append(SchemaChange(
                    field=b_field.name,
                    change_type=ChangeType.TYPE_CHANGED,
                    old_state={"type": b_field.type},
                    proposed_state={"type": a_field.type},
                    is_breaking=not compatible,
                    details=f"Type of field '{b_field.name}' changed from '{b_field.type}' to '{a_field.type}' ({'compatible widening' if compatible else 'potentially incompatible'})"
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

    @staticmethod
    def is_type_compatible(before_type: str, after_type: str) -> bool:
        """Snowflake-oriented compatibility matrix used by the deterministic policy.

        Widening numeric precision/scale and string capacity are compatible;
        narrowing, temporal-family changes, and cross-family changes fail closed.
        """
        before = before_type.upper().strip()
        after = after_type.upper().strip()
        if before == after:
            return True
        if before.startswith("VARCHAR") and after.startswith("VARCHAR"):
            return SchemaDiffEngine._capacity(after) >= SchemaDiffEngine._capacity(before)
        fixed_numeric = ("NUMBER", "DECIMAL", "NUMERIC")
        integer_aliases = {"INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "BYTEINT"}
        float_aliases = {"FLOAT", "FLOAT4", "FLOAT8", "DOUBLE", "DOUBLE PRECISION", "REAL"}
        before_fixed = before.startswith(fixed_numeric) or before in integer_aliases
        after_fixed = after.startswith(fixed_numeric) or after in integer_aliases
        if before_fixed and after_fixed:
            before_precision, before_scale = SchemaDiffEngine._numeric_capacity(before)
            after_precision, after_scale = SchemaDiffEngine._numeric_capacity(after)
            before_integer_digits = before_precision - before_scale
            after_integer_digits = after_precision - after_scale
            return after_integer_digits >= before_integer_digits and after_scale >= before_scale
        if before in float_aliases and after in float_aliases:
            return True
        return False

    @staticmethod
    def _capacity(type_name: str) -> int:
        match = re.search(r"\((\d+)\)", type_name)
        return int(match.group(1)) if match else 2**31

    @staticmethod
    def _numeric_capacity(type_name: str) -> tuple[int, int]:
        match = re.search(r"\((\d+)\s*,\s*(\d+)\)", type_name)
        if match:
            return int(match.group(1)), int(match.group(2))
        precision_only = re.search(r"\((\d+)\)", type_name)
        if precision_only:
            return int(precision_only.group(1)), 0
        return 38, 0
