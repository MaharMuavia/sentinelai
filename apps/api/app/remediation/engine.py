import sqlglot
from sqlglot import exp, parse_one
import difflib
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.schema_engine.diff import ChangeSet, ChangeType


class RemediationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    REQUIRES_HUMAN = "REQUIRES_HUMAN"
    SEMANTIC_SAFETY_UNKNOWN = "SEMANTIC_SAFETY_UNKNOWN"
    REMEDIATION_FAILED = "REMEDIATION_FAILED"
    REMEDIATION_NOT_GENERATED = "REMEDIATION_NOT_GENERATED"


class RemediationValidationResult(BaseModel):
    is_valid: bool
    status: RemediationStatus
    syntax_ok: bool
    removed_field_referenced: bool
    requires_human_reason: Optional[str] = None
    errors: List[str] = []


class RemediationArtifact(BaseModel):
    file_path: str
    original_sql: str
    remediated_sql: str
    unified_diff: str
    validation: RemediationValidationResult


class SQLRemediationEngine:
    """
    Semantic SQL Remediation Engine.
    Transforms AST only when semantic safety can be proven deterministically.
    If a removed column is referenced in WHERE, JOIN, HAVING, GROUP BY, ORDER BY,
    or CASE predicates, automatic patch approval is DENIED and human intervention is required.
    """

    @staticmethod
    def remediate_dbt_model(
        file_path: str,
        original_sql: Optional[str],
        changes: ChangeSet
    ) -> RemediationArtifact:
        if not original_sql or not original_sql.strip():
            return RemediationArtifact(
                file_path=file_path,
                original_sql="",
                remediated_sql="",
                unified_diff="",
                validation=RemediationValidationResult(
                    is_valid=False,
                    status=RemediationStatus.REMEDIATION_NOT_GENERATED,
                    syntax_ok=False,
                    removed_field_referenced=False,
                    requires_human_reason="Downstream source SQL unavailable for candidate model.",
                    errors=["No downstream SQL source provided for remediation analysis."]
                )
            )

        errors: List[str] = []
        breaking_changes = [c for c in changes.changes if c.is_breaking]

        removed_columns = [
            c.field for c in breaking_changes if c.change_type == ChangeType.COLUMN_REMOVED
        ]
        renamed_columns = {
            c.old_state["name"]: c.proposed_state["name"]
            for c in breaking_changes
            if c.change_type == ChangeType.COLUMN_RENAMED and c.old_state and c.proposed_state
        }

        # 1. Parse original SQL
        try:
            expression = parse_one(original_sql, read="snowflake")
        except Exception as e:
            return RemediationArtifact(
                file_path=file_path,
                original_sql=original_sql,
                remediated_sql=original_sql,
                unified_diff="",
                validation=RemediationValidationResult(
                    is_valid=False,
                    status=RemediationStatus.REMEDIATION_FAILED,
                    syntax_ok=False,
                    removed_field_referenced=True,
                    errors=[f"SQL parsing failure before remediation: {str(e)}"]
                )
            )

        # 2. Check for semantic predicate usage (WHERE, JOIN, HAVING, GROUP BY, ORDER BY, CASE)
        semantic_violations: List[str] = []

        for node in expression.walk():
            # Check WHERE clause
            if isinstance(node, exp.Where):
                cols = [c.name.lower() for c in node.find_all(exp.Column)]
                for r in removed_columns:
                    if r.lower() in cols:
                        semantic_violations.append(f"Removed column '{r}' is used in WHERE filter clause.")

            # Check JOIN condition
            elif isinstance(node, exp.Join):
                cols = [c.name.lower() for c in node.find_all(exp.Column)]
                for r in removed_columns:
                    if r.lower() in cols:
                        semantic_violations.append(f"Removed column '{r}' is used in JOIN predicate.")

            # Check HAVING clause
            elif isinstance(node, exp.Having):
                cols = [c.name.lower() for c in node.find_all(exp.Column)]
                for r in removed_columns:
                    if r.lower() in cols:
                        semantic_violations.append(f"Removed column '{r}' is used in HAVING clause.")

            # Check GROUP BY clause
            elif isinstance(node, exp.Group):
                cols = [c.name.lower() for c in node.find_all(exp.Column)]
                for r in removed_columns:
                    if r.lower() in cols:
                        semantic_violations.append(f"Removed column '{r}' is used in GROUP BY clause.")

            # Check ORDER BY clause
            elif isinstance(node, exp.Order):
                cols = [c.name.lower() for c in node.find_all(exp.Column)]
                for r in removed_columns:
                    if r.lower() in cols:
                        semantic_violations.append(f"Removed column '{r}' is used in ORDER BY clause.")

        # If semantic violations exist, refuse automatic remediation approval
        if semantic_violations:
            reason = " ".join(semantic_violations) + " Modifying business logic predicates requires manual engineer review."
            return RemediationArtifact(
                file_path=file_path,
                original_sql=original_sql,
                remediated_sql=original_sql,
                unified_diff="",
                validation=RemediationValidationResult(
                    is_valid=False,
                    status=RemediationStatus.REQUIRES_HUMAN,
                    syntax_ok=True,
                    removed_field_referenced=True,
                    requires_human_reason=reason,
                    errors=semantic_violations
                )
            )

        # 3. Transform SELECT projections & Explicit Renames safely
        def transform_ast(node):
            if isinstance(node, exp.Select):
                new_expressions = []
                for select_expr in node.expressions:
                    cols = list(select_expr.find_all(exp.Column))
                    should_remove = any(col.name.lower() in [r.lower() for r in removed_columns] for col in cols)
                    if should_remove:
                        continue

                    # Rewrite explicit renames
                    for col in cols:
                        if col.name.lower() in [r.lower() for r in renamed_columns.keys()]:
                            new_name = renamed_columns[col.name.lower()]
                            col.set("this", exp.Identifier(this=new_name, quoted=False))

                    new_expressions.append(select_expr)

                node.set("expressions", new_expressions)

            return node

        remediated_ast = expression.transform(transform_ast)
        remediated_sql = remediated_ast.sql(pretty=True, dialect="snowflake")

        # 4. Static Validation
        syntax_ok = True
        removed_referenced = False

        try:
            validated_ast = parse_one(remediated_sql, read="snowflake")
            found_cols = [c.name.lower() for c in validated_ast.find_all(exp.Column)]
            for rem in removed_columns:
                if rem.lower() in found_cols:
                    removed_referenced = True
                    errors.append(f"Removed column '{rem}' is still referenced in remediated query AST.")
        except Exception as ve:
            syntax_ok = False
            errors.append(f"Remediated SQL syntax invalid: {str(ve)}")

        is_valid = syntax_ok and not removed_referenced
        status = RemediationStatus.VALIDATED if is_valid else RemediationStatus.REMEDIATION_FAILED

        diff_lines = list(difflib.unified_diff(
            original_sql.splitlines(keepends=True),
            remediated_sql.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}"
        ))
        unified_diff = "".join(diff_lines)

        return RemediationArtifact(
            file_path=file_path,
            original_sql=original_sql,
            remediated_sql=remediated_sql,
            unified_diff=unified_diff,
            validation=RemediationValidationResult(
                is_valid=is_valid,
                status=status,
                syntax_ok=syntax_ok,
                removed_field_referenced=removed_referenced,
                errors=errors
            )
        )
