from __future__ import annotations

from collections import deque
from pathlib import Path
import re

from analyzers.sql_lineage import extract_sql_dependencies
from graph.knowledge_graph import KnowledgeGraph
from models.schemas import DatasetNode, EdgeType, TransformationNode


class HydrologistAgent:
	def __init__(self, repository_path: str | Path) -> None:
		self.repository_path = Path(repository_path).resolve()
		self.knowledge_graph = KnowledgeGraph()

	def build_lineage_graph(self) -> KnowledgeGraph:
		self.knowledge_graph = KnowledgeGraph()

		for yaml_file in self._iter_files((".yml",)):
			self._register_dbt_yaml_nodes(yaml_file)

		for sql_file in self._iter_files((".sql",)):
			self._register_sql_lineage(sql_file)

		return self.knowledge_graph

	def blast_radius(self, node_name: str) -> list[str]:
		if node_name not in self.knowledge_graph.graph:
			return []

		visited = {node_name}
		queue: deque[str] = deque([node_name])
		downstream_datasets: list[str] = []

		while queue:
			current = queue.popleft()
			for neighbor in self.knowledge_graph.graph.successors(current):
				if neighbor in visited:
					continue
				visited.add(neighbor)
				queue.append(neighbor)

				if self.knowledge_graph.graph.nodes[neighbor].get("node_type") == "dataset":
					downstream_datasets.append(neighbor)

		return downstream_datasets

	def find_source_nodes(self) -> list[str]:
		return [
			node_id
			for node_id, attributes in self.knowledge_graph.graph.nodes(data=True)
			if attributes.get("node_type") == "dataset"
			and self.knowledge_graph.graph.in_degree(node_id) == 0
			and self.knowledge_graph.graph.out_degree(node_id) > 0
		]

	def find_sink_nodes(self) -> list[str]:
		return [
			node_id
			for node_id, attributes in self.knowledge_graph.graph.nodes(data=True)
			if attributes.get("node_type") == "dataset"
			and self.knowledge_graph.graph.out_degree(node_id) == 0
			and self.knowledge_graph.graph.in_degree(node_id) > 0
		]

	def _iter_files(self, suffixes: tuple[str, ...]):
		for file_path in self.repository_path.rglob("*"):
			if not file_path.is_file() or file_path.suffix.lower() not in suffixes:
				continue
			if any(part in {".git", ".venv", "__pycache__", "target", "build", "dist"} for part in file_path.parts):
				continue
			yield file_path

	def _register_sql_lineage(self, sql_file: Path) -> None:
		dependencies = extract_sql_dependencies(sql_file.read_text(encoding="utf-8"))
		target_table = dependencies["target_table"]
		if target_table is None:
			return

		target_node = self._ensure_dataset_node(target_table)
		transformation_id = sql_file.relative_to(self.repository_path).as_posix()
		transformation_node = TransformationNode(id=transformation_id)
		self.knowledge_graph.add_node(transformation_node)
		self.knowledge_graph.add_edge(transformation_node, target_node, EdgeType.PRODUCES)

		for source_table in dependencies["source_tables"]:
			source_node = self._ensure_dataset_node(source_table)
			self.knowledge_graph.add_edge(source_node, transformation_node, EdgeType.CONSUMES)

	def _register_dbt_yaml_nodes(self, yaml_file: Path) -> None:
		section: str | None = None
		source_name: str | None = None
		in_tables_block = False

		for raw_line in yaml_file.read_text(encoding="utf-8").splitlines():
			line = raw_line.rstrip()
			stripped = line.strip()

			if not stripped or stripped.startswith("#"):
				continue

			if stripped == "sources:":
				section = "sources"
				source_name = None
				in_tables_block = False
				continue

			if stripped == "models:":
				section = "models"
				source_name = None
				in_tables_block = False
				continue

			if section == "sources":
				if stripped == "tables:":
					in_tables_block = True
					continue

				name_match = re.match(r"^-\s+name:\s+(.+)$", stripped)
				if name_match:
					value = _strip_yaml_scalar(name_match.group(1))
					if in_tables_block and source_name:
						self._ensure_dataset_node(f"{source_name}.{value}", storage_type="dbt_source")
					else:
						source_name = value
						in_tables_block = False
					continue

			if section == "models":
				name_match = re.match(r"^-\s+name:\s+(.+)$", stripped)
				if name_match:
					model_name = _strip_yaml_scalar(name_match.group(1))
					self._ensure_dataset_node(model_name, storage_type="dbt_model")

	def _ensure_dataset_node(self, dataset_name: str, storage_type: str = "table") -> str:
		if dataset_name not in self.knowledge_graph.graph:
			self.knowledge_graph.add_node(
				DatasetNode(
					id=dataset_name,
					name=dataset_name,
					storage_type=storage_type,
				)
			)
		return dataset_name


def _strip_yaml_scalar(value: str) -> str:
	return value.strip().strip("\"'")


__all__ = ["HydrologistAgent"]
