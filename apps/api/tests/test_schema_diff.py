from app.schema_engine.diff import SchemaDiffEngine, SchemaSnapshot, DatasetIdentifier, SchemaField, ChangeType


def test_schema_diff_column_removed():
    before = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:raw_customers", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False),
            SchemaField(name="email", type="STRING", nullable=True),
            SchemaField(name="country", type="STRING", nullable=True)
        ]
    )

    after = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:raw_customers", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False),
            SchemaField(name="country", type="STRING", nullable=True)
        ]
    )

    changeset = SchemaDiffEngine.diff(before, after)
    assert len(changeset.changes) == 1
    ch = changeset.changes[0]
    assert ch.change_type == ChangeType.COLUMN_REMOVED
    assert ch.field == "email"
    assert ch.is_breaking is True


def test_schema_diff_column_added():
    before = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:raw_customers", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False)
        ]
    )

    after = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:raw_customers", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False),
            SchemaField(name="phone", type="STRING", nullable=True)
        ]
    )

    changeset = SchemaDiffEngine.diff(before, after)
    assert len(changeset.changes) == 1
    ch = changeset.changes[0]
    assert ch.change_type == ChangeType.COLUMN_ADDED
    assert ch.field == "phone"
    assert ch.is_breaking is False
