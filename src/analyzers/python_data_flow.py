from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import TypedDict

from analyzers.sql_lineage import extract_sql_dependencies


class PythonDataFlowEdge(TypedDict):
	source: str
	target: str
	edge_type: str


class PythonDataFlowAnalyzer(ast.NodeVisitor):
	READ_CALL_SUFFIXES = {
		"read_csv",
		"read_json",
		"read_parquet",
		"read_pickle",
		"read_excel",
		"read_feather",
		"read_orc",
		"read_table",
	}
	WRITE_CALL_SUFFIXES = {
		"to_csv",
		"to_json",
		"to_parquet",
		"to_pickle",
		"to_excel",
		"to_feather",
		"to_orc",
	}
	SQL_READ_CALL_SUFFIXES = {"read_sql", "read_sql_query", "read_sql_table"}
	SQL_EXECUTE_CALL_SUFFIXES = {"execute", "executemany", "sql"}
	SPARK_READ_SUFFIXES = {"read.csv", "read.json", "read.parquet", "read.text", "read.table", "read.load"}
	SPARK_WRITE_SUFFIXES = {
		"write.csv",
		"write.json",
		"write.parquet",
		"write.text",
		"write.save",
		"write.saveAsTable",
		"write.insertInto",
	}

	def __init__(self, dialect: str = "postgres") -> None:
		super().__init__()
		self.dialect = dialect
		self._variable_values: dict[str, str] = {}
		self._edges: dict[tuple[str, str, str], PythonDataFlowEdge] = {}
		self._transformation_id: str | None = None

	def analyze_file(self, file_path: str | Path) -> list[PythonDataFlowEdge]:
		self._variable_values = {}
		self._edges = {}
		self._transformation_id = Path(file_path).as_posix()

		source = Path(file_path).read_text(encoding="utf-8")
		tree = ast.parse(source)
		self.visit(tree)

		return list(self._edges.values())

	def visit_Assign(self, node: ast.Assign) -> None:
		resolved_value = self._resolve_value(node.value)
		for target in node.targets:
			self._record_assignment(target, resolved_value)
		self.generic_visit(node)

	def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
		resolved_value = self._resolve_value(node.value) if node.value is not None else None
		self._record_assignment(node.target, resolved_value)
		self.generic_visit(node)

	def visit_Call(self, node: ast.Call) -> None:
		call_name = self._call_name(node.func)
		if call_name is not None and self._transformation_id is not None:
			if self._matches_suffix(call_name, self.READ_CALL_SUFFIXES | self.SPARK_READ_SUFFIXES):
				for dataset in self._extract_read_datasets(node, call_name):
					self._add_edge(dataset, self._transformation_id, "CONSUMES")
			elif self._matches_suffix(call_name, self.WRITE_CALL_SUFFIXES | self.SPARK_WRITE_SUFFIXES):
				for dataset in self._extract_write_datasets(node, call_name):
					self._add_edge(self._transformation_id, dataset, "PRODUCES")
			elif self._matches_suffix(call_name, self.SQL_READ_CALL_SUFFIXES):
				for dataset in self._extract_sql_read_datasets(node, call_name):
					self._add_edge(dataset, self._transformation_id, "CONSUMES")
			elif self._matches_suffix(call_name, self.SQL_EXECUTE_CALL_SUFFIXES):
				for edge in self._extract_sql_execution_edges(node):
					self._add_edge(edge["source"], edge["target"], edge["edge_type"])

		self.generic_visit(node)

	def _record_assignment(self, target: ast.AST, value: str | None) -> None:
		if value is None:
			return

		for target_name in self._extract_target_names(target):
			self._variable_values[target_name] = value

	def _extract_target_names(self, target: ast.AST) -> list[str]:
		if isinstance(target, ast.Name):
			return [target.id]
		if isinstance(target, (ast.Tuple, ast.List)):
			names: list[str] = []
			for element in target.elts:
				names.extend(self._extract_target_names(element))
			return names
		return []

	def _extract_read_datasets(self, node: ast.Call, call_name: str) -> list[str]:
		if self._matches_suffix(call_name, self.SPARK_READ_SUFFIXES):
			return self._extract_datasets_from_arguments(node, keyword_names={"path", "paths", "tableName"})
		return self._extract_datasets_from_arguments(node, keyword_names={"filepath_or_buffer", "path", "path_or_buf"})

	def _extract_write_datasets(self, node: ast.Call, call_name: str) -> list[str]:
		if call_name.endswith("saveAsTable") or call_name.endswith("insertInto"):
			return self._extract_datasets_from_arguments(node, keyword_names={"name", "tableName"})
		if call_name.endswith("save"):
			return self._extract_datasets_from_arguments(node, keyword_names={"path"})
		if call_name.endswith("to_sql"):
			return self._extract_datasets_from_arguments(node, keyword_names={"name"})
		return self._extract_datasets_from_arguments(node, keyword_names={"path", "path_or_buf", "filepath_or_buffer"})

	def _extract_sql_read_datasets(self, node: ast.Call, call_name: str) -> list[str]:
		if call_name.endswith("read_sql_table"):
			return self._extract_datasets_from_arguments(node, keyword_names={"table_name", "name"})

		sql_argument = self._get_argument(node, 0, {"sql", "query"})
		if sql_argument is None:
			return []

		resolved_sql = self._resolve_value(sql_argument)
		if resolved_sql is None:
			return []

		dependencies = self._extract_sql_dependencies(resolved_sql)
		return dependencies["source_tables"] or ([resolved_sql] if not self._looks_like_sql(resolved_sql) else [])

	def _extract_sql_execution_edges(self, node: ast.Call) -> list[PythonDataFlowEdge]:
		sql_argument = self._get_argument(node, 0, {"statement", "sql", "query"})
		if sql_argument is None or self._transformation_id is None:
			return []

		resolved_sql = self._resolve_value(sql_argument)
		if resolved_sql is None:
			return []

		dependencies = self._extract_sql_dependencies(resolved_sql)
		edges: list[PythonDataFlowEdge] = []
		for source_table in dependencies["source_tables"]:
			edges.append({"source": source_table, "target": self._transformation_id, "edge_type": "CONSUMES"})
		if dependencies["target_table"] is not None:
			edges.append(
				{"source": self._transformation_id, "target": dependencies["target_table"], "edge_type": "PRODUCES"}
			)
		return edges

	def _extract_sql_dependencies(self, sql_text: str) -> dict[str, list[str] | str | None]:
		try:
			return extract_sql_dependencies(sql_text, dialect=self.dialect)
		except Exception:
			return {"source_tables": [], "target_table": None}

	def _extract_datasets_from_arguments(
		self,
		node: ast.Call,
		keyword_names: set[str] | None = None,
	) -> list[str]:
		datasets: list[str] = []
		keyword_names = keyword_names or set()

		candidate_values: list[str | None] = []
		if node.args:
			candidate_values.append(self._resolve_value(node.args[0]))
		for keyword in node.keywords:
			if keyword.arg in keyword_names:
				candidate_values.append(self._resolve_value(keyword.value))

		for value in candidate_values:
			if value:
				datasets.append(value)

		return list(dict.fromkeys(datasets))

	def _get_argument(self, node: ast.Call, index: int, keyword_names: set[str]) -> ast.AST | None:
		if len(node.args) > index:
			return node.args[index]
		for keyword in node.keywords:
			if keyword.arg in keyword_names:
				return keyword.value
		return None

	def _resolve_value(self, node: ast.AST | None) -> str | None:
		if node is None:
			return None
		if isinstance(node, ast.Constant) and isinstance(node.value, str):
			return node.value
		if isinstance(node, ast.Name):
			return self._variable_values.get(node.id, self._dynamic_reference(node.id))
		if isinstance(node, ast.JoinedStr):
			return self._resolve_joined_str(node)
		if isinstance(node, ast.Call):
			call_name = self._call_name(node.func)
			if call_name in {"Path", "PurePath", "PosixPath", "WindowsPath"} or call_name.endswith(".Path"):
				parts = [self._resolve_value(argument) for argument in node.args]
				resolved_parts = [part for part in parts if part]
				return "/".join(part.strip("/") for part in resolved_parts) if resolved_parts else None
		if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
			left = self._resolve_value(node.left)
			right = self._resolve_value(node.right)
			if left is None or right is None:
				return left or right
			separator = "" if isinstance(node.op, ast.Add) else "/"
			return f"{left.rstrip('/')}" + separator + f"{right.lstrip('/')}"
		return None

	def _resolve_joined_str(self, node: ast.JoinedStr) -> str:
		parts: list[str] = []
		dynamic = False
		for value in node.values:
			if isinstance(value, ast.Constant) and isinstance(value.value, str):
				parts.append(value.value)
			else:
				dynamic = True
				parts.append("{dynamic}")
		joined = "".join(parts).strip()
		if not dynamic:
			return joined
		return self._dynamic_reference(joined or ast.unparse(node))

	def _looks_like_sql(self, value: str) -> bool:
		return bool(re.search(r"\b(select|insert|update|delete|merge|create)\b", value, re.IGNORECASE))

	def _dynamic_reference(self, label: str) -> str:
		normalized = re.sub(r"[^a-zA-Z0-9._/-]+", "_", label).strip("_") or "unknown"
		return f"dynamic://{normalized}"

	def _call_name(self, node: ast.AST) -> str | None:
		if isinstance(node, ast.Name):
			return node.id
		if isinstance(node, ast.Attribute):
			prefix = self._call_name(node.value)
			return f"{prefix}.{node.attr}" if prefix is not None else node.attr
		return None

	def _matches_suffix(self, call_name: str, suffixes: set[str]) -> bool:
		return any(call_name.endswith(suffix) for suffix in suffixes)

	def _add_edge(self, source: str, target: str, edge_type: str) -> None:
		key = (source, target, edge_type)
		self._edges[key] = {"source": source, "target": target, "edge_type": edge_type}


__all__ = ["PythonDataFlowAnalyzer", "PythonDataFlowEdge"]
