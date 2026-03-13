from __future__ import annotations

from dataclasses import dataclass, field
import shutil
import time


@dataclass(slots=True)
class TerminalLogger:
	width: int = 100
	_run_started_at: float | None = field(default=None, init=False, repr=False)

	RESET = "\033[0m"
	BOLD = "\033[1m"
	DIM = "\033[2m"
	CYAN = "\033[96m"
	BLUE = "\033[94m"
	GREEN = "\033[92m"
	YELLOW = "\033[93m"
	MAGENTA = "\033[95m"
	RED = "\033[91m"
	WHITE = "\033[97m"

	def __post_init__(self) -> None:
		self.width = max(72, shutil.get_terminal_size((self.width, 24)).columns)

	def banner(self, title: str, subtitle: str | None = None, *, color: str | None = None) -> None:
		accent = color or self.CYAN
		line = "═" * self.width
		print()
		print(f"{accent}{self.BOLD}{line}{self.RESET}")
		print(f"{accent}{self.BOLD}{self._center(title.upper())}{self.RESET}")
		if subtitle:
			print(f"{accent}{self.DIM}{self._center(subtitle)}{self.RESET}")
		print(f"{accent}{self.BOLD}{line}{self.RESET}")

	def start_run(self, title: str, subtitle: str | None = None) -> None:
		self._run_started_at = time.perf_counter()
		self.banner(title, subtitle, color=self.BLUE)

	def finish_run(self, message: str) -> None:
		elapsed = ""
		if self._run_started_at is not None:
			elapsed_seconds = time.perf_counter() - self._run_started_at
			elapsed = f" in {elapsed_seconds:.2f}s"
		self.banner("analysis complete", f"{message}{elapsed}", color=self.GREEN)

	def section(self, title: str, *, color: str | None = None) -> None:
		accent = color or self.MAGENTA
		label = f" {title.upper()} "
		filler = "─" * max(2, (self.width - len(label)) // 2)
		print()
		print(f"{accent}{self.BOLD}{filler}{label}{filler}{self.RESET}")

	def step(self, title: str, detail: str | None = None) -> None:
		print(f"{self.YELLOW}{self.BOLD}  ▶ {title}{self.RESET}")
		if detail:
			self.detail(detail)

	def detail(self, message: str) -> None:
		print(f"{self.DIM}      • {message}{self.RESET}")

	def success(self, message: str) -> None:
		print(f"{self.GREEN}{self.BOLD}  ✓ {message}{self.RESET}")

	def warning(self, message: str) -> None:
		print(f"{self.MAGENTA}{self.BOLD}  ! {message}{self.RESET}")

	def error(self, message: str) -> None:
		print(f"{self.RED}{self.BOLD}  ✗ {message}{self.RESET}")

	def artifact(self, title: str, path: str) -> None:
		print(f"{self.WHITE}{self.BOLD}    {title:<18}{self.RESET} {self.DIM}{path}{self.RESET}")

	def _center(self, message: str) -> str:
		return message.center(self.width)


__all__ = ["TerminalLogger"]