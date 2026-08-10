from app.schema_engine.diff import DatasetIdentifier, SchemaField, SchemaSnapshot
from app.schema_engine.parser import SchemaParserEngine


def _base():
    return SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name="raw_customers"),
        fields=[SchemaField(name="customer_id", type="STRING")],
    )


def test_drop_missing_column_is_an_error():
    result = SchemaParserEngine.parse_sql_ddl_alter("ALTER TABLE raw_customers DROP COLUMN email", _base().dataset.urn, _base())
    assert result.success is False
    assert "missing column" in result.error


def test_rename_missing_column_is_an_error():
    result = SchemaParserEngine.parse_sql_ddl_alter("ALTER TABLE raw_customers RENAME COLUMN email TO address", _base().dataset.urn, _base())
    assert result.success is False
    assert "missing column" in result.error
