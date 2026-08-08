import pytest
from app.schema_engine.diff import SchemaDiffEngine, SchemaSnapshot, DatasetIdentifier, SchemaField, ChangeType


def test_schema_diff_no_false_rename_inference():
    """Verify removing email STRING and adding phone STRING is NOT wrongly inferred as a rename."""
    before = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False),
            SchemaField(name="email", type="STRING", nullable=True)
        ]
    )

    after = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False),
            SchemaField(name="phone", type="STRING", nullable=True)
        ]
    )

    changeset = SchemaDiffEngine.diff(before, after)

    # Must produce 1 COLUMN_REMOVED (email) and 1 COLUMN_ADDED (phone), NOT COLUMN_RENAMED
    change_types = [c.change_type for c in changeset.changes]
    assert ChangeType.COLUMN_REMOVED in change_types
    assert ChangeType.COLUMN_ADDED in change_types
    assert ChangeType.COLUMN_RENAMED not in change_types

    removed_field = next(c for c in changeset.changes if c.change_type == ChangeType.COLUMN_REMOVED)
    assert removed_field.field == "email"

    added_field = next(c for c in changeset.changes if c.change_type == ChangeType.COLUMN_ADDED)
    assert added_field.field == "phone"


def test_schema_diff_explicit_rename():
    """Verify explicit rename hint records COLUMN_RENAMED correctly."""
    before = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False),
            SchemaField(name="email", type="STRING", nullable=True)
        ]
    )

    after = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False),
            SchemaField(name="user_email", type="STRING", nullable=True)
        ]
    )

    changeset = SchemaDiffEngine.diff(before, after, explicit_renames={"email": "user_email"})

    assert len(changeset.changes) == 1
    assert changeset.changes[0].change_type == ChangeType.COLUMN_RENAMED
    assert changeset.changes[0].field == "email"
    assert changeset.changes[0].proposed_state["name"] == "user_email"
