from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import tempfile

from orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Analyze a repository and export cartography graphs.")
	subparsers = parser.add_subparsers(dest="command")

	analyze_parser = subparsers.add_parser("analyze", help="Run repository analysis and export cartography graphs.")
	analyze_parser.add_argument("--repo-path", required=True, help="Path or GitHub URL of the repository to analyze.")

	parser.add_argument("--repo-path", help="Path or GitHub URL of the repository to analyze.")
	return parser


def is_remote_repo_path(repo_path: str) -> bool:
	return repo_path.startswith(("http://", "https://", "github.com/"))


def normalize_repo_url(repo_path: str) -> str:
	return f"https://{repo_path}" if repo_path.startswith("github.com/") else repo_path


def remote_output_directory(repo_path: str, base_directory: str | Path = ".cartography/remotes") -> Path:
	repo_url = normalize_repo_url(repo_path).removesuffix("/")
	repo_slug = repo_url.removeprefix("https://").removeprefix("http://")
	safe_slug = repo_slug.replace("/", "__")
	return Path(base_directory) / safe_slug


@contextmanager
def resolve_repo_path(repo_path: str):
	if not is_remote_repo_path(repo_path):
		yield Path(repo_path)
		return

	repo_url = normalize_repo_url(repo_path)
	with tempfile.TemporaryDirectory(prefix="brownfield-cartographer-", dir="/tmp") as tmp_dir:
		clone_destination = Path(tmp_dir) / "repo"
		subprocess.run(
			["git", "clone", repo_url, str(clone_destination)],
			check=True,
			cwd=tmp_dir,
			capture_output=True,
			text=True,
		)
		yield clone_destination


def persist_remote_outputs(outputs: dict[str, str], repo_path: str) -> dict[str, str]:
	destination_dir = remote_output_directory(repo_path)
	destination_dir.mkdir(parents=True, exist_ok=True)

	persisted_outputs: dict[str, str] = {}
	for output_name, output_path in outputs.items():
		source_path = Path(output_path)
		destination_path = destination_dir / source_path.name
		shutil.copy2(source_path, destination_path)
		persisted_outputs[output_name] = str(destination_path.resolve())

	return persisted_outputs


def main() -> int:
	args = build_parser().parse_args()
	repo_path = args.repo_path

	if getattr(args, "command", None) == "analyze":
		repo_path = args.repo_path

	if not repo_path:
		raise SystemExit("A --repo-path value is required. Use `brownfield-cartographer analyze --repo-path <path>`.")

	with resolve_repo_path(repo_path) as resolved_repo_path:
		outputs = Orchestrator(resolved_repo_path).run()
		if is_remote_repo_path(repo_path):
			outputs = persist_remote_outputs(outputs, repo_path)

	print(f"Module graph saved to {outputs['module_graph']}")
	print(f"Lineage graph saved to {outputs['lineage_graph']}")
	if "codebase" in outputs:
		print(f"CODEBASE brief saved to {outputs['codebase']}")
	if "onboarding_brief" in outputs:
		print(f"Onboarding brief saved to {outputs['onboarding_brief']}")
	return 0

__all__ = [
	"build_parser",
	"is_remote_repo_path",
	"main",
	"normalize_repo_url",
	"persist_remote_outputs",
	"remote_output_directory",
	"resolve_repo_path",
]


if __name__ == "__main__":
	raise SystemExit(main())
