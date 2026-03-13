from pathlib import Path

from agents.hydrologist import HydrologistAgent
from agents.surveyor import SurveyorAgent


class Orchestrator:
	def __init__(self, repo_path: str | Path) -> None:
		self.repo_path = Path(repo_path).resolve()
		self.output_dir = self.repo_path / ".cartography"
		self.surveyor = SurveyorAgent(self.repo_path)
		self.hydrologist = HydrologistAgent(self.repo_path)

	def run(self) -> dict[str, str]:
		self.output_dir.mkdir(parents=True, exist_ok=True)

		module_graph = self.surveyor.build_import_graph()
		lineage_graph = self.hydrologist.build_lineage_graph()

		module_graph_path = self.output_dir / "module_graph.json"
		lineage_graph_path = self.output_dir / "lineage_graph.json"

		module_graph.save_to_json(module_graph_path)
		lineage_graph.save_to_json(lineage_graph_path)

		return {
			"module_graph": str(module_graph_path),
			"lineage_graph": str(lineage_graph_path),
		}

__all__ = ["Orchestrator"]
