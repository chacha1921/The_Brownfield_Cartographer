from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import networkx as nx

from graph.knowledge_graph import KnowledgeGraph


class ArchivistAgent:
    def __init__(self, repository_path: str | Path) -> None:
        self.repository_path = Path(repository_path).resolve()
        self.output_dir = self.repository_path / ".cartography"
        self.trace_path = self.output_dir / "cartography_trace.jsonl"

    def generate_CODEBASE_md(self, knowledge_graph: KnowledgeGraph | nx.DiGraph) -> str:
        graph = self._coerce_graph(knowledge_graph)
        architecture_overview = self._architecture_overview(graph)
        critical_path = self._critical_path(graph)
        data_sources, data_sinks = self._data_sources_and_sinks(graph)
        known_debt = self._known_debt(graph)
        high_velocity_files = self._high_velocity_files(graph)

        markdown_lines = [
            "# CODEBASE",
            "",
            "## Architecture Overview",
            architecture_overview,
            "",
            "## Critical Path",
        ]
        markdown_lines.extend(f"- {item}" for item in critical_path)
        markdown_lines.extend([
            "",
            "## Data Sources & Sinks",
            "### Sources",
        ])
        markdown_lines.extend(f"- {item}" for item in data_sources)
        markdown_lines.extend([
            "",
            "### Sinks",
        ])
        markdown_lines.extend(f"- {item}" for item in data_sinks)
        markdown_lines.extend([
            "",
            "## Known Debt",
        ])
        markdown_lines.extend(f"- {item}" for item in known_debt)
        markdown_lines.extend([
            "",
            "## High-Velocity Files",
        ])
        markdown_lines.extend(f"- {item}" for item in high_velocity_files)
        markdown = "\n".join(markdown_lines)

        self.log_trace(
            action="generate_CODEBASE_md",
            evidence=[{"source_file": ".cartography/module_graph.json", "line_start": 1, "line_end": 1, "analysis_method": "static-analysis"}],
            confidence=0.85,
        )
        return markdown

    def generate_onboarding_brief(self, day_one_answers: list[dict[str, Any]] | dict[str, Any]) -> str:
        answers = day_one_answers.get("answers", []) if isinstance(day_one_answers, dict) else day_one_answers
        lines = [
            "# onboarding_brief",
            "",
            "This brief summarizes the semantic synthesis for a new forward-deployed engineer joining the codebase.",
            "",
        ]

        for answer in answers:
            question = str(answer.get("question", "Untitled question")).strip()
            response = str(answer.get("answer", "")).strip()
            citations = answer.get("citations", [])
            lines.extend([
                f"## {question}",
                response or "No answer available.",
            ])
            if citations:
                lines.append("")
                lines.append("Evidence:")
                for citation in citations:
                    path = citation.get("path", "unknown")
                    line_start = citation.get("line_start", 1)
                    line_end = citation.get("line_end", line_start)
                    lines.append(f"- {path}:L{line_start}-L{line_end} via llm-inference")
            lines.append("")

        markdown = "\n".join(lines).rstrip() + "\n"
        self.log_trace(
            action="generate_onboarding_brief",
            evidence=self._normalize_evidence(
                [
                    {
                        "source_file": citation.get("path", "unknown"),
                        "line_start": citation.get("line_start", 1),
                        "line_end": citation.get("line_end", citation.get("line_start", 1)),
                        "analysis_method": "llm-inference",
                    }
                    for answer in answers
                    for citation in answer.get("citations", [])
                ]
            ),
            confidence=0.8,
        )
        return markdown

    def log_trace(self, action: str, evidence: Any, confidence: float) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "confidence": float(confidence),
            "evidence": self._normalize_evidence(evidence),
        }
        with self.trace_path.open("a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(record) + "\n")

    def _coerce_graph(self, knowledge_graph: KnowledgeGraph | nx.DiGraph) -> nx.DiGraph:
        if isinstance(knowledge_graph, KnowledgeGraph):
            return knowledge_graph.graph
        if isinstance(knowledge_graph, nx.DiGraph):
            return knowledge_graph
        raise TypeError("Expected KnowledgeGraph or networkx.DiGraph.")

    def _architecture_overview(self, graph: nx.DiGraph) -> str:
        module_count = sum(1 for _, attrs in graph.nodes(data=True) if attrs.get("node_type") == "module")
        dataset_count = sum(1 for _, attrs in graph.nodes(data=True) if attrs.get("node_type") == "dataset")
        transformation_count = sum(1 for _, attrs in graph.nodes(data=True) if attrs.get("node_type") == "transformation")
        edge_count = graph.number_of_edges()
        hub_count = len(graph.graph.get("architectural_hubs", []))
        scc_count = len(graph.graph.get("strongly_connected_components", []))
        return (
            f"The codebase contains {module_count} modules, {dataset_count} datasets, and {transformation_count} transformations connected by {edge_count} graph edges. "
            f"Its structure is centered around {hub_count} high-importance architectural hubs, with {scc_count} circular dependency clusters currently visible, which suggests the main operational shape, dependency pressure, and likely refactor hotspots for future work."
        )

    def _critical_path(self, graph: nx.DiGraph) -> list[str]:
        hubs = graph.graph.get("architectural_hubs")
        if isinstance(hubs, list) and hubs:
            top_modules = hubs[:5]
            return [f"{entry['path']} (PageRank={entry['pagerank']:.4f})" for entry in top_modules if isinstance(entry, dict)]

        module_graph = nx.DiGraph(
            (
                (source, target, attrs)
                for source, target, attrs in graph.edges(data=True)
                if attrs.get("edge_type") == "IMPORTS"
            )
        )
        for node_id, attrs in graph.nodes(data=True):
            if attrs.get("node_type") == "module":
                module_graph.add_node(node_id, **attrs)

        if not module_graph.nodes:
            return ["No module import data available."]

        ranks = nx.pagerank(module_graph)
        top_modules = sorted(ranks.items(), key=lambda item: item[1], reverse=True)[:5]
        return [f"{path} (PageRank={score:.4f})" for path, score in top_modules]

    def _data_sources_and_sinks(self, graph: nx.DiGraph) -> tuple[list[str], list[str]]:
        dataset_nodes = [node_id for node_id, attrs in graph.nodes(data=True) if attrs.get("node_type") == "dataset"]
        if not dataset_nodes:
            return ["No dataset lineage sources identified in the current repository scan."], ["No dataset lineage sinks identified in the current repository scan."]

        target_nodes = dataset_nodes

        sources = [node_id for node_id in target_nodes if graph.in_degree(node_id) == 0]
        sinks = [node_id for node_id in target_nodes if graph.out_degree(node_id) == 0]

        return self._fallback_list(sources, "No source nodes identified."), self._fallback_list(sinks, "No sink nodes identified.")

    def _known_debt(self, graph: nx.DiGraph) -> list[str]:
        debt_items: list[str] = []
        for component in graph.graph.get("strongly_connected_components", []):
            if isinstance(component, list) and component:
                debt_items.append(f"Circular dependency: {' -> '.join(component)}")

        for node_id, attrs in graph.nodes(data=True):
            if attrs.get("documentation_drift"):
                debt_items.append(f"Documentation drift flagged in {node_id}")

        return self._fallback_list(debt_items, "No circular dependencies or documentation drift flags found.")

    def _high_velocity_files(self, graph: nx.DiGraph) -> list[str]:
        high_velocity_core = graph.graph.get("high_velocity_core", {})
        files = high_velocity_core.get("files", []) if isinstance(high_velocity_core, dict) else []
        entries = [
            f"{entry['path']} ({entry['change_count']} changes / {high_velocity_core.get('days', 30)}d)"
            for entry in files[:5]
            if isinstance(entry, dict) and "path" in entry and "change_count" in entry
        ]

        if not entries:
            module_entries = []
            for _, attrs in graph.nodes(data=True):
                path = attrs.get("path")
                velocity = attrs.get("change_velocity_30d")
                if isinstance(path, str) and isinstance(velocity, (int, float)):
                    module_entries.append((path, float(velocity)))
            module_entries.sort(key=lambda item: item[1], reverse=True)
            entries = [f"{path} ({velocity:.0f} changes / 30d)" for path, velocity in module_entries[:5] if velocity > 0]

        return self._fallback_list(entries, "No high-velocity file data available.")

    def _normalize_evidence(self, evidence: Any) -> list[dict[str, Any]]:
        if evidence is None:
            return []

        raw_items = evidence if isinstance(evidence, list) else [evidence]
        normalized: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "source_file": item.get("source_file") or item.get("path") or "unknown",
                    "line_start": int(item.get("line_start", 1)),
                    "line_end": int(item.get("line_end", item.get("line_start", 1) or 1)),
                    "analysis_method": item.get("analysis_method", "static-analysis"),
                }
            )
        return normalized

    def _fallback_list(self, items: list[str], fallback: str) -> list[str]:
        return items if items else [fallback]


__all__ = ["ArchivistAgent"]
