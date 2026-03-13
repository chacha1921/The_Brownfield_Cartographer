import json
from pathlib import Path
import subprocess
from typing import Any

from agents.archivist import ArchivistAgent
from agents.hydrologist import HydrologistAgent
from agents.semanticist import SemanticistAgent
from agents.surveyor import SurveyorAgent
from graph.knowledge_graph import KnowledgeGraph
from models.schemas import EdgeType, FunctionNode, ModuleNode


def get_changed_files(repo_path: str | Path, last_run_commit_hash: str | None) -> list[str]:
	repository_root = Path(repo_path).resolve()
	baseline_hash = (last_run_commit_hash or "").strip()

	if baseline_hash:
		command = ["git", "diff", "--name-only", baseline_hash, "HEAD"]
	else:
		command = ["git", "ls-files"]

	result = subprocess.run(
		command,
		cwd=repository_root,
		capture_output=True,
		text=True,
		check=True,
	)

	ignored_parts = {".cartography", ".git", ".venv", "__pycache__", "build", "dist", "target", "tmp"}
	changed_files: list[str] = []
	for raw_line in result.stdout.splitlines():
		relative_path = raw_line.strip()
		if not relative_path:
			continue
		if any(part in ignored_parts for part in Path(relative_path).parts):
			continue
		changed_files.append(relative_path)

	return changed_files


