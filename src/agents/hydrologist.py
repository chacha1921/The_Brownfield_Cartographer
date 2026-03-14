from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import TypedDict

from analyzers.dag_config_parser import DAGConfigAnalyzer
from analyzers.python_data_flow import PythonDataFlowAnalyzer
from analyzers.sql_lineage import SQLLineageAnalyzer
from graph.knowledge_graph import KnowledgeGraph
from models.schemas import DatasetNode, EdgeType, TransformationNode


class LineageEdge(TypedDict):
	source: str
	target: str
	edge_type: str


class HydrologistAgent:
	def __init__(self, repository_path: str | Path, *, dialect: str = "postgres") -> None:
		self.repository_path = Path(repository_path).resolve()
		self.dialect = dialect
		self.knowledge_graph = KnowledgeGraph()
		self.python_data_flow_analyzer = PythonDataFlowAnalyzer(dialect=dialect)
		self.sql_lineage_analyzer = SQLLineageAnalyzer(dialect=dialect)
		self.dag_config_analyzer = DAGConfigAnalyzer()

	def build_lineage_graph(self) -> KnowledgeGraph:
		self.knowledge_graph = KnowledgeGraph()
		self.knowledge_graph.graph.graph.update(
			{
				"sql_dialect": self.dialect,
				"unresolved_dynamic_references": [],
				"lineage_merge_logic": {
					"python": "Python IO and embedded SQL produce CONSUMES/PRODUCES edges.",
					"sql": "Standalone SQL and dbt models produce file-backed lineage edges.",
					"config": "Airflow/dbt YAML config contributes CONFIGURES edges and resource nodes.",
				},
			}
		)

		for yaml_file in self._iter_files((".yml", ".yaml")):
			if yaml_file.name == "dbt_project.yml":
				continue
			for node in self.dag_config_analyzer.parse_dbt_resources(yaml_file):
				self.knowledge_graph.add_node(node)

		for python_file in self._iter_files((".py",)):
			python_edges = self.python_data_flow_analyzer.analyze_file(python_file)
			self._register_lineage_edges(python_file, python_edges)
			self.knowledge_graph.graph.graph["unresolved_dynamic_references"].extend(self.python_data_flow_analyzer.unresolved_references)
			self._register_airflow_topology(python_file)

		for sql_file in self._iter_files((".sql",)):
			self._register_lineage_edges(sql_file, self.sql_lineage_analyzer.analyze_file(sql_file))

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

	def _register_lineage_edges(self, file_path: Path, edges: list[LineageEdge]) -> None:
		relative_file_id = file_path.relative_to(self.repository_path).as_posix()
		absolute_file_id = file_path.as_posix()

		for edge in edges:
			source_id = self._normalize_file_endpoint(edge["source"], absolute_file_id, relative_file_id)
			target_id = self._normalize_file_endpoint(edge["target"], absolute_file_id, relative_file_id)
			edge_type = EdgeType(edge["edge_type"])

			self._ensure_lineage_node(source_id, edge_type=edge_type, is_source=True)
			self._ensure_lineage_node(target_id, edge_type=edge_type, is_source=False)
			self.knowledge_graph.add_edge(
				source_id,
				target_id,
				edge_type,
				source_file=edge.get("source_file", relative_file_id),
				line_start=int(edge.get("line_start", 1)),
				line_end=int(edge.get("line_end", edge.get("line_start", 1) or 1)),
				transformation_type=edge.get("transformation_type", "unknown"),
				dialect=edge.get("dialect", self.dialect),
			)

	def _register_airflow_topology(self, python_file: Path) -> None:
		parsed_dag = self.dag_config_analyzer.analyze_airflow_dag(python_file)
		if not parsed_dag["tasks"]:
			return

		relative_file_id = python_file.relative_to(self.repository_path).as_posix()
		for task in parsed_dag["tasks"]:
			task_node_id = self._airflow_task_node_id(relative_file_id, task["task_id"])
			self._ensure_transformation_node(task_node_id)
			self.knowledge_graph.graph.nodes[task_node_id]["operator"] = task["operator"]
			self.knowledge_graph.graph.nodes[task_node_id]["source_file"] = relative_file_id

		for upstream_task_id, downstream_task_id in parsed_dag["dependencies"]:
			self.knowledge_graph.add_edge(
				self._airflow_task_node_id(relative_file_id, upstream_task_id),
				self._airflow_task_node_id(relative_file_id, downstream_task_id),
				EdgeType.CONFIGURES,
			)

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
		if edge_type == EdgeType.CONFIGURES:
			return self._ensure_transformation_node(node_id)

		if edge_type == EdgeType.PRODUCES and is_source:
			return self._ensure_transformation_node(node_id)

		if edge_type == EdgeType.CONSUMES and not is_source:
			return self._ensure_transformation_node(node_id)

		storage_type = self._infer_storage_type(node_id)
		if edge_type == EdgeType.CONSUMES and is_source and "." in node_id and "/" not in node_id and storage_type == "table":
			storage_type = "dbt_source"
		return self._ensure_dataset_node(node_id, storage_type=storage_type)

	def _normalize_file_endpoint(self, node_id: str, absolute_file_id: str, relative_file_id: str) -> str:
		return relative_file_id if node_id == absolute_file_id else node_id

	def _infer_storage_type(self, node_id: str) -> str:
		normalized = node_id.lower()
		if node_id.startswith("dynamic://"):
			return "dynamic_reference"
		if normalized.startswith(("s3://", "gs://", "dbfs:/")):
			return "object_store"
		if "/" in node_id or normalized.endswith((".csv", ".json", ".jsonl", ".parquet", ".avro", ".txt")):
			return "file"
		return "table"

	def _airflow_task_node_id(self, relative_file_id: str, task_id: str) -> str:
		return f"airflow:{relative_file_id}:{task_id}"


__all__ = ["HydrologistAgent"]
