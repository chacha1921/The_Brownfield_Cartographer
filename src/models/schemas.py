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


class ClassDefinition(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: str
	bases: list[str] = Field(default_factory=list)


class FunctionDefinition(BaseModel):
	model_config = ConfigDict(extra="forbid")

	name: str
	original_name: str
	decorators: list[str] = Field(default_factory=list)
	calls: list[str] = Field(default_factory=list)


class ModuleNode(Node):
	node_type: Literal["module"] = "module"
	path: str
	language: str
	imports: list[str] = Field(default_factory=list)
	import_paths: list[str] = Field(default_factory=list)
	public_functions: list[str] = Field(default_factory=list)
	function_definitions: list[FunctionDefinition] = Field(default_factory=list)
	class_definitions: list[ClassDefinition] = Field(default_factory=list)
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
	module_path: str
	name: str


class TransformationNode(Node):
	node_type: Literal["transformation"] = "transformation"


__all__ = [
	"ClassDefinition",
	"DatasetNode",
	"EdgeType",
	"FunctionDefinition",
	"FunctionNode",
	"ModuleNode",
	"Node",
	"TransformationNode",
]
