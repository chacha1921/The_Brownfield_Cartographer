from __future__ import annotations

from pathlib import Path
import subprocess


IGNORED_PATH_PARTS = {".cartography", ".git", ".venv", "__pycache__", "build", "dist", "target", "tmp"}


def is_git_repository(repo_path: str | Path) -> bool:
	repository_root = Path(repo_path).resolve()
	result = subprocess.run(
		["git", "rev-parse", "--is-inside-work-tree"],
		cwd=repository_root,
		capture_output=True,
		text=True,
	)
	return result.returncode == 0 and result.stdout.strip() == "true"


def current_commit_hash(repo_path: str | Path) -> str | None:
	repository_root = Path(repo_path).resolve()
	if not is_git_repository(repository_root):
		return None

	result = subprocess.run(
		["git", "rev-parse", "HEAD"],
		cwd=repository_root,
		capture_output=True,
		text=True,
	)
	return result.stdout.strip() if result.returncode == 0 else None


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

	changed_files: list[str] = []
	for raw_line in result.stdout.splitlines():
		relative_path = raw_line.strip()
		if not relative_path:
			continue
		if any(part in IGNORED_PATH_PARTS for part in Path(relative_path).parts):
			continue
		changed_files.append(relative_path)

	return changed_files


__all__ = ["IGNORED_PATH_PARTS", "current_commit_hash", "get_changed_files", "is_git_repository"]