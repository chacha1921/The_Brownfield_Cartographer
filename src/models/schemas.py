from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EdgeType(str, Enum):
	IMPORTS = "IMPORTS"
	PRODUCES = "PRODUCES"
	CONSUMES = "CONSUMES"
	CALLS = "CALLS"
	CONFIGURES = "CONFIGURES"


class Node(BaseModel):
	model_config = ConfigDict(extra="forbid")

	id: str = Field(..., description="Unique identifier for the graph node.")
	node_type: str = Field(..., description="Concrete node type discriminator.")


class ModuleNode(Node):
	node_type: Literal["module"] = "module"
	path: str
	language: str
	purpose_statement: str | None = None
	domain_cluster: str | None = None
	complexity_score: float | None = Field(default=None, ge=0)
	change_velocity_30d: float | None = Field(default=None, ge=0)
	is_dead_code_candidate: bool = False
	last_modified: datetime | None = None


class DatasetNode(Node):
	node_type: Literal["dataset"] = "dataset"
	name: str
	storage_type: str
	schema_snapshot: dict[str, object] = Field(default_factory=dict)
	freshness_sla: str | None = None
	owner: str | None = None
	is_source_of_truth: bool = False


class FunctionNode(Node):
	node_type: Literal["function"] = "function"


class TransformationNode(Node):
	node_type: Literal["transformation"] = "transformation"


__all__ = [
	"DatasetNode",
	"EdgeType",
	"FunctionNode",
	"ModuleNode",
	"Node",
	"TransformationNode",
]
