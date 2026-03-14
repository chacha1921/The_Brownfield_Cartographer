from __future__ import annotations

import argparse
from pathlib import Path

from orchestrator import Orchestrator
from utils import TerminalLogger, is_remote_repo_path, persist_remote_outputs, resolve_repo_path


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Analyze a repository and export cartography graphs.")
	subparsers = parser.add_subparsers(dest="command")

	analyze_parser = subparsers.add_parser("analyze", help="Run repository analysis and export cartography graphs.")
	analyze_parser.add_argument("--repo-path", required=True, help="Path or GitHub URL of the repository to analyze.")

	parser.add_argument("--repo-path", help="Path or GitHub URL of the repository to analyze.")
	return parser

def main() -> int:
	args = build_parser().parse_args()
	repo_path = args.repo_path
	logger = TerminalLogger()

	if getattr(args, "command", None) == "analyze":
		repo_path = args.repo_path

	if not repo_path:
		raise SystemExit("A --repo-path value is required. Use `brownfield-cartographer analyze --repo-path <path>`.")

	logger.section("CLI input")
	logger.step("Resolving repository target", repo_path)
	logger.detail("Remote repository cloning will be logged when a URL is provided")
	env_path = Path.cwd() / ".env"

	with resolve_repo_path(repo_path) as resolved_repo_path:
		logger.success(f"Repository ready: {resolved_repo_path}")
		outputs = Orchestrator(resolved_repo_path, env_path=env_path).run()
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
