from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from typing import Iterator
from urllib import error, parse, request


REMOTE_CACHE_ROOT = Path(tempfile.gettempdir()) / "brownfield-cartographer-cache"
REMOTE_CACHE_METADATA = "cache_metadata.json"
REMOTE_CACHE_REFRESH_INTERVAL = timedelta(hours=12)


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
	cache_destination = _remote_cache_directory(repo_url)
	cache_destination.parent.mkdir(parents=True, exist_ok=True)
	if not _is_cached_repository_ready(cache_destination):
		_populate_remote_cache(repo_url, cache_destination)
	else:
		if _should_refresh_remote_cache(cache_destination):
			_try_refresh_remote_cache(repo_url, cache_destination)
		yield cache_destination
		return

	yield cache_destination


def _remote_cache_directory(repo_url: str) -> Path:
	repo_slug = normalize_repo_url(repo_url).removesuffix("/").removeprefix("https://").removeprefix("http://")
	safe_slug = repo_slug.replace("/", "__")
	return REMOTE_CACHE_ROOT / safe_slug / "repo"


def _cache_metadata_path(cache_destination: Path) -> Path:
	return cache_destination.parent / REMOTE_CACHE_METADATA


def _is_cached_repository_ready(cache_destination: Path) -> bool:
	return cache_destination.exists() and any(cache_destination.iterdir())


def _populate_remote_cache(repo_url: str, cache_destination: Path) -> None:
	working_dir = cache_destination.parent
	if working_dir.exists():
		shutil.rmtree(working_dir, ignore_errors=True)
	working_dir.mkdir(parents=True, exist_ok=True)
	_clone_remote_repository(repo_url, cache_destination, cwd=working_dir)
	_write_cache_metadata(cache_destination, repo_url)


def _try_refresh_remote_cache(repo_url: str, cache_destination: Path) -> None:
	if not (cache_destination / ".git").exists():
		return
	try:
		subprocess.run(
			["git", "-c", "http.version=HTTP/1.1", "fetch", "--depth", "1", "origin"],
			check=True,
			cwd=cache_destination,
			capture_output=True,
			text=True,
		)
		default_ref = _default_remote_ref(cache_destination)
		subprocess.run(
			["git", "reset", "--hard", default_ref],
			check=True,
			cwd=cache_destination,
			capture_output=True,
			text=True,
		)
		_write_cache_metadata(cache_destination, repo_url)
	except subprocess.CalledProcessError:
		return


def _default_remote_ref(cache_destination: Path) -> str:
	for candidate in ("origin/HEAD", "origin/main", "origin/master"):
		result = subprocess.run(
			["git", "rev-parse", "--verify", candidate],
			cwd=cache_destination,
			capture_output=True,
			text=True,
		)
		if result.returncode == 0:
			return candidate
	return "FETCH_HEAD"


def _write_cache_metadata(cache_destination: Path, repo_url: str) -> None:
	metadata_path = _cache_metadata_path(cache_destination)
	payload = {
		"repo_url": repo_url,
		"cache_path": str(cache_destination),
		"source": "git" if (cache_destination / ".git").exists() else "archive",
		"last_refreshed_at": datetime.now(timezone.utc).isoformat(),
	}
	metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _should_refresh_remote_cache(cache_destination: Path) -> bool:
	metadata_path = _cache_metadata_path(cache_destination)
	if not metadata_path.exists():
		return True

	try:
		metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
	except json.JSONDecodeError:
		return True

	refreshed_at = metadata.get("last_refreshed_at")
	if not isinstance(refreshed_at, str) or not refreshed_at.strip():
		return True

	try:
		last_refreshed = datetime.fromisoformat(refreshed_at)
	except ValueError:
		return True

	if last_refreshed.tzinfo is None:
		last_refreshed = last_refreshed.replace(tzinfo=timezone.utc)

	return datetime.now(timezone.utc) - last_refreshed >= REMOTE_CACHE_REFRESH_INTERVAL


