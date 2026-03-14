from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from models.schemas import EdgeType, Node


class KnowledgeGraph:
	def __init__(self) -> None:
		self.graph = nx.DiGraph()

	def add_node(self, node: Node) -> None:
		node_payload = node.model_dump(mode="json")
		self.graph.add_node(node.id, **node_payload)

	def add_edge(self, source: Node | str, target: Node | str, edge_type: EdgeType, **metadata: Any) -> None:
		source_id = source.id if isinstance(source, Node) else source
		target_id = target.id if isinstance(target, Node) else target
		edge_payload = {"edge_type": edge_type.value, **metadata}
		self.graph.add_edge(source_id, target_id, **edge_payload)

	def save_to_json(self, file_path: str | Path) -> None:
		destination = Path(file_path)
		destination.parent.mkdir(parents=True, exist_ok=True)

		try:
			graph_payload = nx.node_link_data(self.graph, edges="links")
		except TypeError:
			graph_payload = nx.node_link_data(self.graph)
			if "edges" in graph_payload and "links" not in graph_payload:
				graph_payload["links"] = graph_payload.pop("edges")

		with destination.open("w", encoding="utf-8") as output_file:
			json.dump(graph_payload, output_file, indent=2)

	@classmethod
	def load_from_json(cls, file_path: str | Path) -> KnowledgeGraph:
		source = Path(file_path)
		with source.open("r", encoding="utf-8") as input_file:
			graph_payload: dict[str, Any] = json.load(input_file)

		instance = cls()
		try:
			instance.graph = nx.node_link_graph(graph_payload, edges="links")
		except TypeError:
			if "links" in graph_payload and "edges" not in graph_payload:
				graph_payload = dict(graph_payload)
				graph_payload["edges"] = graph_payload.pop("links")
			instance.graph = nx.node_link_graph(graph_payload)
		return instance


__all__ = ["KnowledgeGraph"]
