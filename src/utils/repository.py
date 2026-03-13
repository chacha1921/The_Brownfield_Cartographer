from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterator


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
def resolve_repo_path(repo_path: str) -> Iterator[Path]:
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


__all__ = [
	"is_remote_repo_path",
	"normalize_repo_url",
	"persist_remote_outputs",
	"remote_output_directory",
	"resolve_repo_path",
]