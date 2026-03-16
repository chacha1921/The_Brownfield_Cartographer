from __future__ import annotations

import argparse
from pathlib import Path

from brownfield_cartographer.dashboard import generate_dashboard, resolve_artifact_directory
from agents.navigator import NavigatorAgent
from graph.knowledge_graph import KnowledgeGraph
from orchestrator import Orchestrator
from utils import TerminalLogger, is_remote_repo_path, merge_cartography_graphs, persist_remote_outputs, resolve_repo_path


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="Analyze brownfield repositories into import, lineage, semantic, and onboarding artifacts.",
	)
	subparsers = parser.add_subparsers(dest="command")

	analyze_parser = subparsers.add_parser("analyze", help="Run the full cartography pipeline and write .cartography artifacts.")
	analyze_parser.add_argument("--repo-path", required=True, help="Path or GitHub URL of the repository to analyze.")
	analyze_parser.add_argument("--force-full", action="store_true", help="Ignore cached graphs and re-run the full pipeline.")
	analyze_parser.add_argument("--sql-dialect", default="postgres", help="SQL dialect for SQLGlot parsing, e.g. postgres, spark, bigquery.")

	query_parser = subparsers.add_parser("query", help="Launch Navigator over existing .cartography artifacts.")
	query_parser.add_argument("--repo-path", required=True, help="Repository path, remote URL, or artifact directory containing generated Cartographer outputs.")
	query_parser.add_argument("--question", help="Optional one-shot question. If omitted, interactive mode starts.")

	dashboard_parser = subparsers.add_parser("dashboard", help="Generate an interactive HTML dashboard from existing .cartography artifacts.")
	dashboard_parser.add_argument("--repo-path", required=True, help="Repository path, remote URL, or artifact directory containing generated Cartographer outputs.")
	dashboard_parser.add_argument("--output", help="Optional output path for the generated HTML dashboard.")

	parser.add_argument("--repo-path", help="Path or GitHub URL of the repository to analyze.")
	return parser

def main() -> int:
	args = build_parser().parse_args()
	if getattr(args, "command", None) == "query":
		return _run_query_command(args.repo_path, getattr(args, "question", None))
	if getattr(args, "command", None) == "dashboard":
		return _run_dashboard_command(args.repo_path, getattr(args, "output", None))

	repo_path = args.repo_path
	logger = TerminalLogger()
	force_full = False
	sql_dialect = "postgres"

	if getattr(args, "command", None) == "analyze":
		repo_path = args.repo_path
		force_full = bool(getattr(args, "force_full", False))
		sql_dialect = str(getattr(args, "sql_dialect", "postgres"))

	if not repo_path:
		raise SystemExit("A --repo-path value is required. Use `brownfield-cartographer analyze --repo-path <path>`.")

	logger.section("CLI input")
	logger.step("Resolving repository target", repo_path)
	logger.detail("Remote repository cloning will be logged when a URL is provided")
	env_path = Path.cwd() / ".env"

	with resolve_repo_path(repo_path) as resolved_repo_path:
		logger.success(f"Repository ready: {resolved_repo_path}")
		outputs = Orchestrator(resolved_repo_path, env_path=env_path, force_full=force_full, sql_dialect=sql_dialect).run()
		if is_remote_repo_path(repo_path):
			logger.section("Persisting remote artifacts")
			logger.step("Copying outputs from temporary clone", "Saving generated artifacts into .cartography/remotes")
			outputs = persist_remote_outputs(outputs, repo_path)

	logger.section("CLI outputs")
	logger.artifact("module graph", outputs["module_graph"])
	logger.artifact("lineage graph", outputs["lineage_graph"])
	if "codebase" in outputs:
		logger.artifact("codebase brief", outputs["codebase"])
	if "onboarding_brief" in outputs:
		logger.artifact("onboarding brief", outputs["onboarding_brief"])
	if "trace" in outputs:
		logger.artifact("trace log", outputs["trace"])
	return 0


def _run_query_command(repo_path: str, question: str | None) -> int:
	artifact_dir = resolve_artifact_directory(repo_path)
	repository_root = artifact_dir.parent if artifact_dir.name == ".cartography" else artifact_dir
	module_graph_path = artifact_dir / "module_graph.json"
	lineage_graph_path = artifact_dir / "lineage_graph.json"
	if not module_graph_path.exists() or not lineage_graph_path.exists():
		raise SystemExit("Navigator requires Cartographer artifacts containing module_graph.json and lineage_graph.json.")

	module_graph = KnowledgeGraph.load_from_json(module_graph_path)
	lineage_graph = KnowledgeGraph.load_from_json(lineage_graph_path)
	merged_graph = merge_cartography_graphs(module_graph, lineage_graph)
	navigator = NavigatorAgent(repository_root, merged_graph)

	if question:
		print(navigator.answer(question))
		return 0

	print("Navigator interactive mode. Type 'exit' or 'quit' to stop.")
	while True:
		try:
			prompt = input("query> ").strip()
		except (EOFError, KeyboardInterrupt):
			print()
			return 0
		if not prompt:
			continue
		if prompt.lower() in {"exit", "quit"}:
			return 0
		print(navigator.answer(prompt))
		print()


def _run_dashboard_command(repo_path: str, output_path: str | None) -> int:
	dashboard_path = generate_dashboard(repo_path, output_path=output_path)
	print(f"Dashboard generated: {dashboard_path}")
	return 0

__all__ = [
	"build_parser",
	"is_remote_repo_path",
	"main",
	"persist_remote_outputs",
	"resolve_repo_path",
]


if __name__ == "__main__":
	raise SystemExit(main())
