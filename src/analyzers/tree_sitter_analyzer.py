from __future__ import annotations

from pathlib import Path

from tree_sitter import Language, Node, Parser
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_sql
import tree_sitter_yaml


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

	def get_language(self, file_path: str | Path) -> Language:
		suffix = Path(file_path).suffix.lower()
		loader = self._LANGUAGE_LOADERS.get(suffix)
		if loader is None:
			raise ValueError(f"Unsupported file extension: {suffix or '<none>'}")
		return Language(loader())

	def get_parser(self, file_path: str | Path) -> Parser:
		return Parser(self.get_language(file_path))


def parse_python_imports_and_functions(file_path: str | Path) -> dict[str, list[str]]:
	source_path = Path(file_path)
	source_bytes = source_path.read_bytes()

	router = LanguageRouter()
	parser = router.get_parser(source_path)
	tree = parser.parse(source_bytes)

	return {
		"imports": _extract_import_statements(tree.root_node, source_bytes),
		"public_functions": _extract_public_function_definitions(tree.root_node, source_bytes),
	}


def _extract_import_statements(root_node: Node, source_bytes: bytes) -> list[str]:
	imports: list[str] = []

	for node in _walk_tree(root_node):
		if node.type in {"import_statement", "import_from_statement"}:
			imports.append(source_bytes[node.start_byte:node.end_byte].decode("utf-8").strip())

	return imports


def _extract_public_function_definitions(root_node: Node, source_bytes: bytes) -> list[str]:
	functions: list[str] = []

	for node in _walk_tree(root_node):
		if node.type != "function_definition":
			continue

		name_node = node.child_by_field_name("name")
		if name_node is None:
			continue

		function_name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
		if not function_name.startswith("_"):
			functions.append(function_name)

	return functions


def _walk_tree(root_node: Node):
	stack = [root_node]
	while stack:
		node = stack.pop()
		yield node
		stack.extend(reversed(node.children))


__all__ = ["LanguageRouter", "parse_python_imports_and_functions"]
