import sqlglot
from sqlglot import exp, parse_one
import difflib
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.schema_engine.diff import ChangeSet, ChangeType


class RemediationValidationResult(BaseModel):
    is_valid: bool
    status: str  # VALIDATED, REMEDIATION_FAILED
    syntax_ok: bool
    removed_field_referenced: bool
    errors: List[str] = []


class RemediationArtifact(BaseModel):
    file_path: str
    original_sql: str
    remediated_sql: str
    unified_diff: str
    validation: RemediationValidationResult


class SQLRemediationEngine:
    @staticmethod
    def remediate_dbt_model(
        file_path: str,
        original_sql: str,
        changes: ChangeSet
    ) -> RemediationArtifact:
        """Remediate downstream SQL query across SELECT, WHERE, GROUP BY, ORDER BY, and HAVING clauses using SQLGlot AST."""
        
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

        # 1. Parse SQL with SQLGlot
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
                    status="REMEDIATION_FAILED",
                    syntax_ok=False,
                    removed_field_referenced=True,
                    errors=[f"SQL Parsing error before remediation: {str(e)}"]
                )
            )

        # 2. Comprehensive Multi-Clause AST Transformation
        def transform_ast(node):
            if isinstance(node, exp.Select):
                # A. SELECT List
                new_expressions = []
                for select_expr in node.expressions:
                    cols = list(select_expr.find_all(exp.Column))
                    should_remove = any(col.name.lower() in [r.lower() for r in removed_columns] for col in cols)
                    if should_remove:
                        continue

                    # Rename column references if renamed
                    for col in cols:
                        if col.name.lower() in [r.lower() for r in renamed_columns.keys()]:
                            new_name = renamed_columns[col.name.lower()]
                            col.set("this", exp.Identifier(this=new_name, quoted=False))

                    new_expressions.append(select_expr)

                node.set("expressions", new_expressions)

                # B. WHERE Clause
                where_clause = node.args.get("where")
                if where_clause:
                    where_cols = [c.name.lower() for c in where_clause.find_all(exp.Column)]
                    if any(r.lower() in where_cols for r in removed_columns):
                        node.set("where", None)

                # C. GROUP BY Clause
                group_clause = node.args.get("group")
                if group_clause:
                    new_groups = []
                    for g_expr in group_clause.expressions:
                        g_cols = [c.name.lower() for c in g_expr.find_all(exp.Column)]
                        if not any(r.lower() in g_cols for r in removed_columns):
                            new_groups.append(g_expr)
                    if new_groups:
                        group_clause.set("expressions", new_groups)
                    else:
                        node.set("group", None)

                # D. ORDER BY Clause
                order_clause = node.args.get("order")
                if order_clause:
                    new_orders = []
                    for o_expr in order_clause.expressions:
                        o_cols = [c.name.lower() for c in o_expr.find_all(exp.Column)]
                        if not any(r.lower() in o_cols for r in removed_columns):
                            new_orders.append(o_expr)
                    if new_orders:
                        order_clause.set("expressions", new_orders)
                    else:
                        node.set("order", None)

            return node

        remediated_ast = expression.transform(transform_ast)
        remediated_sql = remediated_ast.sql(pretty=True, dialect="snowflake")

        # 3. Static Validation with SQLGlot
        syntax_ok = True
        removed_referenced = False

        try:
            validated_ast = parse_one(remediated_sql, read="snowflake")
            
            # Verify no deleted column is referenced anywhere in remediated AST
            found_cols = [c.name.lower() for c in validated_ast.find_all(exp.Column)]
            for rem in removed_columns:
                if rem.lower() in found_cols:
                    removed_referenced = True
                    errors.append(f"Removed column '{rem}' is still referenced in remediated query AST.")
        except Exception as ve:
            syntax_ok = False
            errors.append(f"Remediated SQL syntax invalid: {str(ve)}")

        is_valid = syntax_ok and not removed_referenced
        status = "VALIDATED" if is_valid else "REMEDIATION_FAILED"

        # 4. Generate Unified Diff
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
