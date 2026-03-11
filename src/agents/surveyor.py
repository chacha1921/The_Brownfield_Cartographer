from __future__ import annotations

import ast
import subprocess
from datetime import datetime
from pathlib import Path

import networkx as nx

from analyzers.tree_sitter_analyzer import parse_python_imports_and_functions
from graph.knowledge_graph import KnowledgeGraph
from models.schemas import EdgeType, ModuleNode


class SurveyorAgent:
	def __init__(self, repository_dir: str | Path) -> None:
		self.repository_dir = Path(repository_dir).resolve()
		self.knowledge_graph = KnowledgeGraph()

	def extract_git_velocity(self) -> dict[str, int]:
		file_change_counts: dict[str, int] = {}

		for file_path in self._iter_repository_python_files():
			relative_path = file_path.relative_to(self.repository_dir).as_posix()
			command = [
				"git",
				"log",
				"--follow",
				"--since=30 days ago",
				"--name-only",
				"--format=",
				"--",
				relative_path,
			]
			result = subprocess.run(
				command,
				cwd=self.repository_dir,
				capture_output=True,
				text=True,
				check=True,
			)

			changed_paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
			file_change_counts[relative_path] = len(changed_paths)

		return file_change_counts

	def build_import_graph(self) -> KnowledgeGraph:
		self.knowledge_graph = KnowledgeGraph()
		git_velocity = self.extract_git_velocity()
		module_index = self._build_module_index()

		for file_path in self._iter_repository_python_files():
			relative_path = file_path.relative_to(self.repository_dir).as_posix()
			module_node = ModuleNode(
				id=relative_path,
				path=relative_path,
				language="python",
				change_velocity_30d=float(git_velocity.get(relative_path, 0)),
				last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
			)
			self.knowledge_graph.add_node(module_node)

		for file_path in self._iter_repository_python_files():
			relative_path = file_path.relative_to(self.repository_dir).as_posix()
			import_data = parse_python_imports_and_functions(file_path)

			for import_statement in import_data["imports"]:
				for imported_file in self._resolve_import_statement(import_statement, file_path, module_index):
					self.knowledge_graph.add_edge(relative_path, imported_file, EdgeType.IMPORTS)

		return self.knowledge_graph

	def calculate_pagerank(self) -> dict[str, float]:
		if self.knowledge_graph.graph.number_of_nodes() == 0:
			return {}
		try:
			return nx.pagerank(self.knowledge_graph.graph)
		except ModuleNotFoundError:
			from networkx.algorithms.link_analysis.pagerank_alg import _pagerank_python

			return _pagerank_python(self.knowledge_graph.graph)

	def _iter_repository_python_files(self):
		for file_path in self.repository_dir.rglob("*.py"):
			if any(part in {".git", ".venv", "__pycache__", "tmp"} for part in file_path.parts):
				continue
			yield file_path

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
