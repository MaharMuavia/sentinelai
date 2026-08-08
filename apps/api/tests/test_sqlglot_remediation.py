import pytest
from app.schema_engine.diff import ChangeSet, SchemaChange, ChangeType
from app.remediation.engine import SQLRemediationEngine, RemediationStatus


def test_remediation_where_clause_requires_human():
    """Verify that removing a column referenced in a WHERE clause requires human review and is NOT auto-validated."""
    sql = "SELECT customer_id, email, lifetime_value FROM customer_360 WHERE email IS NOT NULL;"
    changes = ChangeSet(
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        changes=[
            SchemaChange(
                field="email",
                change_type=ChangeType.COLUMN_REMOVED,
                is_breaking=True,
                details="Field 'email' removed"
            )
        ]
    )

    artifact = SQLRemediationEngine.remediate_dbt_model(
        file_path="models/customer_360.sql",
        original_sql=sql,
        changes=changes
    )

    # Must be marked REQUIRES_HUMAN, NOT VALIDATED (never deleting WHERE predicates silently)
    assert artifact.validation.status == RemediationStatus.REQUIRES_HUMAN
    assert artifact.validation.is_valid is False
    assert "WHERE filter clause" in artifact.validation.requires_human_reason


def test_remediation_simple_projection_removal():
    """Verify simple SELECT list projection removal without WHERE clause predicates."""
    sql = "SELECT customer_id, email, lifetime_value FROM customer_360;"
    changes = ChangeSet(
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        changes=[
            SchemaChange(
                field="email",
                change_type=ChangeType.COLUMN_REMOVED,
                is_breaking=True,
                details="Field 'email' removed"
            )
        ]
    )

    artifact = SQLRemediationEngine.remediate_dbt_model(
        file_path="models/customer_360.sql",
        original_sql=sql,
        changes=changes
    )

    assert artifact.validation.status == RemediationStatus.STRUCTURALLY_VALID
    assert artifact.validation.is_valid is True
    assert "email" not in artifact.remediated_sql.lower()
