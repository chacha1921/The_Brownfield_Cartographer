from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import Any, TypedDict

import yaml

from models.schemas import DatasetNode


class DbtColumn(TypedDict, total=False):
	name: str
	data_type: str | None
	description: str | None


class DbtResource(TypedDict, total=False):
	name: str
	resource_type: str
	columns: list[DbtColumn]
	dependencies: list[str]
	source_name: str


class DbtSchemaParseResult(TypedDict):
	models: list[DbtResource]
	sources: list[DbtResource]


class AirflowTask(TypedDict):
	variable_name: str
	task_id: str
	operator: str


class AirflowDagParseResult(TypedDict):
	tasks: list[AirflowTask]
	dependencies: list[tuple[str, str]]


class DAGConfigAnalyzer:
	def parse_dbt_resources(self, file_path: str | Path) -> list[DatasetNode]:
		return parse_dbt_yaml(file_path)

	def analyze_airflow_dag(self, file_path: str | Path) -> AirflowDagParseResult:
		return parse_airflow_dag_file(file_path)


def parse_dbt_yaml(file_path: str | Path) -> list[DatasetNode]:
	parsed_schema = parse_dbt_schema_file(file_path)
	nodes_by_id: dict[str, DatasetNode] = {}

	for source in parsed_schema["sources"]:
		dataset_name = source["name"]
		if source.get("source_name"):
			dataset_name = f"{source['source_name']}.{source['name']}"

		nodes_by_id[dataset_name] = DatasetNode(
			id=dataset_name,
			name=dataset_name,
			storage_type="dbt_source",
			schema_snapshot={
				"columns": source.get("columns", []),
				"dependencies": source.get("dependencies", []),
			},
			is_source_of_truth=True,
		)

	for model in parsed_schema["models"]:
		existing_node = nodes_by_id.get(model["name"])
		schema_snapshot = dict(existing_node.schema_snapshot) if existing_node is not None else {}
		schema_snapshot.update(
			{
				"columns": model.get("columns", []),
				"dependencies": model.get("dependencies", []),
			}
		)

		for key in ("description",):
			if key in model:
				schema_snapshot[key] = model[key]

		nodes_by_id[model["name"]] = DatasetNode(
			id=model["name"],
			name=model["name"],
			storage_type="dbt_model" if existing_node is None else existing_node.storage_type,
			schema_snapshot=schema_snapshot,
			is_source_of_truth=existing_node.is_source_of_truth if existing_node is not None else False,
		)

	return list(nodes_by_id.values())


def parse_dbt_schema_file(file_path: str | Path) -> DbtSchemaParseResult:
	payload = yaml.safe_load(Path(file_path).read_text(encoding="utf-8")) or {}
	if not isinstance(payload, dict):
		return {"models": [], "sources": []}

	models = _parse_dbt_model_resources(payload.get("models"))
	sources = _parse_dbt_source_resources(payload.get("sources"))

	return {"models": models, "sources": sources}


def _parse_dbt_model_resources(models_payload: Any) -> list[DbtResource]:
	if not isinstance(models_payload, list):
		return []

	resources: list[DbtResource] = []
	for model in models_payload:
		if not isinstance(model, dict):
			continue

		resource_name = _string_value(model.get("name"))
		if not resource_name:
			continue

		resource: DbtResource = {
			"name": resource_name,
			"resource_type": "model",
			"columns": _parse_dbt_columns(model.get("columns")),
			"dependencies": _collect_dependencies(model),
		}
		description = _string_value(model.get("description"))
		if description:
			resource["description"] = description
		resources.append(resource)

	return resources


def _parse_dbt_source_resources(sources_payload: Any) -> list[DbtResource]:
	if not isinstance(sources_payload, list):
		return []

	resources: list[DbtResource] = []
	for source in sources_payload:
		if not isinstance(source, dict):
			continue

		source_name = _string_value(source.get("name"))
		if not source_name:
			continue

		for table in source.get("tables", []):
			if not isinstance(table, dict):
				continue

			resource_name = _string_value(table.get("name"))
			if not resource_name:
				continue

			dependencies = _collect_dependencies(table)
			dependencies.insert(0, source_name)
			resource: DbtResource = {
				"name": resource_name,
				"resource_type": "source_table",
				"columns": _parse_dbt_columns(table.get("columns")),
				"dependencies": _dedupe(dependencies),
				"source_name": source_name,
			}
			description = _string_value(table.get("description"))
			if description:
				resource["description"] = description
			resources.append(resource)

	return resources


def _parse_dbt_columns(columns_payload: Any) -> list[DbtColumn]:
	if not isinstance(columns_payload, list):
		return []

	columns: list[DbtColumn] = []
	for column in columns_payload:
		if not isinstance(column, dict):
			continue

		column_name = _string_value(column.get("name") or column.get("column_name"))
		if not column_name:
			continue

		column_payload: DbtColumn = {"name": column_name}
		data_type = _string_value(column.get("data_type") or column.get("type"))
		description = _string_value(column.get("description"))
		if data_type:
			column_payload["data_type"] = data_type
		if description:
			column_payload["description"] = description
		columns.append(column_payload)

	return columns


