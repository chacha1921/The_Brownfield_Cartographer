from __future__ import annotations

from typing import TypedDict

from sqlglot import exp, parse_one


class SqlDependencies(TypedDict):
	source_tables: list[str]
	target_table: str | None


def extract_sql_dependencies(sql_string: str, dialect: str = "postgres") -> SqlDependencies:
	expression = parse_one(sql_string, dialect=dialect)
	target_table = _extract_target_table(expression)
	cte_names = {cte.alias_or_name for cte in expression.find_all(exp.CTE)}

	source_tables: list[str] = []
	seen_tables: set[str] = set()

	for table in expression.find_all(exp.Table):
		normalized_name = _normalize_table_name(table)
		if normalized_name is None:
			continue
		if table.name in cte_names or normalized_name in cte_names:
			continue
		if normalized_name == target_table:
			continue
		if normalized_name in seen_tables:
			continue

		seen_tables.add(normalized_name)
		source_tables.append(normalized_name)

	return {
		"source_tables": source_tables,
		"target_table": target_table,
	}


def _extract_target_table(expression: exp.Expression) -> str | None:
	if isinstance(expression, (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create)):
		return _normalize_table_reference(expression.this)
	return None


def _normalize_table_reference(reference: exp.Expression | None) -> str | None:
	if reference is None:
		return None
	if isinstance(reference, exp.Table):
		return _normalize_table_name(reference)
	if isinstance(reference, exp.Schema):
		return _normalize_table_reference(reference.this)

	table = reference.find(exp.Table)
	return _normalize_table_name(table) if table is not None else None


def _normalize_table_name(table: exp.Table | None) -> str | None:
	if table is None:
		return None

	parts = [part for part in (table.catalog, table.db, table.name) if part]
	return ".".join(parts) if parts else None


__all__ = ["SqlDependencies", "extract_sql_dependencies"]
