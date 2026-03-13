from __future__ import annotations

import importlib
from pathlib import Path

from tree_sitter import Language, Node, Parser
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_sql
import tree_sitter_yaml

from models.schemas import ClassDefinition, FunctionDefinition, ModuleNode

tree_sitter_typescript = importlib.import_module("tree_sitter_typescript") if importlib.util.find_spec("tree_sitter_typescript") else None


class LanguageRouter:
	_LANGUAGE_LOADERS = {
		".py": tree_sitter_python.language,
		".sql": tree_sitter_sql.language,
		".yaml": tree_sitter_yaml.language,
		".yml": tree_sitter_yaml.language,
		".js": tree_sitter_javascript.language,
		".jsx": tree_sitter_javascript.language,
		".mjs": tree_sitter_javascript.language,
		".cjs": tree_sitter_javascript.language,
	}
	if tree_sitter_typescript is not None:
		_LANGUAGE_LOADERS[".ts"] = tree_sitter_typescript.language_typescript
		_LANGUAGE_LOADERS[".tsx"] = tree_sitter_typescript.language_tsx

	def get_language(self, file_path: str | Path) -> Language:
		suffix = Path(file_path).suffix.lower()
		loader = self._LANGUAGE_LOADERS.get(suffix)
		if loader is None:
			raise ValueError(f"Unsupported file extension: {suffix or '<none>'}")
		return Language(loader())

	def get_parser(self, file_path: str | Path) -> Parser:
		return Parser(self.get_language(file_path))


def analyze_module(file_path: str | Path) -> ModuleNode:
	source_path = Path(file_path)
	source_bytes = source_path.read_bytes()

	router = LanguageRouter()
	parser = router.get_parser(source_path)
	tree = parser.parse(source_bytes)

	imports = _extract_import_statements(tree.root_node, source_bytes)
	function_definitions = _extract_function_definitions(tree.root_node, source_bytes)
	class_definitions = _extract_class_definitions(tree.root_node, source_bytes)

	return ModuleNode(
		id=source_path.as_posix(),
		path=source_path.as_posix(),
		language=_language_name_for_path(source_path),
		imports=imports,
		import_paths=_extract_relative_import_paths(imports),
		public_functions=[function.name for function in function_definitions],
		function_definitions=function_definitions,
		class_definitions=class_definitions,
	)


def parse_python_imports_and_functions(file_path: str | Path) -> dict[str, list[str]]:
	module = analyze_module(file_path)
	return {
		"imports": module.imports,
		"public_functions": module.public_functions,
	}


def _extract_import_statements(root_node: Node, source_bytes: bytes) -> list[str]:
	imports: list[str] = []

	for node in _walk_tree(root_node):
		if node.type in {"import_statement", "import_from_statement"}:
			imports.append(source_bytes[node.start_byte:node.end_byte].decode("utf-8").strip())

	return imports


def _extract_function_definitions(root_node: Node, source_bytes: bytes) -> list[FunctionDefinition]:
	functions: list[FunctionDefinition] = []

	for node in _walk_tree(root_node):
		if node.type != "function_definition":
			continue

		name_node = node.child_by_field_name("name")
		if name_node is None:
			continue

		function_name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
		if function_name.startswith("__") and function_name.endswith("__"):
			continue
		normalized_name = function_name.lstrip("_")
		if not normalized_name:
			continue

		functions.append(
			FunctionDefinition(
				name=normalized_name,
				original_name=function_name,
				decorators=_extract_decorators(node, source_bytes),
				calls=_extract_called_function_names(node, source_bytes),
			)
		)

	return functions


def _extract_class_definitions(root_node: Node, source_bytes: bytes) -> list[ClassDefinition]:
	classes: list[ClassDefinition] = []

	for node in _walk_tree(root_node):
		if node.type != "class_definition":
			continue

		name_node = node.child_by_field_name("name")
		if name_node is None:
			continue

		class_name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
		classes.append(ClassDefinition(name=class_name, bases=_extract_class_bases(node, source_bytes)))

	return classes


def _extract_class_bases(node: Node, source_bytes: bytes) -> list[str]:
	bases: list[str] = []
	argument_list = next((child for child in node.children if child.type == "argument_list"), None)
	if argument_list is None:
		return bases

	for child in argument_list.children:
		if child.type in {"(", ")", ","}:
			continue
		bases.append(source_bytes[child.start_byte:child.end_byte].decode("utf-8"))

	return bases


def _extract_decorators(node: Node, source_bytes: bytes) -> list[str]:
	decorators: list[str] = []
	for child in node.children:
		if child.type == "decorator":
			decorators.append(source_bytes[child.start_byte:child.end_byte].decode("utf-8").lstrip("@"))
	return decorators


def _extract_called_function_names(function_node: Node, source_bytes: bytes) -> list[str]:
	called_functions: list[str] = []
	for node in _walk_tree(function_node):
		if node.type != "call":
			continue

		function_child = node.child_by_field_name("function")
		if function_child is None:
			continue

		called_name = source_bytes[function_child.start_byte:function_child.end_byte].decode("utf-8")
		called_functions.append(called_name.lstrip("_"))

	return list(dict.fromkeys(name for name in called_functions if name))


def _extract_relative_import_paths(import_statements: list[str]) -> list[str]:
	relative_paths: list[str] = []
	for statement in import_statements:
		if statement.startswith("from ."):
			module_part = statement.split(" import ", 1)[0].removeprefix("from ")
			relative_paths.append(module_part.replace(".", "/") + ".py")
	return list(dict.fromkeys(relative_paths))


def _language_name_for_path(file_path: Path) -> str:
	suffix = file_path.suffix.lower()
	if suffix == ".py":
		return "python"
	if suffix == ".sql":
		return "sql"
	if suffix in {".yml", ".yaml"}:
		return "yaml"
	if suffix in {".js", ".jsx", ".mjs", ".cjs"}:
		return "javascript"
	if suffix in {".ts", ".tsx"}:
		return "typescript"
	return suffix.lstrip(".")


def _walk_tree(root_node: Node):
	stack = [root_node]
	while stack:
		node = stack.pop()
		yield node
		stack.extend(reversed(node.children))


__all__ = ["LanguageRouter", "analyze_module", "parse_python_imports_and_functions"]