def _collect_dependencies(payload: Any) -> list[str]:
	dependencies: list[str] = []

	if isinstance(payload, dict):
		explicit_dependencies = payload.get("depends_on")
		if isinstance(explicit_dependencies, list):
			for item in explicit_dependencies:
				dependency = _normalize_dependency(item)
				if dependency:
					dependencies.append(dependency)

		for value in payload.values():
			dependencies.extend(_collect_dependencies(value))
	elif isinstance(payload, list):
		for item in payload:
			dependencies.extend(_collect_dependencies(item))
	elif isinstance(payload, str):
		dependencies.extend(_extract_embedded_dependencies(payload))

	return _dedupe(dependencies)


def parse_airflow_dag_file(file_path: str | Path) -> AirflowDagParseResult:
	source = Path(file_path).read_text(encoding="utf-8")
	tree = ast.parse(source)

	task_lookup: dict[str, AirflowTask] = {}
	dependencies: set[tuple[str, str]] = set()

	for node in ast.walk(tree):
		if isinstance(node, ast.Assign):
			task = _extract_airflow_task(node)
			if task is not None:
				task_lookup[task["variable_name"]] = task

	for node in ast.walk(tree):
		if isinstance(node, ast.Expr):
			edges, _, _ = _parse_dependency_expression(node.value, task_lookup)
			dependencies.update(edges)

	return {
		"tasks": sorted(task_lookup.values(), key=lambda item: item["task_id"]),
		"dependencies": sorted(dependencies),
	}


def _extract_airflow_task(node: ast.Assign) -> AirflowTask | None:
	if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
		return None
	if not isinstance(node.value, ast.Call):
		return None

	operator_name = _call_name(node.value.func)
	if operator_name not in {"PythonOperator", "BashOperator"}:
		return None

	task_id = None
	for keyword in node.value.keywords:
		if keyword.arg == "task_id" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
			task_id = keyword.value.value
			break

	if task_id is None:
		return None

	return {
		"variable_name": node.targets[0].id,
		"task_id": task_id,
		"operator": operator_name,
	}


def _parse_dependency_expression(
	node: ast.AST,
	task_lookup: dict[str, AirflowTask],
) -> tuple[set[tuple[str, str]], set[str], set[str]]:
	if isinstance(node, ast.BinOp) and isinstance(node.op, ast.RShift):
		left_edges, left_roots, left_leaves = _parse_dependency_expression(node.left, task_lookup)
		right_edges, right_roots, right_leaves = _parse_dependency_expression(node.right, task_lookup)
		new_edges = {(source, target) for source in left_leaves for target in right_roots}
		return left_edges | right_edges | new_edges, left_roots, right_leaves

	if isinstance(node, ast.BinOp) and isinstance(node.op, ast.LShift):
		left_edges, left_roots, left_leaves = _parse_dependency_expression(node.left, task_lookup)
		right_edges, right_roots, right_leaves = _parse_dependency_expression(node.right, task_lookup)
		new_edges = {(source, target) for source in right_leaves for target in left_roots}
		return left_edges | right_edges | new_edges, right_roots, left_leaves

	task_ids = _resolve_task_references(node, task_lookup)
	return set(), task_ids, task_ids


def _resolve_task_references(node: ast.AST, task_lookup: dict[str, AirflowTask]) -> set[str]:
	if isinstance(node, ast.Name):
		task = task_lookup.get(node.id)
		return {task["task_id"]} if task is not None else set()

	if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
		task_ids: set[str] = set()
		for element in node.elts:
			task_ids.update(_resolve_task_references(element, task_lookup))
		return task_ids

	return set()


def _call_name(node: ast.AST) -> str | None:
	if isinstance(node, ast.Name):
		return node.id
	if isinstance(node, ast.Attribute):
		return node.attr
	return None


def _normalize_dependency(value: Any) -> str | None:
	if not isinstance(value, str):
		return None

	stripped_value = _strip_yaml_scalar(value)
	if not stripped_value:
		return None

	source_match = re.search(r"source\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", stripped_value)
	if source_match:
		return f"{source_match.group(1)}.{source_match.group(2)}"

	ref_match = re.search(r"ref\(\s*['\"]([^'\"]+)['\"]\s*\)", stripped_value)
	if ref_match:
		return ref_match.group(1)

	if stripped_value.startswith("{{") and stripped_value.endswith("}}"):
		return None

	if re.fullmatch(r"[A-Za-z0-9_.-]+", stripped_value):
		return stripped_value

	return None


def _extend_dependencies(resource: DbtResource, value: str) -> None:
	for dependency in _extract_embedded_dependencies(value):
		resource.setdefault("dependencies", []).append(dependency)


def _extract_embedded_dependencies(value: str) -> list[str]:
	dependencies: list[str] = []

	for source_name, table_name in re.findall(r"source\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", value):
		dependencies.append(f"{source_name}.{table_name}")

	for model_name in re.findall(r"ref\(\s*['\"]([^'\"]+)['\"]\s*\)", value):
		dependencies.append(model_name)

	return dependencies


def _dedupe(values: list[str]) -> list[str]:
	return list(dict.fromkeys(value for value in values if value))


def _strip_yaml_scalar(value: str) -> str:
	return value.strip().strip("\"'")


def _string_value(value: Any) -> str | None:
	return _strip_yaml_scalar(value) if isinstance(value, str) and _strip_yaml_scalar(value) else None


__all__ = [
	"AirflowDagParseResult",
	"AirflowTask",
	"DAGConfigAnalyzer",
	"DbtColumn",
	"DbtResource",
	"DbtSchemaParseResult",
	"parse_airflow_dag_file",
	"parse_dbt_yaml",
	"parse_dbt_schema_file",
]
