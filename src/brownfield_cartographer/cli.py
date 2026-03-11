from __future__ import annotations

import argparse

from .__init__ import __version__
from .orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze a repository and export cartography graphs.")
    parser.add_argument("--repo-path", required=True, help="Path to the repository to analyze.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    outputs = Orchestrator(args.repo_path).run()
    print(f"Module graph saved to {outputs['module_graph']}")
    print(f"Lineage graph saved to {outputs['lineage_graph']}")
    return 0


__all__ = ["build_parser", "main"]
