from app.schema_engine.diff import ChangeSet, SchemaChange, ChangeType
from app.schema_engine.parser import SchemaParserEngine
from app.remediation.engine import SQLRemediationEngine


def test_sqlglot_column_removed_remediation():
    changeset = ChangeSet(
        dataset_urn="urn:li:dataset:raw_customers",
        changes=[
            SchemaChange(
                field="email",
                change_type=ChangeType.COLUMN_REMOVED,
                is_breaking=True,
                details="Field 'email' removed"
            )
        ]
    )

    sql = "SELECT customer_id, email, lifetime_value FROM customer_360 WHERE email IS NOT NULL GROUP BY customer_id, email ORDER BY email;"
    artifact = SQLRemediationEngine.remediate_dbt_model("models/marts/customer_360.sql", sql, changeset)

    assert artifact.validation.is_valid is True
    assert artifact.validation.status == "VALIDATED"
    assert "email" not in artifact.remediated_sql.lower()
    assert artifact.unified_diff != ""


def test_schema_parser_ddl_alter_drop():
    ddl = "ALTER TABLE raw_customers DROP COLUMN email;"
    before, after = SchemaParserEngine.parse_sql_ddl_alter(ddl)
    assert len(before.fields) == 4
    assert len(after.fields) == 3
    assert not any(f.name.lower() == "email" for f in after.fields)
