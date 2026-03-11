from __future__ import annotations

from pathlib import Path
import re
from typing import TypedDict

from sqlglot import exp, parse_one


class SqlDependencies(TypedDict):
	source_tables: list[str]
	target_table: str | None


class DbtSqlEdge(TypedDict):
	source: str
	target: str
	edge_type: str


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


def parse_dbt_sql(file_path: str | Path) -> list[DbtSqlEdge]:
	sql_file = Path(file_path)
	sql_text = sql_file.read_text(encoding="utf-8")
	target_dataset = sql_file.stem
	transformation_id = sql_file.as_posix()

	upstream_datasets = _extract_dbt_references(sql_text)
	edges: list[DbtSqlEdge] = [
		{
			"source": transformation_id,
			"target": target_dataset,
			"edge_type": "PRODUCES",
		}
	]

	for upstream_dataset in upstream_datasets:
		edges.append(
			{
				"source": upstream_dataset,
				"target": transformation_id,
				"edge_type": "CONSUMES",
			}
		)

	return edges


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


def _extract_dbt_references(sql_text: str) -> list[str]:
	references: list[str] = []

	for model_name in re.findall(r"\{\{\s*ref\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", sql_text):
		references.append(model_name)

	for source_name, table_name in re.findall(
		r"\{\{\s*source\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}",
		sql_text,
	):
		references.append(f"{source_name}.{table_name}")

	return list(dict.fromkeys(references))


__all__ = ["DbtSqlEdge", "SqlDependencies", "extract_sql_dependencies", "parse_dbt_sql"]