class Orchestrator:
	DAY_ONE_PROMPT_VERSION = 2

	def __init__(self, repo_path: str | Path) -> None:
		self.repo_path = Path(repo_path).resolve()
		self.output_dir = self.repo_path / ".cartography"
		self.module_graph_path = self.output_dir / "module_graph.json"
		self.lineage_graph_path = self.output_dir / "lineage_graph.json"
		self.codebase_path = self.output_dir / "CODEBASE.md"
		self.onboarding_brief_path = self.output_dir / "onboarding_brief.md"
		self.day_one_answers_path = self.output_dir / "day_one_answers.json"
		self.run_metadata_path = self.output_dir / "run_metadata.json"
		self.surveyor = SurveyorAgent(self.repo_path)
		self.hydrologist = HydrologistAgent(self.repo_path)
		self.semanticist = SemanticistAgent(self.repo_path)
		self.archivist = ArchivistAgent(self.repo_path)

	def run(self) -> dict[str, str]:
		self.output_dir.mkdir(parents=True, exist_ok=True)
		previous_metadata = self._load_run_metadata()
		incremental_candidates = self._load_changed_files(previous_metadata)
		has_saved_graphs = self._has_saved_graphs()

		used_incremental = has_saved_graphs and self._is_git_repository()
		if used_incremental:
			module_graph = KnowledgeGraph.load_from_json(self.module_graph_path)
			lineages_need_full_rebuild = self._requires_full_lineage_rebuild(incremental_candidates)
			lineage_graph = self._load_or_build_incremental_lineage_graph(incremental_candidates)
			if incremental_candidates:
				self._refresh_module_graph(module_graph, incremental_candidates)
			if lineages_need_full_rebuild:
				lineage_graph = self.hydrologist.build_lineage_graph()
			elif incremental_candidates:
				self._refresh_lineage_graph(lineage_graph, incremental_candidates)
			self.archivist.log_trace(
				action="incremental_refresh" if incremental_candidates else "incremental_noop",
				evidence=[{"source_file": path, "line_start": 1, "line_end": 1, "analysis_method": "git-diff"} for path in incremental_candidates],
				confidence=0.88 if incremental_candidates and not lineages_need_full_rebuild else 0.95 if not incremental_candidates else 0.8,
			)
		else:
			module_graph = self.surveyor.build_import_graph()
			lineage_graph = self.hydrologist.build_lineage_graph()
			incremental_candidates = []
			self.archivist.log_trace(
				action="full_rebuild",
				evidence={"source_file": ".cartography/module_graph.json", "line_start": 1, "line_end": 1, "analysis_method": "static-analysis"},
				confidence=0.9,
			)

		semantic_summary = self._enrich_module_graph(module_graph, incremental_candidates, force=not used_incremental)
		day_one_answers = self._generate_day_one_answers(
			module_graph,
			lineage_graph,
			semantic_summary,
			used_incremental,
			incremental_candidates,
			previous_metadata,
		)

		module_graph.save_to_json(self.module_graph_path)
		lineage_graph.save_to_json(self.lineage_graph_path)
		self._write_text_file(self.codebase_path, self.archivist.generate_CODEBASE_md(module_graph))
		self._write_text_file(self.onboarding_brief_path, self.archivist.generate_onboarding_brief(day_one_answers))
		self.day_one_answers_path.write_text(json.dumps(day_one_answers, indent=2), encoding="utf-8")
		self._save_run_metadata(changed_files=incremental_candidates, used_incremental=used_incremental)

		return {
			"module_graph": str(self.module_graph_path),
			"lineage_graph": str(self.lineage_graph_path),
			"codebase": str(self.codebase_path),
			"onboarding_brief": str(self.onboarding_brief_path),
			"day_one_answers": str(self.day_one_answers_path),
			"trace": str(self.archivist.trace_path),
		}

	def _load_changed_files(self, previous_metadata: dict[str, Any]) -> list[str]:
		if not self._is_git_repository() or not self._has_saved_graphs():
			return []

		try:
			return get_changed_files(self.repo_path, previous_metadata.get("last_run_commit"))
		except subprocess.CalledProcessError:
			return []

	def _has_saved_graphs(self) -> bool:
		return self.module_graph_path.exists() and self.lineage_graph_path.exists()

	def _is_git_repository(self) -> bool:
		result = subprocess.run(
			["git", "rev-parse", "--is-inside-work-tree"],
			cwd=self.repo_path,
			capture_output=True,
			text=True,
		)
		return result.returncode == 0 and result.stdout.strip() == "true"

	def _load_run_metadata(self) -> dict[str, Any]:
		if not self.run_metadata_path.exists():
			return {}
		try:
			return json.loads(self.run_metadata_path.read_text(encoding="utf-8"))
		except json.JSONDecodeError:
			return {}

	def _save_run_metadata(self, *, changed_files: list[str], used_incremental: bool) -> None:
		payload = {
			"last_run_commit": self._current_commit_hash(),
			"changed_files": changed_files,
			"used_incremental": used_incremental,
			"day_one_prompt_version": self.DAY_ONE_PROMPT_VERSION,
		}
		self.run_metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

	def _current_commit_hash(self) -> str | None:
		if not self._is_git_repository():
			return None
		result = subprocess.run(
			["git", "rev-parse", "HEAD"],
			cwd=self.repo_path,
			capture_output=True,
			text=True,
		)
		return result.stdout.strip() if result.returncode == 0 else None

	def _load_or_build_incremental_lineage_graph(self, changed_files: list[str]) -> KnowledgeGraph:
		if self._requires_full_lineage_rebuild(changed_files):
			return self.hydrologist.build_lineage_graph()
		return KnowledgeGraph.load_from_json(self.lineage_graph_path)

	def _requires_full_lineage_rebuild(self, changed_files: list[str]) -> bool:
		return any(Path(relative_path).suffix.lower() in {".yml", ".yaml"} for relative_path in changed_files)

	def _refresh_module_graph(self, module_graph: KnowledgeGraph, changed_files: list[str]) -> None:
		python_changes = [relative_path for relative_path in changed_files if Path(relative_path).suffix.lower() == ".py"]
		velocity_map = self.surveyor.extract_git_velocity(self.repo_path, days=30) if self._is_git_repository() else {}

		for relative_path in python_changes:
			self._remove_module_nodes(module_graph, relative_path)

		for relative_path in python_changes:
			absolute_path = self.repo_path / relative_path
			if not absolute_path.exists() or not absolute_path.is_file():
				continue
			module_node = self.surveyor.analyze_module(absolute_path, velocity_map)
			module_graph.add_node(module_node)
			for function_definition in module_node.function_definitions:
				module_graph.add_node(
					FunctionNode(
						id=f"{module_node.path}::{function_definition.name}",
						module_path=module_node.path,
						name=function_definition.name,
					)
				)

		for node_id, attributes in module_graph.graph.nodes(data=True):
			if attributes.get("node_type") == "module":
				attributes["change_velocity_30d"] = float(velocity_map.get(node_id, 0))

		self._rebuild_module_edges(module_graph)
		self._refresh_module_metadata(module_graph, velocity_map)

	def _remove_module_nodes(self, module_graph: KnowledgeGraph, relative_path: str) -> None:
		graph = module_graph.graph
		function_nodes = [node_id for node_id in graph.nodes if node_id.startswith(f"{relative_path}::")]
		if graph.has_node(relative_path):
			graph.remove_node(relative_path)
		for function_node in function_nodes:
			if graph.has_node(function_node):
				graph.remove_node(function_node)

	def _rebuild_module_edges(self, module_graph: KnowledgeGraph) -> None:
		graph = module_graph.graph
		edges_to_remove = [
			(source, target)
			for source, target, attributes in graph.edges(data=True)
			if attributes.get("edge_type") in {EdgeType.IMPORTS.value, EdgeType.CALLS.value}
		]
		graph.remove_edges_from(edges_to_remove)

		function_index = {
			(node_id.rsplit("::", 1)[0], attributes.get("name")): node_id
			for node_id, attributes in graph.nodes(data=True)
			if attributes.get("node_type") == "function" and isinstance(attributes.get("name"), str)
		}

		for node_id, attributes in list(graph.nodes(data=True)):
			if attributes.get("node_type") != "module":
				continue
			for import_path in attributes.get("import_paths", []):
				if isinstance(import_path, str) and graph.has_node(import_path):
					module_graph.add_edge(node_id, import_path, EdgeType.IMPORTS)

			for function_definition in attributes.get("function_definitions", []):
				function_name = function_definition.get("name") if isinstance(function_definition, dict) else None
				if not isinstance(function_name, str):
					continue
				caller_id = function_index.get((node_id, function_name))
				if caller_id is None:
					continue
				for called_name in function_definition.get("calls", []):
					if not isinstance(called_name, str):
						continue
					callee_id = function_index.get((node_id, called_name.split(".")[-1]))
					if callee_id is not None:
						module_graph.add_edge(caller_id, callee_id, EdgeType.CALLS)

	def _refresh_module_metadata(self, module_graph: KnowledgeGraph, velocity_map: dict[str, int]) -> None:
		self.surveyor.knowledge_graph = module_graph
		pagerank_scores = self.surveyor.calculate_pagerank()
		architectural_hubs = sorted(pagerank_scores.items(), key=lambda item: item[1], reverse=True)
		strongly_connected_components = self.surveyor.identify_strongly_connected_components()
		module_graph.graph.graph.update(
			{
				"git_velocity_days": 30,
				"git_velocity": velocity_map,
				"high_velocity_core": self.surveyor.identify_high_velocity_core(velocity_map),
				"architectural_hubs": [
					{"path": path, "pagerank": score}
					for path, score in architectural_hubs
				],
				"strongly_connected_components": strongly_connected_components,
			}
		)

	def _refresh_lineage_graph(self, lineage_graph: KnowledgeGraph, changed_files: list[str]) -> None:
		relevant_changes = [
			relative_path
			for relative_path in changed_files
			if Path(relative_path).suffix.lower() in {".py", ".sql"}
		]
		for relative_path in relevant_changes:
			self._remove_lineage_contribution(lineage_graph, relative_path)

		for relative_path in relevant_changes:
			absolute_path = self.repo_path / relative_path
			if not absolute_path.exists() or not absolute_path.is_file():
				continue
			if absolute_path.suffix.lower() == ".py":
				self.hydrologist.knowledge_graph = lineage_graph
				self.hydrologist._register_lineage_edges(absolute_path, self.hydrologist.python_data_flow_analyzer.analyze_file(absolute_path))
				self.hydrologist._register_airflow_topology(absolute_path)
			elif absolute_path.suffix.lower() == ".sql":
				self.hydrologist.knowledge_graph = lineage_graph
				self.hydrologist._register_lineage_edges(absolute_path, self.hydrologist.sql_lineage_analyzer.analyze_file(absolute_path))

		self._prune_orphan_lineage_nodes(lineage_graph)

	def _remove_lineage_contribution(self, lineage_graph: KnowledgeGraph, relative_path: str) -> None:
		graph = lineage_graph.graph
		nodes_to_remove = {
			node_id
			for node_id, attributes in graph.nodes(data=True)
			if node_id == relative_path
			or node_id.startswith(f"airflow:{relative_path}:")
			or attributes.get("source_file") == relative_path
		}

		for node_id in nodes_to_remove:
			if graph.has_node(node_id):
				graph.remove_node(node_id)

	def _prune_orphan_lineage_nodes(self, lineage_graph: KnowledgeGraph) -> None:
		graph = lineage_graph.graph
		orphan_nodes = [
			node_id
			for node_id, attributes in graph.nodes(data=True)
			if attributes.get("node_type") in {"dataset", "transformation"}
			and graph.in_degree(node_id) == 0
			and graph.out_degree(node_id) == 0
		]
		graph.remove_nodes_from(orphan_nodes)

	def _enrich_module_graph(self, module_graph: KnowledgeGraph, changed_files: list[str], *, force: bool) -> dict[str, Any]:
		graph = module_graph.graph
		changed_python_files = {relative_path for relative_path in changed_files if Path(relative_path).suffix.lower() == ".py"}
		module_payloads: list[tuple[str, ModuleNode]] = []

		for node_id, attributes in graph.nodes(data=True):
			if attributes.get("node_type") != "module":
				continue
			module_payloads.append((node_id, self._module_node_from_attributes(node_id, attributes)))

		statements_updated = False
		for node_id, module_node in module_payloads:
			needs_regeneration = force or node_id in changed_python_files or not graph.nodes[node_id].get("purpose_statement")
			if not needs_regeneration:
				continue
			purpose_result = self.semanticist.generate_purpose_statement(module_node)
			graph.nodes[node_id]["purpose_statement"] = purpose_result.purpose_statement
			graph.nodes[node_id]["documentation_drift"] = purpose_result.documentation_drift
			statements_updated = True

		should_recluster = force or statements_updated or changed_python_files or any(
			not attributes.get("domain_cluster")
			for _, attributes in graph.nodes(data=True)
			if attributes.get("node_type") == "module"
		)

		cluster_summary: dict[str, Any] = {"clusters": [], "assignments": []}
		if should_recluster:
			module_ids: list[str] = []
			purpose_statements: list[str] = []
			for node_id, attributes in graph.nodes(data=True):
				if attributes.get("node_type") != "module":
					continue
				purpose_statement = attributes.get("purpose_statement")
				if isinstance(purpose_statement, str) and purpose_statement.strip():
					module_ids.append(node_id)
					purpose_statements.append(purpose_statement)

			cluster_summary = self.semanticist.cluster_into_domains(purpose_statements)
			cluster_lookup = {
				cluster["cluster_id"]: cluster["domain_label"]
				for cluster in cluster_summary.get("clusters", [])
				if isinstance(cluster, dict)
			}
			for index, module_id in enumerate(module_ids):
				cluster_id = cluster_summary.get("assignments", [])[index]
				graph.nodes[module_id]["domain_cluster"] = cluster_lookup.get(cluster_id)
			graph.graph["domain_clusters"] = cluster_summary.get("clusters", [])

		if statements_updated or should_recluster:
			self.archivist.log_trace(
				action="semantic_enrichment",
				evidence=[{"source_file": module_id, "line_start": 1, "line_end": 1, "analysis_method": "llm-inference"} for module_id, _ in module_payloads],
				confidence=0.82,
			)

		return cluster_summary

	def _module_node_from_attributes(self, node_id: str, attributes: dict[str, Any]) -> ModuleNode:
		module_fields = set(ModuleNode.model_fields)
		payload = {key: value for key, value in attributes.items() if key in module_fields}
		payload.setdefault("id", node_id)
		payload.setdefault("path", str(attributes.get("path") or node_id))
		return ModuleNode.model_validate(payload)

	def _generate_day_one_answers(
		self,
		module_graph: KnowledgeGraph,
		lineage_graph: KnowledgeGraph,
		semantic_summary: dict[str, Any],
		used_incremental: bool,
		changed_files: list[str],
		previous_metadata: dict[str, Any],
	) -> dict[str, Any]:
		prompt_version_changed = previous_metadata.get("day_one_prompt_version") != self.DAY_ONE_PROMPT_VERSION
		needs_refresh = (
			not used_incremental
			or bool(changed_files)
			or not self.day_one_answers_path.exists()
			or bool(semantic_summary.get("clusters"))
			or prompt_version_changed
		)
		if not needs_refresh:
			return json.loads(self.day_one_answers_path.read_text(encoding="utf-8"))

		day_one_answers = self.semanticist.answer_day_one_questions(module_graph, lineage_graph)
		self.archivist.log_trace(
			action="day_one_questions",
			evidence={"source_file": ".cartography/day_one_answers.json", "line_start": 1, "line_end": 1, "analysis_method": "llm-inference"},
			confidence=0.8,
		)
		return day_one_answers

	def _write_text_file(self, destination: Path, content: str) -> None:
		destination.write_text(content, encoding="utf-8")

__all__ = ["Orchestrator", "get_changed_files"]
