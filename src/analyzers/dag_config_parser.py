from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import Any, TypedDict

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
	lines = Path(file_path).read_text(encoding="utf-8").splitlines()
	models: list[DbtResource] = []
	sources: list[DbtResource] = []

	section: str | None = None
	source_name: str | None = None
	current_resource: DbtResource | None = None
	current_column: DbtColumn | None = None
	in_tables = False
	in_columns = False
	in_depends_on = False

	for raw_line in lines:
		line = raw_line.rstrip()
		stripped = line.strip()
		indent = len(line) - len(line.lstrip(" "))

		if not stripped or stripped.startswith("#"):
			continue

		if indent == 0 and stripped.endswith(":"):
			section = stripped[:-1]
			source_name = None
			current_resource = None
			current_column = None
			in_tables = False
			in_columns = False
			in_depends_on = False
			continue

		if section == "sources" and indent == 4 and stripped == "tables:":
			in_tables = True
			in_columns = False
			in_depends_on = False
			current_column = None
			continue

		if current_resource is not None and stripped == "columns:":
			in_columns = True
			in_depends_on = False
			current_column = None
			continue

		if current_resource is not None and stripped == "depends_on:":
			in_depends_on = True
			in_columns = False
			current_column = None
			continue

		if section == "sources" and indent == 2 and stripped.startswith("- name:"):
			source_name = _strip_yaml_scalar(stripped.split(":", 1)[1])
			current_resource = None
			current_column = None
			in_tables = False
			in_columns = False
			in_depends_on = False
			continue

		if section == "sources" and in_tables and indent == 6 and stripped.startswith("- name:"):
			resource_name = _strip_yaml_scalar(stripped.split(":", 1)[1])
			current_resource = {
				"name": resource_name,
				"resource_type": "source_table",
				"columns": [],
				"dependencies": _dedupe([source_name] if source_name else []),
			}
			if source_name:
				current_resource["source_name"] = source_name
			sources.append(current_resource)
			current_column = None
			in_columns = False
			in_depends_on = False
			continue

		if section == "models" and indent == 2 and stripped.startswith("- name:"):
			resource_name = _strip_yaml_scalar(stripped.split(":", 1)[1])
			current_resource = {
				"name": resource_name,
				"resource_type": "model",
				"columns": [],
				"dependencies": [],
			}
			models.append(current_resource)
			current_column = None
			in_tables = False
			in_columns = False
			in_depends_on = False
			continue

		if current_resource is not None and in_columns and stripped.startswith("- name:"):
			expected_indent = 10 if current_resource["resource_type"] == "source_table" else 6
			if indent == expected_indent:
				column_name = _strip_yaml_scalar(stripped.split(":", 1)[1])
				current_column = {"name": column_name}
				current_resource.setdefault("columns", []).append(current_column)
				continue

		if current_resource is not None and in_depends_on and stripped.startswith("- "):
			item_content = stripped[2:].strip()
			dependency = _normalize_dependency(item_content)
			if dependency:
				current_resource.setdefault("dependencies", []).append(dependency)
				current_resource["dependencies"] = _dedupe(current_resource["dependencies"])
			continue

		if current_column is not None and ":" in stripped:
			key, value = [part.strip() for part in stripped.split(":", 1)]
			if key in {"description", "data_type", "type"}:
				normalized_key = "data_type" if key == "type" else key
				current_column[normalized_key] = _strip_yaml_scalar(value) if value else None
			if current_resource is not None:
				_extend_dependencies(current_resource, value)
			continue

		if current_resource is not None and ":" in stripped:
			key, value = [part.strip() for part in stripped.split(":", 1)]
			if key == "description":
				current_resource["description"] = _strip_yaml_scalar(value) if value else None
			if key not in {"name", "columns", "depends_on", "tables"}:
				_extend_dependencies(current_resource, value)
			continue

		if current_resource is not None:
			_extend_dependencies(current_resource, stripped)

	for resource in models + sources:
		resource["dependencies"] = _dedupe(resource.get("dependencies", []))

	return {"models": models, "sources": sources}


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


def _normalize_dependency(value: str) -> str | None:
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

	return stripped_value if stripped_value.startswith(("source(", "ref(")) is False else None


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


__all__ = [
	"AirflowDagParseResult",
	"AirflowTask",
	"DbtColumn",
	"DbtResource",
	"DbtSchemaParseResult",
	"parse_airflow_dag_file",
	"parse_dbt_yaml",
	"parse_dbt_schema_file",
]
