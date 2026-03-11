from __future__ import annotations

from collections import deque
from pathlib import Path

from analyzers.dag_config_parser import parse_dbt_yaml
from analyzers.sql_lineage import parse_dbt_sql
from graph.knowledge_graph import KnowledgeGraph
from models.schemas import DatasetNode, EdgeType, TransformationNode


class HydrologistAgent:
	def __init__(self, repository_path: str | Path) -> None:
		self.repository_path = Path(repository_path).resolve()
		self.knowledge_graph = KnowledgeGraph()

	def build_lineage_graph(self) -> KnowledgeGraph:
		self.knowledge_graph = KnowledgeGraph()

		for yaml_file in self._iter_yaml_files():
			for node in parse_dbt_yaml(yaml_file):
				self.knowledge_graph.add_node(node)

		for sql_file in self._iter_files((".sql",)):
			self._register_dbt_sql_lineage(sql_file)

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

	def find_sources(self) -> list[str]:
		return self.find_source_nodes()

	def find_sinks(self) -> list[str]:
		return self.find_sink_nodes()

	def _iter_files(self, suffixes: tuple[str, ...]):
		for file_path in self.repository_path.rglob("*"):
			if not file_path.is_file() or file_path.suffix.lower() not in suffixes:
				continue
			relative_parts = file_path.relative_to(self.repository_path).parts
			if any(part in {".cartography", ".git", ".venv", "__pycache__", "build", "dist", "target", "tmp"} for part in relative_parts):
				continue
			yield file_path

	def _iter_yaml_files(self):
		for file_path in self._iter_files((".yml",)):
			if file_path.name == "dbt_project.yml":
				continue
			yield file_path

	def _register_dbt_sql_lineage(self, sql_file: Path) -> None:
		relative_sql_path = sql_file.relative_to(self.repository_path)
		relative_sql_id = relative_sql_path.as_posix()

		for edge in parse_dbt_sql(sql_file):
			source_id = self._normalize_sql_endpoint(edge["source"], sql_file, relative_sql_id)
			target_id = self._normalize_sql_endpoint(edge["target"], sql_file, relative_sql_id)
			edge_type = EdgeType(edge["edge_type"])

			self._ensure_lineage_node(source_id, edge_type=edge_type, is_source=True)
			self._ensure_lineage_node(target_id, edge_type=edge_type, is_source=False)
			self.knowledge_graph.add_edge(source_id, target_id, edge_type)

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

	def _ensure_transformation_node(self, transformation_id: str) -> str:
		if transformation_id not in self.knowledge_graph.graph:
			self.knowledge_graph.add_node(TransformationNode(id=transformation_id))
		return transformation_id

	def _ensure_lineage_node(self, node_id: str, edge_type: EdgeType, is_source: bool) -> str:
		if node_id.endswith(".sql"):
			return self._ensure_transformation_node(node_id)

		storage_type = "dbt_model"
		if edge_type == EdgeType.CONSUMES and is_source and "." in node_id:
			storage_type = "dbt_source"
		return self._ensure_dataset_node(node_id, storage_type=storage_type)

	def _normalize_sql_endpoint(self, node_id: str, sql_file: Path, relative_sql_id: str) -> str:
		absolute_sql_id = sql_file.as_posix()
		return relative_sql_id if node_id == absolute_sql_id else node_id


__all__ = ["HydrologistAgent"]