def _clone_remote_repository(repo_url: str, clone_destination: Path, *, cwd: Path) -> None:
	attempts = [
		["git", "clone", repo_url, str(clone_destination)],
		[
			"git",
			"-c",
			"http.version=HTTP/1.1",
			"clone",
			"--depth",
			"1",
			"--single-branch",
			"--no-tags",
			repo_url,
			str(clone_destination),
		],
	]
	last_error: subprocess.CalledProcessError | None = None

	for index, command in enumerate(attempts):
		if clone_destination.exists():
			shutil.rmtree(clone_destination, ignore_errors=True)
		try:
			subprocess.run(
				command,
				check=True,
				cwd=cwd,
				capture_output=True,
				text=True,
			)
			return
		except subprocess.CalledProcessError as exc:
			last_error = exc
			if index == len(attempts) - 1:
				break

	if last_error is None:
		raise RuntimeError(f"Failed to clone remote repository: {repo_url}")

	stderr = (last_error.stderr or "").strip()
	stdout = (last_error.stdout or "").strip()
	if _is_github_repo_url(repo_url):
		try:
			_download_github_archive(repo_url, clone_destination, cwd=cwd)
			return
		except RuntimeError as archive_error:
			details = stderr or stdout or f"git exited with status {last_error.returncode}"
			raise RuntimeError(
				f"Failed to clone remote repository '{repo_url}'. {details}. Archive fallback also failed: {archive_error}"
			) from last_error

	details = stderr or stdout or f"git exited with status {last_error.returncode}"
	raise RuntimeError(f"Failed to clone remote repository '{repo_url}'. {details}") from last_error


def _is_github_repo_url(repo_url: str) -> bool:
	parsed = parse.urlparse(repo_url)
	return parsed.netloc.lower() == "github.com"


def _download_github_archive(repo_url: str, clone_destination: Path, *, cwd: Path) -> None:
	owner, repository = _parse_github_owner_repo(repo_url)
	archive_candidates = [
		f"https://codeload.github.com/{owner}/{repository}/tar.gz/refs/heads/main",
		f"https://codeload.github.com/{owner}/{repository}/tar.gz/refs/heads/master",
	]
	archive_path = cwd / "repo.tar.gz"
	last_error: Exception | None = None

	for archive_url in archive_candidates:
		try:
			with request.urlopen(archive_url) as response, archive_path.open("wb") as destination:
				shutil.copyfileobj(response, destination)
			extract_dir = cwd / "archive-extract"
			if extract_dir.exists():
				shutil.rmtree(extract_dir, ignore_errors=True)
			extract_dir.mkdir(parents=True, exist_ok=True)
			with tarfile.open(archive_path, mode="r:gz") as archive:
				archive.extractall(extract_dir)
			top_level_entries = [entry for entry in extract_dir.iterdir() if entry.is_dir()]
			if len(top_level_entries) != 1:
				raise RuntimeError("GitHub archive extraction did not yield a single repository root.")
			shutil.move(str(top_level_entries[0]), str(clone_destination))
			return
		except (error.URLError, error.HTTPError, tarfile.TarError, OSError, RuntimeError) as exc:
			last_error = exc
			if archive_path.exists():
				archive_path.unlink(missing_ok=True)
			continue

	if archive_path.exists():
		archive_path.unlink(missing_ok=True)
	raise RuntimeError(str(last_error) if last_error is not None else "Unknown GitHub archive download failure.")


def _parse_github_owner_repo(repo_url: str) -> tuple[str, str]:
	parsed = parse.urlparse(repo_url)
	parts = [part for part in parsed.path.split("/") if part]
	if len(parts) < 2:
		raise RuntimeError(f"Unsupported GitHub repository URL: {repo_url}")
	owner = parts[0]
	repository = parts[1].removesuffix(".git")
	return owner, repository


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