from __future__ import annotations

import ast
from datetime import datetime
import math
from pathlib import Path
import subprocess

import networkx as nx

from analyzers.tree_sitter_analyzer import analyze_module
from graph.knowledge_graph import KnowledgeGraph
from models.schemas import EdgeType, FunctionNode, ModuleNode


class SurveyorAgent:
	def __init__(self, repository_dir: str | Path) -> None:
		self.repository_dir = Path(repository_dir).resolve()
		self.knowledge_graph = KnowledgeGraph()

	def analyze_module(self, path: str | Path, velocity_map: dict[str, int] | None = None) -> ModuleNode:
		file_path = Path(path).resolve()
		relative_path = file_path.relative_to(self.repository_dir).as_posix()
		module_index = self._build_module_index()
		module_node = analyze_module(file_path)

		return module_node.model_copy(
			update={
				"id": relative_path,
				"path": relative_path,
				"import_paths": sorted(self._resolve_import_paths(module_node.imports, file_path, module_index)),
				"change_velocity_30d": float((velocity_map or {}).get(relative_path, 0)),
				"last_modified": datetime.fromtimestamp(file_path.stat().st_mtime),
			}
		)

	def extract_git_velocity(self, path: str | Path | None = None, days: int = 30) -> dict[str, int]:
		target_path = Path(path).resolve() if path is not None else self.repository_dir
		repository_root = self._git_repository_root(target_path)

		command = [
			"git",
			"log",
			"--since",
			f"{days} days ago",
			"--name-only",
			"--format=",
		]

		requested_relative_path: str | None = None
		if target_path.is_file():
			requested_relative_path = target_path.relative_to(repository_root).as_posix()
			command.insert(2, "--follow")
			command.extend(["--", requested_relative_path])

		result = subprocess.run(
			command,
			cwd=repository_root,
			capture_output=True,
			text=True,
			check=True,
		)

		file_change_counts: dict[str, int] = {}
		for line in result.stdout.splitlines():
			stripped = line.strip()
			if not stripped:
				continue
			if self._is_ignored_relative_path(stripped):
				continue
			file_change_counts[stripped] = file_change_counts.get(stripped, 0) + 1

		if requested_relative_path is not None:
			return {requested_relative_path: file_change_counts.get(requested_relative_path, 0)}

		return file_change_counts

	def identify_high_velocity_core(self, velocity_map: dict[str, int]) -> dict[str, object]:
		sorted_files = sorted(velocity_map.items(), key=lambda item: item[1], reverse=True)
		total_changes = sum(change_count for _, change_count in sorted_files)
		if not sorted_files or total_changes == 0:
			return {"files": [], "change_share": 0.0, "file_share": 0.0, "days": 30}

		core_files: list[tuple[str, int]] = []
		cumulative_changes = 0
		for file_path, change_count in sorted_files:
			core_files.append((file_path, change_count))
			cumulative_changes += change_count
			if cumulative_changes / total_changes >= 0.8:
				break

		change_share = sum(change_count for _, change_count in core_files) / total_changes

		return {
			"files": [{"path": path, "change_count": count} for path, count in core_files],
			"change_share": change_share,
			"file_share": len(core_files) / len(sorted_files),
			"days": 30,
		}

	def build_import_graph(self) -> KnowledgeGraph:
		self.knowledge_graph = KnowledgeGraph()
		git_velocity = self.extract_git_velocity(self.repository_dir, days=30)
		module_index = self._build_module_index()
		module_nodes: dict[str, ModuleNode] = {}
		function_index: dict[tuple[str, str], str] = {}

		for file_path in self._iter_repository_python_files():
			module_node = self.analyze_module(file_path, git_velocity)
			module_nodes[module_node.path] = module_node
			self.knowledge_graph.add_node(module_node)

			for function_definition in module_node.function_definitions:
				function_id = f"{module_node.path}::{function_definition.name}"
				function_index[(module_node.path, function_definition.name)] = function_id
				self.knowledge_graph.add_node(
					FunctionNode(
						id=function_id,
						module_path=module_node.path,
						name=function_definition.name,
					)
				)

		for module_node in module_nodes.values():
			for import_path in module_node.import_paths:
				self.knowledge_graph.add_edge(module_node.path, import_path, EdgeType.IMPORTS)

			for function_definition in module_node.function_definitions:
				caller_id = function_index.get((module_node.path, function_definition.name))
				if caller_id is None:
					continue

				for called_name in function_definition.calls:
					callee_id = function_index.get((module_node.path, called_name.split(".")[-1]))
					if callee_id is not None:
						self.knowledge_graph.add_edge(caller_id, callee_id, EdgeType.CALLS)

		pagerank_scores = self.calculate_pagerank()
		architectural_hubs = sorted(pagerank_scores.items(), key=lambda item: item[1], reverse=True)
		strongly_connected_components = self.identify_strongly_connected_components()

		self.knowledge_graph.graph.graph.update(
			{
				"git_velocity_days": 30,
				"git_velocity": git_velocity,
				"high_velocity_core": self.identify_high_velocity_core(git_velocity),
				"architectural_hubs": [
					{"path": path, "pagerank": score}
					for path, score in architectural_hubs
				],
				"strongly_connected_components": strongly_connected_components,
			}
		)

		return self.knowledge_graph

	def calculate_pagerank(self) -> dict[str, float]:
		module_graph = self._module_import_subgraph()
		if module_graph.number_of_nodes() == 0:
			return {}
		try:
			return nx.pagerank(module_graph)
		except ModuleNotFoundError:
			from networkx.algorithms.link_analysis.pagerank_alg import _pagerank_python

			return _pagerank_python(module_graph)

	def identify_strongly_connected_components(self) -> list[list[str]]:
		module_graph = self._module_import_subgraph()
		components = [sorted(component) for component in nx.strongly_connected_components(module_graph) if len(component) > 1]
		return sorted(components, key=len, reverse=True)

	def _module_import_subgraph(self) -> nx.DiGraph:
		module_graph = nx.DiGraph()
		for node_id, attributes in self.knowledge_graph.graph.nodes(data=True):
			if attributes.get("node_type") == "module":
				module_graph.add_node(node_id, **attributes)

		for source, target, attributes in self.knowledge_graph.graph.edges(data=True):
			if attributes.get("edge_type") == EdgeType.IMPORTS.value:
				module_graph.add_edge(source, target, **attributes)

		return module_graph

	def _iter_repository_python_files(self):
		for file_path in self.repository_dir.rglob("*.py"):
			relative_parts = file_path.relative_to(self.repository_dir).parts
			if any(part in {".cartography", ".git", ".venv", "__pycache__", "build", "dist", "target", "tmp"} for part in relative_parts):
				continue
			yield file_path

	def _is_ignored_relative_path(self, relative_path: str) -> bool:
		return any(part in {".cartography", ".git", ".venv", "__pycache__", "build", "dist", "target", "tmp"} for part in Path(relative_path).parts)

	def _git_repository_root(self, path: Path) -> Path:
		result = subprocess.run(
			["git", "rev-parse", "--show-toplevel"],
			cwd=path if path.is_dir() else path.parent,
			capture_output=True,
			text=True,
			check=True,
		)
		return Path(result.stdout.strip()).resolve()

	def _build_module_index(self) -> dict[str, str]:
		module_index: dict[str, str] = {}

		for file_path in self._iter_repository_python_files():
			relative_path = file_path.relative_to(self.repository_dir)
			relative_posix = relative_path.as_posix()

			for module_name in self._module_names_for_path(relative_path):
				module_index[module_name] = relative_posix

		return module_index

	def _module_names_for_path(self, relative_path: Path) -> set[str]:
		parts = list(relative_path.with_suffix("").parts)
		candidates: set[str] = set()

		variants = [parts]
		if parts and parts[0] == "src":
			variants.append(parts[1:])

		for variant in variants:
			if not variant:
				continue
			if variant[-1] == "__init__":
				package_parts = variant[:-1]
				if package_parts:
					candidates.add(".".join(package_parts))
			else:
				candidates.add(".".join(variant))

		return {candidate for candidate in candidates if candidate}

	def _resolve_import_paths(self, import_statements: list[str], source_file: Path, module_index: dict[str, str]) -> set[str]:
		resolved_paths: set[str] = set()
		for import_statement in import_statements:
			resolved_paths.update(self._resolve_import_statement(import_statement, source_file, module_index))
		return resolved_paths

	def _resolve_import_statement(
		self,
		import_statement: str,
		source_file: Path,
		module_index: dict[str, str],
	) -> set[str]:
		resolved_paths: set[str] = set()
		statement = ast.parse(import_statement).body[0]
		source_module = self._preferred_module_name(source_file.relative_to(self.repository_dir))

		if isinstance(statement, ast.Import):
			for alias in statement.names:
				resolved_path = self._resolve_module_reference(alias.name, module_index)
				if resolved_path is not None:
					resolved_paths.add(resolved_path)

		if isinstance(statement, ast.ImportFrom):
			base_module = self._resolve_from_base_module(source_module, statement.module, statement.level)
			if base_module is None:
				return resolved_paths

			candidate_modules = [base_module]
			for alias in statement.names:
				if alias.name != "*":
					candidate_modules.insert(0, f"{base_module}.{alias.name}")

			for candidate in candidate_modules:
				resolved_path = self._resolve_module_reference(candidate, module_index)
				if resolved_path is not None:
					resolved_paths.add(resolved_path)

		return resolved_paths

	def _preferred_module_name(self, relative_path: Path) -> str | None:
		candidates = sorted(self._module_names_for_path(relative_path), key=lambda value: (value.startswith("src."), len(value)))
		return candidates[0] if candidates else None

	def _resolve_from_base_module(self, source_module: str | None, module: str | None, level: int) -> str | None:
		if level == 0:
			return module

		if source_module is None:
			return module

		source_parts = source_module.split(".")
		package_parts = source_parts[:-1]

		if level > len(package_parts) + 1:
			return module

		base_parts = package_parts[: len(package_parts) - (level - 1)]
		if module:
			base_parts.extend(module.split("."))

		return ".".join(base_parts) if base_parts else module

	def _resolve_module_reference(self, module_name: str, module_index: dict[str, str]) -> str | None:
		candidate = module_name
		while candidate:
			resolved_path = module_index.get(candidate)
			if resolved_path is not None:
				return resolved_path
			candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
		return None


__all__ = ["SurveyorAgent"]
