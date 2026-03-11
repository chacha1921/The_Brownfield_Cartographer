from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile

from .__init__ import __version__
from .orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze a repository and export cartography graphs.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    analyze_parser = subparsers.add_parser("analyze", help="Run repository analysis and export cartography graphs.")
    analyze_parser.add_argument("--repo-path", required=True, help="Path or GitHub URL of the repository to analyze.")

    parser.add_argument("--repo-path", help="Path or GitHub URL of the repository to analyze.")
    return parser


def is_remote_repo_path(repo_path: str) -> bool:
    return repo_path.startswith(("http://", "https://", "github.com/"))


def normalize_repo_url(repo_path: str) -> str:
    return f"https://{repo_path}" if repo_path.startswith("github.com/") else repo_path


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


def main() -> int:
    args = build_parser().parse_args()

    repo_path = args.repo_path
    if getattr(args, "command", None) == "analyze":
        repo_path = args.repo_path

    if not repo_path:
        raise SystemExit("A --repo-path value is required. Use `brownfield-cartographer analyze --repo-path <path>`.")

    with resolve_repo_path(repo_path) as resolved_repo_path:
        outputs = Orchestrator(resolved_repo_path).run()
    print(f"Module graph saved to {outputs['module_graph']}")
    print(f"Lineage graph saved to {outputs['lineage_graph']}")
    return 0


__all__ = ["build_parser", "is_remote_repo_path", "main", "normalize_repo_url", "resolve_repo_path"]
