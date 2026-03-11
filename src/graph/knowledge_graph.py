from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from models.schemas import EdgeType, Node


class KnowledgeGraph:
	def __init__(self) -> None:
		self.graph = nx.DiGraph()

	def add_node(self, node: Node) -> None:
		node_payload = node.model_dump(mode="json")
		self.graph.add_node(node.id, **node_payload)

	def add_edge(self, source: Node | str, target: Node | str, edge_type: EdgeType) -> None:
		source_id = source.id if isinstance(source, Node) else source
		target_id = target.id if isinstance(target, Node) else target
		self.graph.add_edge(source_id, target_id, edge_type=edge_type.value)

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


__all__ = ["KnowledgeGraph"]
