from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, TypedDict

import networkx as nx
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from graph.knowledge_graph import KnowledgeGraph
from models.schemas import EdgeType

try:
	import importlib
except ImportError:  # pragma: no cover - dependency availability varies by environment
	importlib = None

from agents.semanticist import SemanticistAgent


class FindImplementationInput(BaseModel):
	concept: str = Field(..., description="Business concept or implementation concern to search for.")


class TraceLineageInput(BaseModel):
	dataset: str = Field(..., description="Dataset or table name to trace.")
	direction: str = Field(..., description="Either upstream or downstream.")


class BlastRadiusInput(BaseModel):
	module_path: str = Field(..., description="Repository-relative module path.")


class ExplainModuleInput(BaseModel):
	path: str = Field(..., description="Repository-relative module path to explain.")


class NavigatorState(TypedDict, total=False):
	query: str
	tool_name: str
	tool_input: dict[str, Any]
	tool_output: dict[str, Any]
	tool_sequence: list[str]
	response: str


@dataclass(slots=True)
class PurposeIndexEntry:
	path: str
	purpose_statement: str
	line_start: int
	line_end: int


class NavigatorAgent:
	SYSTEM_PROMPT = (
		"You are the Brownfield Cartographer Navigator. Every answer must cite evidence with source file, "
		"line range, and the analysis method used. If evidence is incomplete, say so explicitly instead of guessing."
	)

	def __init__(
		self,
		repository_path: str | Path,
		knowledge_graph: KnowledgeGraph | nx.DiGraph,
		*,
		semanticist: SemanticistAgent | None = None,
	) -> None:
		self.repository_path = Path(repository_path).resolve()
		self.graph = self._coerce_graph(knowledge_graph)
		self.semanticist = semanticist or SemanticistAgent(self.repository_path)
		self._purpose_entries: list[PurposeIndexEntry] | None = None
		self._purpose_vectors: Any = None
		self._purpose_vectorizer: TfidfVectorizer | None = None
		self._embedding_backend: str = "tfidf"
		self.tools = self._build_tools()
		self.app = self._build_graph()

	def answer(self, query: str, *, tool_name: str | None = None, tool_input: dict[str, Any] | None = None) -> str:
		state: NavigatorState = {"query": query, "tool_input": tool_input or {}}
		if tool_name:
			state["tool_name"] = tool_name
		result = self.app.invoke(state)
		return result["response"]

	def _build_tools(self) -> dict[str, Any]:
		structured_tool = self._load_structured_tool()
		if structured_tool is None:
			raise RuntimeError("NavigatorAgent requires langgraph and langchain-core to be installed.")

		return {
			"find_implementation": structured_tool.from_function(
				func=self.find_implementation,
				name="find_implementation",
				description="Semantic search over module purpose statements.",
				args_schema=FindImplementationInput,
			),
			"trace_lineage": structured_tool.from_function(
				func=self.trace_lineage,
				name="trace_lineage",
				description="Trace dataset lineage upstream or downstream using PRODUCES/CONSUMES edges.",
				args_schema=TraceLineageInput,
			),
			"blast_radius": structured_tool.from_function(
				func=self.blast_radius,
				name="blast_radius",
				description="Find all downstream dependents affected by a module change.",
				args_schema=BlastRadiusInput,
			),
			"explain_module": structured_tool.from_function(
				func=self.explain_module,
				name="explain_module",
				description="Explain a module using its source code and graph edges.",
				args_schema=ExplainModuleInput,
			),
		}

	def _build_graph(self):
		state_graph, end_marker = self._load_langgraph_symbols()
		if state_graph is None:
			raise RuntimeError("NavigatorAgent requires langgraph to be installed.")

		workflow = state_graph(NavigatorState)
		workflow.add_node("route", self._route_query)
		workflow.add_node("execute", self._execute_tool)
		workflow.add_node("format", self._format_response)
		workflow.set_entry_point("route")
		workflow.add_edge("route", "execute")
		workflow.add_edge("execute", "format")
		workflow.add_edge("format", end_marker)
		return workflow.compile()

	def _route_query(self, state: NavigatorState) -> NavigatorState:
		if state.get("tool_name"):
			return state

		query = state.get("query", "").strip()
		lowered = query.lower()
		if "lineage" in lowered or "upstream" in lowered or "downstream" in lowered:
			direction = "upstream" if "upstream" in lowered else "downstream"
			return {**state, "tool_name": "trace_lineage", "tool_input": {"dataset": query, "direction": direction}}
		if "blast radius" in lowered or "dependents" in lowered or "impact" in lowered:
			return {**state, "tool_name": "blast_radius", "tool_input": {"module_path": self._extract_last_path_token(query)}}
		if "explain" in lowered:
			return {**state, "tool_name": "explain_module", "tool_input": {"path": self._extract_last_path_token(query)}}
		return {**state, "tool_name": "find_implementation", "tool_input": {"concept": query}}

	def _execute_tool(self, state: NavigatorState) -> NavigatorState:
		tool_name = state["tool_name"]
		tool = self.tools[tool_name]
		tool_output = tool.invoke(state.get("tool_input", {}))
		sequence = list(state.get("tool_sequence", []))
		sequence.append(tool_name)
		return {**state, "tool_output": tool_output, "tool_sequence": sequence}

	def _format_response(self, state: NavigatorState) -> NavigatorState:
		payload = state.get("tool_output", {})
		answer = str(payload.get("answer", "No answer available.")).strip()
		evidence = payload.get("evidence", [])
		if not evidence:
			raise RuntimeError("Navigator responses must include evidence citations.")

		lines = [answer, "", "Evidence:"]
		for item in evidence:
			source_file = item.get("source_file", "unknown")
			line_start = item.get("line_start", 1)
			line_end = item.get("line_end", line_start)
			analysis_method = item.get("analysis_method", "static-analysis")
			lines.append(f"- {source_file}:L{line_start}-L{line_end} via {analysis_method}")

		tool_sequence = state.get("tool_sequence", [])
		if tool_sequence:
			lines.extend(["", "Tool sequence:"])
			lines.extend(f"- {tool_name}" for tool_name in tool_sequence)

		response = f"{self.SYSTEM_PROMPT}\n\n" + "\n".join(lines)
		return {**state, "response": response}

	def find_implementation(self, concept: str) -> dict[str, Any]:
		entries = self._get_purpose_entries()
		if not entries:
			return {
				"answer": f"No purpose statements are available yet for concept '{concept}'.",
				"evidence": [{"source_file": ".cartography/module_graph.json", "line_start": 1, "line_end": 1, "analysis_method": "semantic-index"}],
			}

		scores = self._search_purpose_index(concept)
		top_matches = sorted(scores, key=lambda item: item[1], reverse=True)[:5]
		match_lines = [f"{entry.path} ({score:.3f}) — {entry.purpose_statement}" for entry, score in top_matches]
		evidence = [
			{
				"source_file": entry.path,
				"line_start": entry.line_start,
				"line_end": entry.line_end,
				"analysis_method": "semantic-index",
			}
			for entry, _ in top_matches
		]
		return {
			"answer": f"Top implementation matches for '{concept}' using {self._embedding_backend}:\n" + "\n".join(f"- {line}" for line in match_lines),
			"evidence": evidence,
		}

	def trace_lineage(self, dataset: str, direction: str) -> dict[str, Any]:
		node_id = dataset.strip()
		if node_id not in self.graph:
			candidate = self._resolve_dataset_node(node_id)
			if candidate is None:
				return {
					"answer": f"Dataset '{dataset}' is not present in the knowledge graph.",
					"evidence": [{"source_file": ".cartography/lineage_graph.json", "line_start": 1, "line_end": 1, "analysis_method": "static-analysis"}],
				}
			node_id = candidate

		direction_normalized = direction.strip().lower()
		if direction_normalized not in {"upstream", "downstream"}:
			raise ValueError("direction must be either 'upstream' or 'downstream'.")

		traversal = self._traverse_lineage(node_id, direction_normalized)
		if not traversal:
			return {
				"answer": f"No {direction_normalized} lineage found for '{node_id}'.",
				"evidence": self._node_evidence(node_id, analysis_method="static-analysis"),
			}

		answer_lines = [f"{direction_normalized.title()} lineage for '{node_id}':"]
		for dataset_name in traversal:
			answer_lines.append(f"- {dataset_name}")
		evidence = self._lineage_evidence([node_id, *traversal])
		return {"answer": "\n".join(answer_lines), "evidence": evidence}

	def blast_radius(self, module_path: str) -> dict[str, Any]:
		target = module_path.strip()
		if target not in self.graph:
			return {
				"answer": f"Module '{target}' is not present in the knowledge graph.",
				"evidence": [{"source_file": ".cartography/module_graph.json", "line_start": 1, "line_end": 1, "analysis_method": "static-analysis"}],
			}

		reverse_graph = self.graph.reverse(copy=False)
		visited = {target}
		queue: deque[str] = deque([target])
		impacted: list[str] = []
		while queue:
			current = queue.popleft()
			for dependent in reverse_graph.successors(current):
				if dependent in visited:
					continue
				visited.add(dependent)
				queue.append(dependent)
				impacted.append(dependent)

		if not impacted:
			return {
				"answer": f"No downstream dependents found for '{target}'.",
				"evidence": self._node_evidence(target, analysis_method="static-analysis"),
			}

		answer = f"Blast radius for '{target}' includes {len(impacted)} downstream dependents:\n" + "\n".join(f"- {node}" for node in impacted)
		evidence = self._node_evidence(target, analysis_method="static-analysis") + self._lineage_evidence(impacted)
		return {"answer": answer, "evidence": evidence[:10]}

	def explain_module(self, path: str) -> dict[str, Any]:
		module_path = path.strip()
		absolute_path = self.repository_path / module_path
		if not absolute_path.exists():
			return {
				"answer": f"Module '{module_path}' does not exist in the repository.",
				"evidence": [{"source_file": module_path, "line_start": 1, "line_end": 1, "analysis_method": "static-analysis"}],
			}

		code = absolute_path.read_text(encoding="utf-8")
		line_count = max(1, len(code.splitlines()))
		predecessors = sorted(self.graph.predecessors(module_path)) if module_path in self.graph else []
		successors = sorted(self.graph.successors(module_path)) if module_path in self.graph else []
		prompt = (
			"Explain this module for an engineer onboarding to a brownfield codebase. Summarize its responsibility, "
			"the most important dependencies, and the likely impact of changing it. Return JSON with a single key explanation.\n\n"
			f"Path: {module_path}\n"
			f"Incoming edges: {json.dumps(predecessors)}\n"
			f"Outgoing edges: {json.dumps(successors)}\n"
			f"Code:\n{code[:12000]}"
		)

		analysis_method = "llm-inference"
		try:
			provider, model = self.semanticist.budget.task_descriptor("bulk_summary")
			payload = self.semanticist._llm_client_for(provider).generate_json(model=model, prompt=prompt, temperature=0.1)
			explanation = str(payload.get("explanation", "")).strip()
			if not explanation:
				raise RuntimeError("LLM explanation did not include explanation text.")
		except Exception:
			analysis_method = "static-analysis"
			explanation = (
				f"{module_path} participates in {len(predecessors)} incoming and {len(successors)} outgoing graph relationships. "
				f"Review the imports and function entry points first, then inspect how its downstream consumers rely on its outputs."
			)

		evidence = [
			{"source_file": module_path, "line_start": 1, "line_end": min(40, line_count), "analysis_method": analysis_method},
			*[
				{"source_file": item, "line_start": 1, "line_end": 1, "analysis_method": "static-analysis"}
				for item in [*predecessors[:3], *successors[:3]]
			],
		]
		return {"answer": explanation, "evidence": evidence}

	def _coerce_graph(self, knowledge_graph: KnowledgeGraph | nx.DiGraph) -> nx.DiGraph:
		if isinstance(knowledge_graph, KnowledgeGraph):
			return knowledge_graph.graph
		if isinstance(knowledge_graph, nx.DiGraph):
			return knowledge_graph
		raise TypeError("Expected KnowledgeGraph or networkx.DiGraph.")

	def _get_purpose_entries(self) -> list[PurposeIndexEntry]:
		if self._purpose_entries is not None:
			return self._purpose_entries

		entries: list[PurposeIndexEntry] = []
		for node_id, attrs in self.graph.nodes(data=True):
			if attrs.get("node_type") != "module":
				continue
			purpose_statement = attrs.get("purpose_statement")
			path = attrs.get("path") or node_id
			if not isinstance(path, str) or not isinstance(purpose_statement, str) or not purpose_statement.strip():
				continue
			line_start, line_end = self._module_line_range(path)
			entries.append(PurposeIndexEntry(path=path, purpose_statement=purpose_statement.strip(), line_start=line_start, line_end=line_end))

		self._purpose_entries = entries
		self._build_purpose_index(entries)
		return entries

	def _build_purpose_index(self, entries: list[PurposeIndexEntry]) -> None:
		texts = [entry.purpose_statement for entry in entries]
		if not texts:
			self._purpose_vectorizer = None
			self._purpose_vectors = None
			self._embedding_backend = "tfidf"
			return

		try:
			provider, model = self.semanticist.budget.task_descriptor("embedding")
			self._purpose_vectors = self.semanticist._embedding_client_for(provider).embed_texts(texts, model=model)
			self._purpose_vectorizer = (provider, model)
			self._embedding_backend = f"{provider}-embeddings"
			return
		except Exception:
			self._purpose_vectorizer = None
			self._purpose_vectors = None

		vectorizer = TfidfVectorizer(stop_words="english")
		self._purpose_vectors = vectorizer.fit_transform(texts)
		self._purpose_vectorizer = vectorizer
		self._embedding_backend = "tfidf"

	def _search_purpose_index(self, concept: str) -> list[tuple[PurposeIndexEntry, float]]:
		entries = self._purpose_entries or []
		if not entries or self._purpose_vectors is None:
			return []

		if self._embedding_backend != "tfidf" and isinstance(self._purpose_vectorizer, tuple):
			provider, model = self._purpose_vectorizer
			query_vector = self.semanticist._embedding_client_for(provider).embed_texts([concept], model=model)[0]
			scores = cosine_similarity([query_vector], self._purpose_vectors)[0]
			return list(zip(entries, [float(score) for score in scores], strict=False))

		if self._purpose_vectorizer is None:
			return []

		query_vector = self._purpose_vectorizer.transform([concept])
		scores = cosine_similarity(query_vector, self._purpose_vectors)[0]
		return list(zip(entries, [float(score) for score in scores], strict=False))

	def _traverse_lineage(self, dataset: str, direction: str) -> list[str]:
		visited = {dataset}
		queue: deque[str] = deque([dataset])
		results: list[str] = []
		while queue:
			current = queue.popleft()
			neighbors = self.graph.predecessors(current) if direction == "upstream" else self.graph.successors(current)
			for neighbor in neighbors:
				if neighbor in visited:
					continue
				edge_payload = self.graph.get_edge_data(neighbor, current, default={}) if direction == "upstream" else self.graph.get_edge_data(current, neighbor, default={})
				edge_type = edge_payload.get("edge_type")
				if edge_type not in {EdgeType.PRODUCES.value, EdgeType.CONSUMES.value}:
					continue
				visited.add(neighbor)
				queue.append(neighbor)
				if self.graph.nodes[neighbor].get("node_type") == "dataset":
					results.append(neighbor)
		return results

	def _resolve_dataset_node(self, dataset: str) -> str | None:
		for node_id, attrs in self.graph.nodes(data=True):
			if attrs.get("node_type") == "dataset" and dataset in {node_id, attrs.get("name")}:
				return node_id
		return None

	def _lineage_evidence(self, nodes: list[str]) -> list[dict[str, Any]]:
		evidence: list[dict[str, Any]] = []
		for node in nodes:
			evidence.extend(self._node_evidence(node, analysis_method="static-analysis"))
		return evidence[:10]

	def _node_evidence(self, node: str, *, analysis_method: str) -> list[dict[str, Any]]:
		attrs = self.graph.nodes.get(node, {})
		source_file = attrs.get("source_file") or attrs.get("path") or node
		line_start, line_end = self._module_line_range(source_file) if isinstance(source_file, str) and "/" in source_file else (1, 1)
		return [{"source_file": source_file, "line_start": line_start, "line_end": line_end, "analysis_method": analysis_method}]

	def _module_line_range(self, path: str) -> tuple[int, int]:
		absolute_path = self.repository_path / path
		if not absolute_path.exists():
			return 1, 1
		lines = absolute_path.read_text(encoding="utf-8").splitlines()
		if not lines:
			return 1, 1
		try:
			module = ast.parse("\n".join(lines))
			docstring_node = module.body[0] if module.body else None
			if isinstance(docstring_node, ast.Expr) and isinstance(getattr(docstring_node, "value", None), ast.Constant) and isinstance(docstring_node.value.value, str):
				return docstring_node.lineno, docstring_node.end_lineno or docstring_node.lineno
		except SyntaxError:
			pass
		return 1, min(20, len(lines))

	def _extract_last_path_token(self, query: str) -> str:
		for token in reversed(query.split()):
			cleaned = token.strip("`'\".,:;()[]{}")
			if "/" in cleaned or cleaned.endswith(".py"):
				return cleaned
		return query.strip()

	def _load_structured_tool(self):
		if importlib is None:
			return None
		try:
			return importlib.import_module("langchain_core.tools").StructuredTool
		except ImportError:
			return None

	def _load_langgraph_symbols(self):
		if importlib is None:
			return None, "__end__"
		try:
			module = importlib.import_module("langgraph.graph")
			return module.StateGraph, module.END
		except ImportError:
			return None, "__end__"


__all__ = ["NavigatorAgent"]
