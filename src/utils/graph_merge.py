from __future__ import annotations

from typing import Any

import networkx as nx

from graph.knowledge_graph import KnowledgeGraph


def merge_cartography_graphs(
	module_graph: KnowledgeGraph | nx.DiGraph,
	lineage_graph: KnowledgeGraph | nx.DiGraph,
) -> KnowledgeGraph:
	merged = KnowledgeGraph()
	module_di_graph = _coerce_graph(module_graph)
	lineage_di_graph = _coerce_graph(lineage_graph)
	merged.graph = nx.compose(module_di_graph, lineage_di_graph)
	merged.graph.graph.update(
		{
			"module_graph_attributes": dict(module_di_graph.graph),
			"lineage_graph_attributes": dict(lineage_di_graph.graph),
			"graph_merge_logic": {
				"strategy": "networkx.compose",
				"node_precedence": "lineage attributes extend module attributes when node ids overlap",
				"edge_sources": ["module_graph.json", "lineage_graph.json"],
				"purpose_index_source": "module purpose_statement + domain_cluster attributes",
				"onboarding_citation_source": "day_one_answers citations propagated verbatim into onboarding_brief",
			},
		}
	)
	return merged


def _coerce_graph(knowledge_graph: KnowledgeGraph | nx.DiGraph) -> nx.DiGraph:
	if isinstance(knowledge_graph, KnowledgeGraph):
		return knowledge_graph.graph
	if isinstance(knowledge_graph, nx.DiGraph):
		return knowledge_graph
	raise TypeError("Expected KnowledgeGraph or networkx.DiGraph.")


__all__ = ["merge_cartography_graphs"]