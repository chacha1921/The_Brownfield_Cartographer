from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from graph.knowledge_graph import KnowledgeGraph
from utils import is_remote_repo_path, merge_cartography_graphs, remote_output_directory


DEFAULT_DASHBOARD_FILENAME = "dashboard.html"


def generate_dashboard(target_path: str | Path, output_path: str | Path | None = None) -> Path:
	artifact_dir = resolve_artifact_directory(target_path)
	module_graph = KnowledgeGraph.load_from_json(artifact_dir / "module_graph.json")
	lineage_graph = KnowledgeGraph.load_from_json(artifact_dir / "lineage_graph.json")
	merged_graph = merge_cartography_graphs(module_graph, lineage_graph)

	payload = _build_dashboard_payload(artifact_dir, module_graph, lineage_graph, merged_graph)
	destination = Path(output_path).resolve() if output_path is not None else artifact_dir / DEFAULT_DASHBOARD_FILENAME
	destination.parent.mkdir(parents=True, exist_ok=True)
	destination.write_text(_render_html_document(payload), encoding="utf-8")
	return destination


def resolve_artifact_directory(target_path: str | Path) -> Path:
	if isinstance(target_path, Path):
		candidate = target_path
	else:
		target_string = str(target_path)
		candidate = remote_output_directory(target_string) if is_remote_repo_path(target_string) else Path(target_string)

	if candidate.is_file():
		candidate = candidate.parent

	for artifact_dir in (candidate, candidate / ".cartography"):
		if (artifact_dir / "module_graph.json").exists() and (artifact_dir / "lineage_graph.json").exists():
			return artifact_dir.resolve()

	raise FileNotFoundError(
		"Could not find Cartographer artifacts. Pass a repository root containing .cartography/ or an artifact directory with module_graph.json and lineage_graph.json."
	)


def _build_dashboard_payload(
	artifact_dir: Path,
	module_graph: KnowledgeGraph,
	lineage_graph: KnowledgeGraph,
	merged_graph: KnowledgeGraph,
) -> dict[str, Any]:
	module_graph_payload = _serialize_graph(module_graph, view_id="surveyor", title="Surveyor")
	semantic_graph_payload = _serialize_graph(
		module_graph,
		view_id="semanticist",
		title="Semanticist",
		node_filter=lambda _, attributes: attributes.get("node_type") == "module",
	)
	lineage_graph_payload = _serialize_graph(lineage_graph, view_id="hydrologist", title="Hydrologist")
	navigator_graph_payload = _serialize_graph(
		merged_graph,
		view_id="navigator",
		title="Navigator",
		node_filter=_merged_focus_filter(merged_graph),
	)

	semantic_summary = _build_semantic_summary(module_graph)
	hydrologist_summary = _build_hydrologist_summary(lineage_graph)
	navigator_summary = _build_navigator_summary(merged_graph)

	agents = [
		{
			"id": "surveyor",
			"name": "Surveyor",
			"tagline": "Module structure and dependency graph",
      "theme": {"accent": "#4f8cff", "accentSoft": "rgba(79, 140, 255, 0.18)", "glow": "rgba(79, 140, 255, 0.28)"},
      "graphStyle": "surveyor",
			"graph": module_graph_payload,
			"summary": {
				"title": "Static architecture",
				"bullets": [
					f"{module_graph_payload['stats']['nodeCount']} nodes and {module_graph_payload['stats']['edgeCount']} edges in the module graph.",
					f"Most connected node: {module_graph_payload['stats']['mostConnectedNode'] or 'n/a'}.",
					"Use search to jump to a module or function, then click a node for metadata.",
				],
			},
			"files": [
				_load_file_payload(artifact_dir / "module_graph.json", "module_graph.json", "json"),
			],
		},
		{
			"id": "hydrologist",
			"name": "Hydrologist",
			"tagline": "Lineage graph with source and sink hints",
      "theme": {"accent": "#22c55e", "accentSoft": "rgba(34, 197, 94, 0.18)", "glow": "rgba(34, 197, 94, 0.28)"},
      "graphStyle": "hydrologist",
			"graph": lineage_graph_payload,
			"summary": {
				"title": "Data lineage",
				"bullets": [
					f"{lineage_graph_payload['stats']['nodeCount']} nodes and {lineage_graph_payload['stats']['edgeCount']} edges across datasets and transformations.",
					f"Initial/source datasets: {hydrologist_summary['sourceCount']}. Terminal sinks: {hydrologist_summary['sinkCount']}.",
					f"Most connected node: {lineage_graph_payload['stats']['mostConnectedNode'] or 'n/a'}.",
				],
				"lists": hydrologist_summary["lists"],
			},
			"files": [
				_load_file_payload(artifact_dir / "lineage_graph.json", "lineage_graph.json", "json"),
			],
		},
		{
			"id": "semanticist",
			"name": "Semanticist",
			"tagline": "Purpose statements and domain-cluster view",
      "theme": {"accent": "#a855f7", "accentSoft": "rgba(168, 85, 247, 0.18)", "glow": "rgba(168, 85, 247, 0.28)"},
      "graphStyle": "semanticist",
			"graph": semantic_graph_payload,
			"summary": {
				"title": "Semantic enrichment",
				"bullets": [
					f"Purpose statements available for {semantic_summary['purposeCount']} modules.",
					f"Domain clusters discovered: {semantic_summary['clusterCount']}.",
					f"Most connected node: {semantic_graph_payload['stats']['mostConnectedNode'] or 'n/a'}.",
				],
				"lists": semantic_summary["lists"],
			},
			"files": [
				_load_file_payload(artifact_dir / "day_one_answers.json", "day_one_answers.json", "json"),
			],
		},
		{
			"id": "archivist",
			"name": "Archivist",
			"tagline": "Rendered outputs after synthesis",
      "theme": {"accent": "#f59e0b", "accentSoft": "rgba(245, 158, 11, 0.18)", "glow": "rgba(245, 158, 11, 0.28)"},
      "graphStyle": "archivist",
			"graph": None,
			"summary": {
				"title": "Generated deliverables",
				"bullets": [
					"Browse the markdown and JSON artifacts without leaving the dashboard.",
					"Use these tabs during the video to show CODEBASE, onboarding, day-one answers, and trace evidence quickly.",
				],
			},
			"files": [
				_load_file_payload(artifact_dir / "CODEBASE.md", "CODEBASE.md", "markdown"),
				_load_file_payload(artifact_dir / "onboarding_brief.md", "onboarding_brief.md", "markdown"),
				_load_file_payload(artifact_dir / "day_one_answers.json", "day_one_answers.json", "json"),
				_load_file_payload(artifact_dir / "cartography_trace.jsonl", "cartography_trace.jsonl", "text"),
				_load_file_payload(artifact_dir / "run_metadata.json", "run_metadata.json", "json"),
			],
		},
		{
			"id": "navigator",
			"name": "Navigator",
			"tagline": "Merged focus graph for demo-ready questioning",
      "theme": {"accent": "#06b6d4", "accentSoft": "rgba(6, 182, 212, 0.18)", "glow": "rgba(6, 182, 212, 0.28)"},
      "graphStyle": "navigator",
			"graph": navigator_graph_payload,
			"summary": {
				"title": "Query-ready merged view",
				"bullets": [
					f"Focus view contains {navigator_graph_payload['stats']['nodeCount']} high-signal nodes from the merged graph.",
					f"Most connected node: {navigator_graph_payload['stats']['mostConnectedNode'] or 'n/a'}.",
					"Use this panel to show how architecture and lineage intersect before running CLI queries.",
				],
				"lists": navigator_summary["lists"],
			},
			"files": [
				{
					"name": "query_examples.txt",
					"format": "text",
					"content": navigator_summary["queryExamplesText"],
				},
			],
		},
	]

	return {
		"title": f"Cartographer Dashboard · {artifact_dir.parent.name if artifact_dir.name == '.cartography' else artifact_dir.name}",
		"artifactDirectory": str(artifact_dir),
		"generatedFiles": [file_payload["name"] for agent in agents for file_payload in agent["files"]],
		"agents": agents,
	}


def _merged_focus_filter(merged_graph: KnowledgeGraph):
	graph = merged_graph.graph
	degree_map = dict(graph.degree())
	module_nodes = [node_id for node_id, attributes in graph.nodes(data=True) if attributes.get("node_type") == "module"]
	dataset_nodes = [node_id for node_id, attributes in graph.nodes(data=True) if attributes.get("node_type") == "dataset"]
	transformation_nodes = [node_id for node_id, attributes in graph.nodes(data=True) if attributes.get("node_type") == "transformation"]
	selected_nodes = set(_top_nodes(module_nodes, degree_map, limit=80))
	selected_nodes.update(_top_nodes(dataset_nodes, degree_map, limit=90))
	selected_nodes.update(_top_nodes(transformation_nodes, degree_map, limit=50))
	selected_nodes.update(_top_nodes(list(graph.nodes), degree_map, limit=180))

	def _filter(node_id: str, _: dict[str, Any]) -> bool:
		return node_id in selected_nodes

	return _filter


def _serialize_graph(
	knowledge_graph: KnowledgeGraph,
	*,
	view_id: str,
	title: str,
	node_filter: Any | None = None,
) -> dict[str, Any]:
	graph = knowledge_graph.graph.copy()
	if node_filter is not None:
		allowed_nodes = [node_id for node_id, attributes in graph.nodes(data=True) if node_filter(node_id, attributes)]
		graph = graph.subgraph(allowed_nodes).copy()

	positions = _compute_positions(graph, view_id)
	degree_map = dict(graph.degree())
	max_degree = max(degree_map.values(), default=0)
	node_type_counts = Counter(str(attributes.get("node_type", "unknown")) for _, attributes in graph.nodes(data=True))

	nodes: list[dict[str, Any]] = []
	for node_id, attributes in graph.nodes(data=True):
		x, y = positions.get(node_id, (0.0, 0.0))
		label = _node_label(node_id, attributes)
		nodes.append(
			{
				"id": node_id,
				"label": label,
				"shortLabel": label if len(label) <= 28 else f"{label[:25]}…",
				"x": round(x, 2),
				"y": round(y, 2),
				"nodeType": attributes.get("node_type", "unknown"),
				"storageType": attributes.get("storage_type"),
				"domainCluster": attributes.get("domain_cluster"),
				"degree": degree_map.get(node_id, 0),
				"inDegree": graph.in_degree(node_id),
				"outDegree": graph.out_degree(node_id),
				"isSource": attributes.get("node_type") == "dataset" and graph.in_degree(node_id) == 0 and graph.out_degree(node_id) > 0,
				"isSink": attributes.get("node_type") == "dataset" and graph.out_degree(node_id) == 0 and graph.in_degree(node_id) > 0,
				"isMostConnected": degree_map.get(node_id, 0) == max_degree and max_degree > 0,
				"color": _node_color(attributes),
				"metadata": _node_metadata(attributes),
			}
		)

	edges = [
		{
			"source": source,
			"target": target,
			"edgeType": attributes.get("edge_type", "UNKNOWN"),
			"sourceFile": attributes.get("source_file"),
			"lineStart": attributes.get("line_start"),
			"lineEnd": attributes.get("line_end"),
			"transformationType": attributes.get("transformation_type"),
			"dialect": attributes.get("dialect"),
		}
		for source, target, attributes in graph.edges(data=True)
	]

	most_connected_node = next((node["label"] for node in nodes if node["isMostConnected"]), None)

	return {
		"id": view_id,
		"title": title,
    "style": view_id,
		"nodes": nodes,
		"edges": edges,
		"stats": {
			"nodeCount": graph.number_of_nodes(),
			"edgeCount": graph.number_of_edges(),
			"mostConnectedNode": most_connected_node,
			"nodeTypeCounts": dict(sorted(node_type_counts.items())),
		},
	}


def _build_semantic_summary(module_graph: KnowledgeGraph) -> dict[str, Any]:
	cluster_to_modules: dict[str, list[str]] = defaultdict(list)
	purpose_count = 0
	for _, attributes in module_graph.graph.nodes(data=True):
		if attributes.get("node_type") != "module":
			continue
		if attributes.get("purpose_statement"):
			purpose_count += 1
		cluster_name = str(attributes.get("domain_cluster") or "Unclustered")
		cluster_to_modules[cluster_name].append(str(attributes.get("path") or attributes.get("id") or "unknown"))

	lists = []
	for cluster_name, members in sorted(cluster_to_modules.items(), key=lambda item: (-len(item[1]), item[0]))[:6]:
		lists.append({"title": cluster_name, "items": sorted(members)[:8]})

	return {
		"purposeCount": purpose_count,
		"clusterCount": len(cluster_to_modules),
		"lists": lists,
	}


def _build_hydrologist_summary(lineage_graph: KnowledgeGraph) -> dict[str, Any]:
	graph = lineage_graph.graph
	sources = []
	sinks = []
	for node_id, attributes in graph.nodes(data=True):
		if attributes.get("node_type") != "dataset":
			continue
		if graph.in_degree(node_id) == 0 and graph.out_degree(node_id) > 0:
			sources.append(node_id)
		if graph.out_degree(node_id) == 0 and graph.in_degree(node_id) > 0:
			sinks.append(node_id)

	return {
		"sourceCount": len(sources),
		"sinkCount": len(sinks),
		"lists": [
			{"title": "Initial sources", "items": sorted(sources)[:10]},
			{"title": "Terminal sinks", "items": sorted(sinks)[:10]},
		],
	}


def _build_navigator_summary(merged_graph: KnowledgeGraph) -> dict[str, Any]:
	query_examples = [
		"blast radius for src/ol_orchestrate/__init__.py",
		"upstream sources for reporting.student_risk_probability",
		"find implementation for edxorg S3 ingest",
		"which modules should I read first to understand the critical path?",
	]
	return {
		"lists": [{"title": "Suggested queries", "items": query_examples}],
		"queryExamplesText": "\n".join(f"- {item}" for item in query_examples),
	}


def _compute_positions(graph, view_id: str) -> dict[str, tuple[float, float]]:
	if view_id == "hydrologist":
		return _layout_hydrologist(graph)
	if view_id == "semanticist":
		return _layout_semanticist(graph)
	if view_id == "navigator":
		return _layout_grouped_rings(graph, ["module", "transformation", "dataset", "function"])
	return _layout_grouped_rings(graph, ["module", "function", "dataset", "transformation"])


def _stable_fraction(key: str, salt: str) -> float:
  digest = hashlib.sha256(f"{salt}:{key}".encode("utf-8")).digest()
  return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _stable_signed_offset(key: str, salt: str) -> float:
  return (_stable_fraction(key, salt) * 2.0) - 1.0


def _sunflower_layout(
  items: list[str],
  *,
  center: tuple[float, float],
  max_radius: float,
  min_radius: float = 18.0,
  x_scale: float = 1.0,
  y_scale: float = 1.0,
  angle_offset: float = 0.0,
  jitter: float = 0.18,
) -> dict[str, tuple[float, float]]:
  if not items:
    return {}
  if len(items) == 1:
    return {items[0]: center}

  center_x, center_y = center
  golden_angle = math.pi * (3 - math.sqrt(5))
  positions: dict[str, tuple[float, float]] = {}
  for index, item in enumerate(items):
    progress = (index + 0.5) / len(items)
    radius = min_radius + (max_radius - min_radius) * math.sqrt(progress)
    radial_jitter = 1.0 + _stable_signed_offset(item, "radial") * jitter
    angle = angle_offset + index * golden_angle + _stable_signed_offset(item, "angle") * 0.45
    x = center_x + math.cos(angle) * radius * x_scale * radial_jitter + _stable_signed_offset(item, "x") * max_radius * 0.08
    y = center_y + math.sin(angle) * radius * y_scale * radial_jitter + _stable_signed_offset(item, "y") * max_radius * 0.08
    positions[item] = (x, y)
  return positions


def _spiral_centers(labels: list[str], *, spacing: float) -> dict[str, tuple[float, float]]:
	if not labels:
		return {}
	positions: dict[str, tuple[float, float]] = {labels[0]: (0.0, 0.0)}
	golden_angle = math.pi * (3 - math.sqrt(5))
	for index, label in enumerate(labels[1:], start=1):
		radius = spacing * math.sqrt(index)
		angle = (index - 1) * golden_angle + _stable_signed_offset(label, "cluster-angle") * 0.35
		positions[label] = (
			math.cos(angle) * radius * 1.08,
			math.sin(angle) * radius * 0.82,
		)
	return positions


def _layout_grouped_rings(graph, ordered_types: list[str]) -> dict[str, tuple[float, float]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for node_id, attributes in graph.nodes(data=True):
        groups[str(attributes.get("node_type", "unknown"))].append(node_id)

    positions: dict[str, tuple[float, float]] = {}
    group_order = ordered_types + [name for name in groups if name not in ordered_types]
    anchor_points = [(-250.0, -150.0), (235.0, -120.0), (-175.0, 175.0), (250.0, 170.0), (0.0, 0.0), (-35.0, -300.0), (40.0, 300.0)]
    for index, group_name in enumerate(group_order):
        nodes = sorted(groups.get(group_name, []))
        if not nodes:
            continue
        if index < len(anchor_points):
            center = anchor_points[index]
        else:
            spill_index = index - len(anchor_points) + 1
            spill_radius = 300.0 + spill_index * 72.0
            spill_angle = spill_index * 1.2
            center = (math.cos(spill_angle) * spill_radius, math.sin(spill_angle) * spill_radius * 0.72)
        positions.update(
            _sunflower_layout(
                nodes,
                center=center,
                max_radius=105.0 + len(nodes) * 4.5,
                min_radius=20.0,
                x_scale=1.14 if index % 2 == 0 else 0.94,
                y_scale=0.92 if index % 2 == 0 else 1.16,
                angle_offset=index * 0.65,
            )
        )
    return positions


def _layout_hydrologist(graph) -> dict[str, tuple[float, float]]:
    source_nodes = []
    sink_nodes = []
    transformation_nodes = []
    other_nodes = []
    for node_id, attributes in graph.nodes(data=True):
        if attributes.get("node_type") == "transformation":
            transformation_nodes.append(node_id)
        elif attributes.get("node_type") == "dataset" and graph.in_degree(node_id) == 0 and graph.out_degree(node_id) > 0:
            source_nodes.append(node_id)
        elif attributes.get("node_type") == "dataset" and graph.out_degree(node_id) == 0 and graph.in_degree(node_id) > 0:
            sink_nodes.append(node_id)
        else:
            other_nodes.append(node_id)

    positions: dict[str, tuple[float, float]] = {}
    positions.update(_sunflower_layout(sorted(source_nodes), center=(-315.0, -10.0), max_radius=195.0 + len(source_nodes) * 2.5, min_radius=26.0, x_scale=0.74, y_scale=1.46, angle_offset=-0.8))
    positions.update(_sunflower_layout(sorted(transformation_nodes), center=(0.0, 0.0), max_radius=145.0 + len(transformation_nodes) * 2.4, min_radius=18.0, x_scale=1.0, y_scale=0.95, angle_offset=0.2))
    positions.update(_sunflower_layout(sorted(sink_nodes), center=(315.0, 18.0), max_radius=195.0 + len(sink_nodes) * 2.5, min_radius=26.0, x_scale=0.74, y_scale=1.46, angle_offset=0.95))
    positions.update(_sunflower_layout(sorted(other_nodes), center=(0.0, 205.0), max_radius=235.0 + len(other_nodes) * 2.8, min_radius=72.0, x_scale=1.22, y_scale=0.94, angle_offset=1.1))
    return positions


def _layout_semanticist(graph) -> dict[str, tuple[float, float]]:
    clusters: dict[str, list[str]] = defaultdict(list)
    for node_id, attributes in graph.nodes(data=True):
        cluster_name = str(attributes.get("domain_cluster") or "Unclustered")
        clusters[cluster_name].append(node_id)

    cluster_names = sorted(clusters, key=lambda name: (-len(clusters[name]), name))
    if not cluster_names:
        return {}

    cluster_centers = _spiral_centers(cluster_names, spacing=235.0)
    positions: dict[str, tuple[float, float]] = {}
    for cluster_name, members in clusters.items():
        center = cluster_centers[cluster_name]
        positions.update(
            _sunflower_layout(
                sorted(members),
                center=center,
                max_radius=90.0 + max(22.0, len(members) * 5.0),
                min_radius=16.0,
                x_scale=1.04,
                y_scale=0.96,
                angle_offset=_stable_signed_offset(cluster_name, "semantic-cluster") * math.pi,
            )
        )
    return positions


def _circle_layout(items: list[str], *, center: tuple[float, float], radius: float) -> dict[str, tuple[float, float]]:
	if not items:
		return {}
	if len(items) == 1:
		return {items[0]: center}
	center_x, center_y = center
	positions: dict[str, tuple[float, float]] = {}
	for index, item in enumerate(items):
		angle = (2 * math.pi * index) / len(items)
		positions[item] = (center_x + radius * math.cos(angle), center_y + radius * math.sin(angle))
	return positions


def _arc_layout(
	items: list[str],
	*,
	center: tuple[float, float],
	radius: float,
	start_angle: float,
	end_angle: float,
) -> dict[str, tuple[float, float]]:
	if not items:
		return {}
	center_x, center_y = center
	positions: dict[str, tuple[float, float]] = {}
	for index, item in enumerate(items):
		progress = 0.5 if len(items) == 1 else index / (len(items) - 1)
		angle = start_angle + (end_angle - start_angle) * progress
		positions[item] = (center_x + radius * math.cos(angle), center_y + radius * math.sin(angle))
	return positions


def _node_label(node_id: str, attributes: dict[str, Any]) -> str:
	for key in ("name", "path"):
		value = attributes.get(key)
		if isinstance(value, str) and value.strip():
			return value
	return node_id


def _node_color(attributes: dict[str, Any]) -> str:
	node_type = str(attributes.get("node_type", "unknown"))
	if node_type == "module":
		return "#4f8cff"
	if node_type == "function":
		return "#8a63ff"
	if node_type == "transformation":
		return "#ff8f3d"
	if node_type == "dataset":
		storage_type = str(attributes.get("storage_type") or "")
		if storage_type == "dbt_source":
			return "#38bdf8"
		if storage_type == "dbt_model":
			return "#34d399"
		if storage_type == "dynamic_reference":
			return "#f472b6"
		return "#22c55e"
	return "#94a3b8"


def _node_metadata(attributes: dict[str, Any]) -> dict[str, Any]:
	interesting_keys = [
		"path",
		"language",
		"storage_type",
		"domain_cluster",
		"purpose_statement",
		"complexity_score",
		"change_velocity_30d",
		"is_dead_code_candidate",
		"schema_snapshot",
		"source_file",
		"owner",
		"freshness_sla",
	]
	return {key: attributes.get(key) for key in interesting_keys if attributes.get(key) not in (None, [], {}, "")}


def _top_nodes(node_ids: list[str], degree_map: dict[str, int], *, limit: int) -> list[str]:
	return sorted(node_ids, key=lambda node_id: (-degree_map.get(node_id, 0), node_id))[:limit]


def _load_file_payload(file_path: Path, display_name: str, file_format: str) -> dict[str, str]:
	content = file_path.read_text(encoding="utf-8") if file_path.exists() else f"Missing file: {display_name}"
	return {"name": display_name, "format": file_format, "content": content}


def _safe_json_for_html(payload: dict[str, Any]) -> str:
	return json.dumps(payload, ensure_ascii=False).replace("</script>", "<\\/script>")


def _render_html_document(payload: dict[str, Any]) -> str:
	return HTML_TEMPLATE.replace("__DASHBOARD_DATA__", _safe_json_for_html(payload))


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Cartographer Dashboard</title>
  <style>
    :root {
      --bg: #081120;
      --panel: #0f1b2d;
      --panel-soft: #122238;
      --border: rgba(148, 163, 184, 0.2);
      --text: #e5eefc;
      --muted: #9fb4d3;
      --accent: #4f8cff;
      --agent-accent: #4f8cff;
      --agent-accent-soft: rgba(79, 140, 255, 0.18);
      --agent-glow: rgba(79, 140, 255, 0.28);
      --accent-2: #22c55e;
      --warn: #ff8f3d;
      --danger: #f472b6;
      --shadow: 0 16px 40px rgba(0, 0, 0, 0.28);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
      background: radial-gradient(circle at top, #12294a, #081120 48%);
      color: var(--text);
    }
    .app {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr) 360px;
      min-height: 100vh;
    }
    .sidebar, .details {
      background: rgba(8, 17, 32, 0.88);
      backdrop-filter: blur(16px);
      border-right: 1px solid var(--border);
      padding: 24px;
    }
    .details {
      border-right: none;
      border-left: 1px solid var(--border);
      overflow: auto;
    }
    .main {
      padding: 20px;
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr) auto;
      gap: 16px;
      min-width: 0;
    }
    .brand h1 {
      font-size: 1.1rem;
      margin: 0 0 6px;
    }
    .brand p, .muted { color: var(--muted); }
    .artifact-path {
      display: block;
      margin-top: 8px;
      font-size: 0.78rem;
      color: #7dd3fc;
      word-break: break-all;
    }
    .agent-list {
      margin-top: 24px;
      display: grid;
      gap: 10px;
    }
    .agent-button {
      width: 100%;
      text-align: left;
      border: 1px solid var(--border);
      background: var(--panel);
      color: var(--text);
      border-radius: 16px;
      padding: 14px 16px;
      cursor: pointer;
      transition: transform 0.15s ease, border-color 0.15s ease, background 0.15s ease;
    }
    .agent-button:hover, .agent-button.active {
      transform: translateY(-1px);
      border-color: var(--agent-glow);
      background: linear-gradient(180deg, var(--agent-accent-soft), rgba(15, 27, 45, 0.96));
    }
    .agent-button strong { display: block; margin-bottom: 4px; font-size: 0.95rem; }
    .agent-button span { color: var(--muted); font-size: 0.82rem; }
    .toolbar, .stats, .file-tabs, .summary-card, .details-card {
      background: rgba(15, 27, 45, 0.88);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }
    .toolbar {
      padding: 10px 12px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      background: rgba(8, 17, 32, 0.62);
      backdrop-filter: blur(14px);
    }
    .toolbar input {
      min-width: 260px;
      flex: 1;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      padding: 11px 12px;
    }
    .toolbar button, .file-tab {
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.06);
      color: var(--text);
      border-radius: 999px;
      padding: 10px 12px;
      cursor: pointer;
    }
    .toolbar button:hover, .file-tab.active { border-color: var(--agent-glow); }
    .stats {
      padding: 14px;
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      background: rgba(8, 17, 32, 0.56);
      backdrop-filter: blur(12px);
    }
    .stat-card {
      background: rgba(8, 17, 32, 0.72);
      border-radius: 14px;
      padding: 12px;
      border: 1px solid rgba(148, 163, 184, 0.12);
    }
    .stat-card .label { color: var(--muted); font-size: 0.8rem; }
    .stat-card .value { margin-top: 8px; font-size: 1.3rem; font-weight: 700; }
    .graph-shell {
      min-height: 540px;
      background:
        radial-gradient(circle at top right, rgba(255,255,255,0.12), transparent 22%),
        radial-gradient(circle at center, rgba(255,255,255,0.08), transparent 48%),
        linear-gradient(180deg, rgba(194, 209, 225, 0.94), rgba(132, 150, 172, 0.92));
      border: 1px solid var(--border);
      border-radius: 22px;
      overflow: hidden;
      position: relative;
      box-shadow: var(--shadow);
    }
    .graph-header {
      position: absolute;
      top: 14px;
      left: 16px;
      right: 16px;
      z-index: 2;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      pointer-events: none;
    }
    .graph-title-wrap {
      background: rgba(255, 255, 255, 0.38);
      border: 1px solid rgba(255, 255, 255, 0.3);
      border-radius: 14px;
      padding: 10px 12px;
      backdrop-filter: blur(10px);
      max-width: min(70%, 560px);
    }
    .graph-title-wrap h2 {
      margin: 0 0 4px;
      font-size: 0.98rem;
    }
    .graph-title-wrap p {
      margin: 0;
      color: rgba(15, 23, 42, 0.72);
      font-size: 0.8rem;
    }
    .graph-style-pill {
      background: rgba(255, 255, 255, 0.4);
      color: #0f172a;
      border: 1px solid rgba(255,255,255,0.36);
      border-radius: 999px;
      padding: 10px 14px;
      font-size: 0.78rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      box-shadow: 0 0 0 1px rgba(255,255,255,0.03) inset;
    }
    canvas { width: 100%; height: 100%; display: block; }
    .graph-empty {
      position: absolute;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      color: var(--muted);
      font-size: 1rem;
    }
    .legend {
      position: absolute;
      left: 16px;
      bottom: 16px;
      background: rgba(255, 255, 255, 0.38);
      border: 1px solid rgba(255,255,255,0.3);
      border-radius: 14px;
      padding: 12px;
      display: grid;
      gap: 8px;
      font-size: 0.8rem;
      backdrop-filter: blur(12px);
    }
    .legend-row {
      display: flex;
      align-items: center;
      gap: 8px;
      color: rgba(15, 23, 42, 0.72);
    }
    .legend-dot {
      width: 12px;
      height: 12px;
      border-radius: 999px;
      display: inline-block;
    }
    .legend-shape {
      width: 14px;
      height: 14px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 0.72rem;
      color: #0f172a;
      border: 1px solid rgba(15, 23, 42, 0.12);
      background: rgba(255,255,255,0.18);
    }
    .graph-float-controls {
      position: absolute;
      right: 18px;
      bottom: 18px;
      display: flex;
      gap: 10px;
      z-index: 3;
    }
    .graph-float-controls button {
      width: 44px;
      height: 44px;
      border-radius: 999px;
      border: 2px solid rgba(74, 138, 77, 0.55);
      background: rgba(210, 241, 212, 0.55);
      color: #2f6b34;
      font-size: 1.4rem;
      line-height: 1;
      cursor: pointer;
      box-shadow: 0 6px 18px rgba(0, 0, 0, 0.14);
    }
    .graph-float-controls button:hover {
      background: rgba(220, 248, 223, 0.78);
    }
    .legend-shape.square { border-radius: 4px; }
    .legend-shape.circle { border-radius: 999px; }
    .legend-shape.double-circle {
      border-radius: 999px;
      position: relative;
    }
    .legend-shape.double-circle::after {
      content: '';
      position: absolute;
      width: 6px;
      height: 6px;
      border-radius: 999px;
      border: 1px solid rgba(15, 23, 42, 0.16);
      background: rgba(255,255,255,0.32);
    }
    .legend-shape.diamond { transform: rotate(45deg); border-radius: 3px; }
    .legend-shape.diamond > span { transform: rotate(-45deg); display: inline-block; }
    .file-tabs { padding: 12px; }
    .file-tab-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 12px;
    }
    .file-content {
      background: rgba(8, 17, 32, 0.8);
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.12);
      max-height: 320px;
      overflow: auto;
      padding: 14px;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.82rem;
      line-height: 1.45;
    }
    .summary-card, .details-card {
      padding: 16px;
      margin-bottom: 16px;
    }
    .summary-card h2, .details-card h2, .details-card h3 {
      margin: 0 0 10px;
      font-size: 1rem;
    }
    .summary-card ul, .details-card ul { margin: 0; padding-left: 18px; }
    .summary-card li, .details-card li { margin: 0 0 8px; color: var(--muted); }
    .kv-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 8px;
    }
    #selection-panel {
      max-height: 320px;
      overflow: auto;
      padding-right: 4px;
    }
    #highlight-lists {
      max-height: 300px;
      overflow: auto;
      padding-right: 4px;
    }
    .kv-item {
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(8, 17, 32, 0.72);
      border: 1px solid rgba(148, 163, 184, 0.1);
    }
    .kv-item strong { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 5px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.82rem; }
    @media (max-width: 1180px) {
      .app { grid-template-columns: 260px minmax(0, 1fr); }
      .details { grid-column: 1 / -1; border-left: none; border-top: 1px solid var(--border); }
    }
    @media (max-width: 960px) {
      .app { grid-template-columns: 1fr; }
      .sidebar, .details { border: none; }
      .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <div class=\"app\">
    <aside class=\"sidebar\">
      <div class=\"brand\">
        <p class=\"muted\">Brownfield Cartographer</p>
        <h1 id=\"dashboard-title\"></h1>
        <span class=\"artifact-path\" id=\"artifact-path\"></span>
      </div>
      <div class=\"agent-list\" id=\"agent-list\"></div>
    </aside>

    <main class=\"main\">
      <section class=\"toolbar\">
        <input id=\"search-input\" type=\"search\" placeholder=\"Search nodes, files, datasets, modules…\" />
        <button id=\"search-button\">Search</button>
        <button data-zoom=\"in\">Zoom In</button>
        <button data-zoom=\"out\">Zoom Out</button>
        <button data-zoom=\"reset\">Reset View</button>
      </section>

      <section class=\"stats\" id=\"stats\"></section>

      <section class=\"graph-shell\">
        <div class=\"graph-header\">
          <div class=\"graph-title-wrap\">
            <h2 id=\"graph-title\"></h2>
            <p id=\"graph-subtitle\"></p>
          </div>
          <div class=\"graph-style-pill\" id=\"graph-style-pill\"></div>
        </div>
        <canvas id=\"graph-canvas\"></canvas>
        <div class=\"graph-empty\" id=\"graph-empty\">This agent focuses on files rather than a graph view.</div>
        <div class=\"legend\" id=\"legend\"></div>
        <div class=\"graph-float-controls\">
          <button data-zoom=\"out\" aria-label=\"Zoom out\">−</button>
          <button data-zoom=\"in\" aria-label=\"Zoom in\">+</button>
        </div>
      </section>

      <section class=\"file-tabs\">
        <div class=\"file-tab-row\" id=\"file-tab-row\"></div>
        <div class=\"file-content mono\" id=\"file-content\"></div>
      </section>
    </main>

    <aside class=\"details\">
      <section class=\"summary-card\">
        <h2 id=\"summary-title\"></h2>
        <ul id=\"summary-bullets\"></ul>
      </section>
      <section class=\"details-card\">
        <h2>Selection</h2>
        <div class=\"kv-grid\" id=\"selection-panel\"></div>
      </section>
      <section class=\"details-card\">
        <h2>Highlights</h2>
        <div id=\"highlight-lists\"></div>
      </section>
    </aside>
  </div>

  <script>
    const DASHBOARD_DATA = __DASHBOARD_DATA__;

    const state = {
      currentAgentId: DASHBOARD_DATA.agents[0]?.id || null,
      selectedNodeId: null,
      highlightedNodeIds: [],
      highlightedEdgeKeys: [],
      activeFileName: null,
      scale: 0.65,
      offsetX: 0,
      offsetY: 0,
      dragging: false,
      isPanning: false,
      dragStartX: 0,
      dragStartY: 0,
      pointerDownX: 0,
      pointerDownY: 0,
    };

    const canvas = document.getElementById('graph-canvas');
    const context = canvas.getContext('2d');
    const elements = {
      title: document.getElementById('dashboard-title'),
      artifactPath: document.getElementById('artifact-path'),
      agentList: document.getElementById('agent-list'),
      stats: document.getElementById('stats'),
      summaryTitle: document.getElementById('summary-title'),
      summaryBullets: document.getElementById('summary-bullets'),
      selectionPanel: document.getElementById('selection-panel'),
      highlightLists: document.getElementById('highlight-lists'),
      fileTabRow: document.getElementById('file-tab-row'),
      fileContent: document.getElementById('file-content'),
      searchInput: document.getElementById('search-input'),
      graphEmpty: document.getElementById('graph-empty'),
      legend: document.getElementById('legend'),
      graphTitle: document.getElementById('graph-title'),
      graphSubtitle: document.getElementById('graph-subtitle'),
      graphStylePill: document.getElementById('graph-style-pill'),
    };

    function currentAgent() {
      return DASHBOARD_DATA.agents.find((agent) => agent.id === state.currentAgentId) || DASHBOARD_DATA.agents[0];
    }

    function currentGraph() {
      return currentAgent()?.graph || null;
    }

    function currentTheme() {
      return currentAgent()?.theme || { accent: '#4f8cff', accentSoft: 'rgba(79, 140, 255, 0.18)', glow: 'rgba(79, 140, 255, 0.28)' };
    }

    function applyTheme() {
      const theme = currentTheme();
      document.documentElement.style.setProperty('--agent-accent', theme.accent);
      document.documentElement.style.setProperty('--agent-accent-soft', theme.accentSoft);
      document.documentElement.style.setProperty('--agent-glow', theme.glow);
    }

    function resizeCanvas() {
      const rect = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(rect.width * ratio);
      canvas.height = Math.floor(rect.height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      drawGraph();
    }

    function resetViewport() {
      const graph = currentGraph();
      const rect = canvas.getBoundingClientRect();
      if (!graph || !graph.nodes.length || !rect.width || !rect.height) {
        state.scale = 0.82;
        state.offsetX = 0;
        state.offsetY = 0;
        return;
      }

      const xs = graph.nodes.map((node) => node.x);
      const ys = graph.nodes.map((node) => node.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const padding = 110;
      const graphWidth = Math.max(maxX - minX + padding * 2, 220);
      const graphHeight = Math.max(maxY - minY + padding * 2, 220);
      const scaleX = rect.width / graphWidth;
      const scaleY = rect.height / graphHeight;

      state.scale = Math.max(0.24, Math.min(1.28, Math.min(scaleX, scaleY)));
      state.offsetX = -((minX + maxX) / 2) * state.scale;
      state.offsetY = -((minY + maxY) / 2) * state.scale;
    }

    function renderSidebar() {
      elements.title.textContent = DASHBOARD_DATA.title;
      elements.artifactPath.textContent = DASHBOARD_DATA.artifactDirectory;
      elements.agentList.innerHTML = '';

      for (const agent of DASHBOARD_DATA.agents) {
        const button = document.createElement('button');
        button.className = `agent-button${agent.id === state.currentAgentId ? ' active' : ''}`;
        button.innerHTML = `<strong>${agent.name}</strong><span>${agent.tagline}</span>`;
        button.addEventListener('click', () => {
          state.currentAgentId = agent.id;
          state.selectedNodeId = null;
          state.highlightedNodeIds = [];
          state.highlightedEdgeKeys = [];
          state.activeFileName = agent.files[0]?.name || null;
          render();
          resetViewport();
          drawGraph();
        });
        elements.agentList.appendChild(button);
      }
    }

    function renderStats() {
      const agent = currentAgent();
      const graph = currentGraph();
      const stats = graph?.stats || { nodeCount: 0, edgeCount: 0, mostConnectedNode: 'n/a', nodeTypeCounts: {} };
      const dominantType = Object.entries(stats.nodeTypeCounts || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || 'n/a';
      const cards = [
        ['Nodes', stats.nodeCount],
        ['Edges', stats.edgeCount],
        ['Top Node', stats.mostConnectedNode || 'n/a'],
        ['Top Type', dominantType],
      ];
      elements.stats.innerHTML = cards.map(([label, value]) => `
        <article class=\"stat-card\">
          <div class=\"label\">${label}</div>
          <div class=\"value\">${value}</div>
        </article>`).join('');

      elements.graphEmpty.style.display = graph ? 'none' : 'flex';
      canvas.style.display = graph ? 'block' : 'none';
      elements.graphTitle.textContent = agent.name;
      elements.graphSubtitle.textContent = graph ? agent.tagline : 'File-focused output viewer';
      elements.graphStylePill.textContent = graph ? `${agent.graphStyle} view` : 'artifact viewer';
    }

    function renderSummary() {
      const agent = currentAgent();
      elements.summaryTitle.textContent = agent.summary?.title || agent.name;
      elements.summaryBullets.innerHTML = (agent.summary?.bullets || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');

      const lists = agent.summary?.lists || [];
      elements.highlightLists.innerHTML = lists.map((list) => `
        <div style=\"margin-bottom: 14px;\">
          <h3>${escapeHtml(list.title)}</h3>
          <ul>${(list.items || []).map((item) => `<li class=\"mono\">${escapeHtml(item)}</li>`).join('')}</ul>
        </div>`).join('') || '<p class=\"muted\">No additional highlights for this panel.</p>';
    }

    function renderFileTabs() {
      const agent = currentAgent();
      if (!state.activeFileName) {
        state.activeFileName = agent.files[0]?.name || null;
      }
      elements.fileTabRow.innerHTML = agent.files.map((file) => `
        <button class=\"file-tab${file.name === state.activeFileName ? ' active' : ''}\" data-file-name=\"${escapeHtml(file.name)}\">${escapeHtml(file.name)}</button>`).join('');
      const activeFile = agent.files.find((file) => file.name === state.activeFileName) || agent.files[0];
      elements.fileContent.textContent = activeFile?.content || 'No file output available.';
      elements.fileTabRow.querySelectorAll('[data-file-name]').forEach((button) => {
        button.addEventListener('click', () => {
          state.activeFileName = button.getAttribute('data-file-name');
          renderFileTabs();
        });
      });
    }

    function renderSelectionPanel() {
      const graph = currentGraph();
      if (!graph || !state.selectedNodeId) {
        elements.selectionPanel.innerHTML = `
          <div class=\"kv-item\"><strong>Status</strong><span>Select a node or use search to inspect graph metadata.</span></div>
          <div class=\"kv-item\"><strong>Tip</strong><span>Hydrologist marks initial sources with a green halo and sinks with a pink halo.</span></div>`;
        return;
      }

      const node = graph.nodes.find((entry) => entry.id === state.selectedNodeId);
      if (!node) {
        elements.selectionPanel.innerHTML = '<div class=\"kv-item\"><strong>Status</strong><span>Selected node not found.</span></div>';
        return;
      }

      const items = [
        ['Label', node.label],
        ['Node Type', node.nodeType],
        ['Degree', `${node.degree} (${node.inDegree} in / ${node.outDegree} out)`],
      ];
      if (node.storageType) items.push(['Storage Type', node.storageType]);
      if (node.domainCluster) items.push(['Domain Cluster', node.domainCluster]);
      for (const [key, value] of Object.entries(node.metadata || {})) {
        if (typeof value === 'object') {
          items.push([key, JSON.stringify(value, null, 2)]);
        } else {
          items.push([key, String(value)]);
        }
      }
      elements.selectionPanel.innerHTML = items.map(([label, value]) => `
        <div class=\"kv-item\">
          <strong>${escapeHtml(label)}</strong>
          <span class=\"mono\">${escapeHtml(value)}</span>
        </div>`).join('');
    }

    function renderLegend() {
      const agent = currentAgent();
      const graph = currentGraph();
      if (!graph) {
        elements.legend.innerHTML = '';
        return;
      }
      const byAgent = {
        surveyor: [
          ['square', 'Module'],
          ['double-circle', 'Function'],
          ['dot:#4f8cff', 'Dependency node'],
          ['dot:#7dd3fc', 'Selected / searched'],
        ],
        hydrologist: [
          ['circle', 'Dataset'],
          ['diamond', 'Transformation'],
          ['dot:#34d399', 'Initial source'],
          ['dot:#f472b6', 'Terminal sink'],
        ],
        semanticist: [
          ['circle', 'Module bubble'],
          ['dot:#a855f7', 'Cluster glow'],
          ['dot:#ffffff', 'Most connected'],
        ],
        navigator: [
          ['square', 'Module'],
          ['diamond', 'Transformation'],
          ['circle', 'Dataset'],
          ['dot:#06b6d4', 'Bridge highlight'],
        ],
      };
      const entries = byAgent[agent.graphStyle] || [];
      elements.legend.innerHTML = entries.map(([shape, label]) => renderLegendEntry(shape, label)).join('');
    }

    function renderLegendEntry(shape, label) {
      if (shape.startsWith('dot:')) {
        const color = shape.split(':')[1];
        return `<div class=\"legend-row\"><span class=\"legend-dot\" style=\"background:${color}\"></span><span>${label}</span></div>`;
      }
      if (shape === 'diamond') {
        return `<div class=\"legend-row\"><span class=\"legend-shape diamond\"><span></span></span><span>${label}</span></div>`;
      }
      return `<div class=\"legend-row\"><span class=\"legend-shape ${shape}\"></span><span>${label}</span></div>`;
    }

    function drawGraph() {
      const graph = currentGraph();
      const agent = currentAgent();
      const rect = canvas.getBoundingClientRect();
      context.clearRect(0, 0, rect.width, rect.height);
      if (!graph) return;

      context.save();
      context.translate(rect.width / 2 + state.offsetX, rect.height / 2 + state.offsetY);
      context.scale(state.scale, state.scale);

      const nodeMap = new Map(graph.nodes.map((node) => [node.id, node]));
      const highlighted = new Set(state.highlightedNodeIds);
      const highlightedEdges = new Set(state.highlightedEdgeKeys);

      drawBackdrop(agent, graph);

      context.lineWidth = 1;
      for (const edge of graph.edges) {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);
        if (!source || !target) continue;
        const edgeKey = `${edge.source}=>${edge.target}`;
        drawEdge(agent, source, target, highlightedEdges.has(edgeKey));
      }

      for (const node of graph.nodes) {
        const radius = node.nodeType === 'function' ? 5 : node.nodeType === 'transformation' ? 7 : 8;
        const effectiveRadius = getNodeRadius(node, radius);
        const isSelected = node.id === state.selectedNodeId;
        const isHighlighted = highlighted.has(node.id);

        if (node.isSource || node.isSink || node.isMostConnected) {
          context.beginPath();
          context.arc(node.x, node.y, effectiveRadius + (node.isMostConnected ? 10 : 7), 0, Math.PI * 2);
          context.fillStyle = node.isSource ? 'rgba(52, 211, 153, 0.12)' : node.isSink ? 'rgba(244, 114, 182, 0.12)' : 'rgba(79, 140, 255, 0.16)';
          context.fill();
        }

        drawNode(agent, node, radius, isSelected, isHighlighted);

        if (state.scale >= 0.52 || isSelected || isHighlighted || node.isMostConnected) {
          context.font = '12px Inter, sans-serif';
          context.fillStyle = '#dbeafe';
          context.fillText(node.shortLabel, node.x + effectiveRadius + 6, node.y + 4);
        }
      }
      context.restore();
    }

    function drawBackdrop(agent, graph) {
      if (agent.graphStyle === 'surveyor') {
        context.strokeStyle = 'rgba(79, 140, 255, 0.08)';
        context.lineWidth = 1;
        for (let radius = 120; radius <= 780; radius += 120) {
          context.beginPath();
          context.arc(0, 0, radius, 0, Math.PI * 2);
          context.stroke();
        }
      }

      if (agent.graphStyle === 'hydrologist') {
        const lanes = [
          { x: -340, label: 'Sources', color: 'rgba(52, 211, 153, 0.10)' },
          { x: 0, label: 'Transforms', color: 'rgba(255, 143, 61, 0.10)' },
          { x: 340, label: 'Sinks', color: 'rgba(244, 114, 182, 0.10)' },
        ];
        for (const lane of lanes) {
          context.fillStyle = lane.color;
          context.fillRect(lane.x - 140, -500, 280, 1000);
          context.fillStyle = 'rgba(229, 238, 252, 0.7)';
          context.font = '18px Inter, sans-serif';
          context.fillText(lane.label, lane.x - 46, -448);
        }
      }

      if (agent.graphStyle === 'semanticist') {
        const clusters = new Map();
        for (const node of graph.nodes) {
          const cluster = node.domainCluster || 'Unclustered';
          if (!clusters.has(cluster)) clusters.set(cluster, []);
          clusters.get(cluster).push(node);
        }
        const colors = ['rgba(168, 85, 247, 0.12)', 'rgba(59, 130, 246, 0.12)', 'rgba(34, 197, 94, 0.12)', 'rgba(236, 72, 153, 0.10)'];
        Array.from(clusters.entries()).forEach(([cluster, nodes], index) => {
          const center = nodes.reduce((acc, node) => ({ x: acc.x + node.x, y: acc.y + node.y }), { x: 0, y: 0 });
          center.x /= Math.max(nodes.length, 1);
          center.y /= Math.max(nodes.length, 1);
          const maxDistance = Math.max(...nodes.map((node) => Math.hypot(node.x - center.x, node.y - center.y)), 40);
          context.beginPath();
          context.arc(center.x, center.y, maxDistance + 58, 0, Math.PI * 2);
          context.fillStyle = colors[index % colors.length];
          context.fill();
          context.fillStyle = 'rgba(229, 238, 252, 0.78)';
          context.font = '16px Inter, sans-serif';
          context.fillText(cluster, center.x - 26, center.y - maxDistance - 28);
        });
      }

      if (agent.graphStyle === 'navigator') {
        context.strokeStyle = 'rgba(6, 182, 212, 0.08)';
        context.lineWidth = 1;
        for (let x = -720; x <= 720; x += 120) {
          context.beginPath();
          context.moveTo(x, -520);
          context.lineTo(x, 520);
          context.stroke();
        }
        for (let y = -520; y <= 520; y += 120) {
          context.beginPath();
          context.moveTo(-720, y);
          context.lineTo(720, y);
          context.stroke();
        }
      }
    }

    function drawEdge(agent, source, target, isHighlighted) {
      context.beginPath();
      const midX = (source.x + target.x) / 2;
      const midY = (source.y + target.y) / 2;
      const bend = Math.sign(target.x - source.x || 1) * Math.min(95, Math.abs(target.x - source.x) * 0.18 + Math.abs(target.y - source.y) * 0.05);
      context.moveTo(source.x, source.y);
      context.quadraticCurveTo(midX, midY - bend, target.x, target.y);
      if (agent.graphStyle === 'hydrologist') {
        context.strokeStyle = isHighlighted ? 'rgba(40, 92, 182, 0.88)' : 'rgba(60, 74, 96, 0.15)';
        context.lineWidth = isHighlighted ? 2.8 : 1.0;
      } else if (agent.graphStyle === 'semanticist') {
        context.strokeStyle = isHighlighted ? 'rgba(66, 99, 170, 0.86)' : 'rgba(75, 85, 99, 0.12)';
        context.lineWidth = isHighlighted ? 2.6 : 0.95;
      } else if (agent.graphStyle === 'navigator') {
        context.strokeStyle = isHighlighted ? 'rgba(40, 92, 182, 0.9)' : 'rgba(82, 94, 112, 0.14)';
        context.lineWidth = isHighlighted ? 2.8 : 1.05;
      } else {
        context.strokeStyle = isHighlighted ? 'rgba(34, 76, 163, 0.92)' : 'rgba(90, 103, 122, 0.16)';
        context.lineWidth = isHighlighted ? 3 : 1.05;
      }
      context.stroke();
    }

    function drawNode(agent, node, radius, isSelected, isHighlighted) {
      const fill = getNodePaint(node);
      const stroke = isSelected ? '#ffffff' : isHighlighted ? '#204ea9' : 'rgba(51, 65, 85, 0.55)';
      const lineWidth = isSelected ? 3 : isHighlighted ? 2 : 1;
      const effectiveRadius = getNodeRadius(node, radius);

      if (agent.graphStyle === 'surveyor' && node.nodeType === 'module') {
        const width = Math.max(48, Math.min(118, node.shortLabel.length * 6.5));
        const height = Math.max(22, effectiveRadius * 2.1);
        roundRect(context, node.x - width / 2, node.y - height / 2, width, height, 8);
        context.shadowColor = isHighlighted || isSelected ? 'rgba(33, 75, 164, 0.28)' : 'rgba(0,0,0,0.08)';
        context.shadowBlur = isHighlighted || isSelected ? 12 : 4;
        context.fillStyle = fill;
        context.fill();
        context.shadowBlur = 0;
        context.lineWidth = lineWidth;
        context.strokeStyle = stroke;
        context.stroke();
        return;
      }

      if (agent.graphStyle === 'surveyor' && node.nodeType === 'function') {
        const outerRadius = effectiveRadius + 4;
        const innerRadius = Math.max(4, effectiveRadius - 2);

        context.beginPath();
        context.arc(node.x, node.y, outerRadius, 0, Math.PI * 2);
        context.shadowColor = isHighlighted || isSelected ? 'rgba(33, 75, 164, 0.28)' : 'rgba(0,0,0,0.08)';
        context.shadowBlur = isHighlighted || isSelected ? 12 : 4;
        context.fillStyle = 'rgba(243, 246, 251, 0.18)';
        context.fill();
        context.shadowBlur = 0;
        context.lineWidth = lineWidth;
        context.strokeStyle = stroke;
        context.stroke();

        context.beginPath();
        context.arc(node.x, node.y, innerRadius, 0, Math.PI * 2);
        context.fillStyle = fill;
        context.fill();
        context.lineWidth = Math.max(1, lineWidth - 0.5);
        context.strokeStyle = stroke;
        context.stroke();
        return;
      }

      if (agent.graphStyle === 'hydrologist' && node.nodeType === 'transformation') {
        context.save();
        context.translate(node.x, node.y);
        context.rotate(Math.PI / 4);
        context.beginPath();
        context.rect(-effectiveRadius, -effectiveRadius, effectiveRadius * 2, effectiveRadius * 2);
        context.shadowColor = isHighlighted || isSelected ? 'rgba(33, 75, 164, 0.28)' : 'rgba(0,0,0,0.08)';
        context.shadowBlur = isHighlighted || isSelected ? 12 : 4;
        context.fillStyle = fill;
        context.fill();
        context.shadowBlur = 0;
        context.lineWidth = lineWidth;
        context.strokeStyle = stroke;
        context.stroke();
        context.restore();
        return;
      }

      if (agent.graphStyle === 'semanticist') {
        context.beginPath();
        context.arc(node.x, node.y, effectiveRadius + (node.isMostConnected ? 8 : 4), 0, Math.PI * 2);
        context.fillStyle = node.isMostConnected ? 'rgba(255,255,255,0.18)' : 'rgba(88, 107, 160, 0.08)';
        context.fill();
      }

      context.beginPath();
      context.arc(node.x, node.y, isSelected ? effectiveRadius + 3 : effectiveRadius, 0, Math.PI * 2);
      context.shadowColor = isHighlighted || isSelected ? 'rgba(32, 78, 169, 0.26)' : 'rgba(0,0,0,0.08)';
      context.shadowBlur = isHighlighted || isSelected ? 14 : 4;
      context.fillStyle = fill;
      context.fill();
      context.shadowBlur = 0;
      context.lineWidth = lineWidth;
      context.strokeStyle = stroke;
      context.stroke();
    }

    function getNodeRadius(node, fallbackRadius) {
      const degree = Math.max(node.degree || 0, 0);
      const degreeBoost = Math.pow(degree, 0.58) * 2.35;
      const prominenceBoost = node.isMostConnected ? 8 : degree >= 12 ? 3.5 : 0;
      return Math.max(fallbackRadius + 1, Math.min(38, fallbackRadius + degreeBoost + prominenceBoost));
    }

    function getNodePaint(node) {
      if (node.nodeType === 'function') return 'rgba(214, 159, 121, 0.95)';
      if (node.nodeType === 'transformation') return 'rgba(219, 171, 129, 0.95)';
      if (node.nodeType === 'dataset') return 'rgba(102, 133, 179, 0.96)';
      return 'rgba(96, 127, 174, 0.96)';
    }

    function roundRect(ctx, x, y, width, height, radius) {
      ctx.beginPath();
      ctx.moveTo(x + radius, y);
      ctx.lineTo(x + width - radius, y);
      ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
      ctx.lineTo(x + width, y + height - radius);
      ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
      ctx.lineTo(x + radius, y + height);
      ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
      ctx.lineTo(x, y + radius);
      ctx.quadraticCurveTo(x, y, x + radius, y);
      ctx.closePath();
    }

    function findNodeAt(clientX, clientY) {
      const agent = currentAgent();
      const graph = currentGraph();
      if (!graph) return null;
      const rect = canvas.getBoundingClientRect();
      const x = (clientX - rect.left - rect.width / 2 - state.offsetX) / state.scale;
      const y = (clientY - rect.top - rect.height / 2 - state.offsetY) / state.scale;
      for (const node of graph.nodes) {
        const fallbackRadius = node.nodeType === 'function' ? 5 : node.nodeType === 'transformation' ? 7 : 8;
        const radius = getNodeRadius(node, fallbackRadius);
        if (agent.graphStyle === 'surveyor' && node.nodeType === 'module') {
          const width = Math.max(48, Math.min(118, node.shortLabel.length * 6.5));
          const height = Math.max(22, radius * 2.1);
          if (x >= node.x - width / 2 - 4 && x <= node.x + width / 2 + 4 && y >= node.y - height / 2 - 4 && y <= node.y + height / 2 + 4) {
            return node;
          }
          continue;
        }
        if (agent.graphStyle === 'surveyor' && node.nodeType === 'function') {
          if (Math.hypot(node.x - x, node.y - y) <= radius + 10) {
            return node;
          }
          continue;
        }
        if (agent.graphStyle === 'hydrologist' && node.nodeType === 'transformation') {
          const dx = Math.abs(x - node.x);
          const dy = Math.abs(y - node.y);
          if (dx + dy <= radius + 5) {
            return node;
          }
          continue;
        }
        if (Math.hypot(node.x - x, node.y - y) <= radius + 6) {
          return node;
        }
      }
      return null;
    }

    function centerOnNode(node) {
      const rect = canvas.getBoundingClientRect();
      state.offsetX = -node.x * state.scale;
      state.offsetY = -node.y * state.scale;
    }

    function buildSelectionHighlights(graph, nodeId) {
      const nodeIds = new Set([nodeId]);
      const edgeKeys = [];
      for (const edge of graph.edges) {
        if (edge.source === nodeId || edge.target === nodeId) {
          edgeKeys.push(`${edge.source}=>${edge.target}`);
          nodeIds.add(edge.source);
          nodeIds.add(edge.target);
        }
      }
      return {
        nodeIds: Array.from(nodeIds),
        edgeKeys,
      };
    }

    function runSearch() {
      const graph = currentGraph();
      const query = elements.searchInput.value.trim().toLowerCase();
      if (!graph || !query) {
        state.selectedNodeId = null;
        state.highlightedNodeIds = [];
        state.highlightedEdgeKeys = [];
        drawGraph();
        return;
      }
      const matches = graph.nodes.filter((node) => {
        const haystack = `${node.label} ${node.nodeType} ${node.storageType || ''} ${node.domainCluster || ''}`.toLowerCase();
        return haystack.includes(query);
      });
      if (matches[0]) {
        state.selectedNodeId = matches[0].id;
        const selection = buildSelectionHighlights(graph, matches[0].id);
        state.highlightedNodeIds = selection.nodeIds;
        state.highlightedEdgeKeys = selection.edgeKeys;
      } else {
        state.selectedNodeId = null;
        state.highlightedNodeIds = [];
        state.highlightedEdgeKeys = [];
      }
      renderSelectionPanel();
      drawGraph();
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function render() {
      applyTheme();
      renderSidebar();
      renderStats();
      renderSummary();
      renderFileTabs();
      renderSelectionPanel();
      renderLegend();
      drawGraph();
    }

    window.addEventListener('resize', resizeCanvas);
    canvas.addEventListener('mousedown', (event) => {
      state.dragging = true;
      state.isPanning = false;
      state.pointerDownX = event.clientX;
      state.pointerDownY = event.clientY;
      state.dragStartX = event.clientX - state.offsetX;
      state.dragStartY = event.clientY - state.offsetY;
    });
    window.addEventListener('mouseup', () => {
      state.dragging = false;
      state.isPanning = false;
    });
    window.addEventListener('mousemove', (event) => {
      if (!state.dragging) return;
      const distance = Math.hypot(event.clientX - state.pointerDownX, event.clientY - state.pointerDownY);
      if (!state.isPanning && distance < 6) return;
      state.isPanning = true;
      state.offsetX = event.clientX - state.dragStartX;
      state.offsetY = event.clientY - state.dragStartY;
      drawGraph();
    });
    canvas.addEventListener('click', (event) => {
      if (state.isPanning) return;
      const node = findNodeAt(event.clientX, event.clientY);
      state.selectedNodeId = node?.id || null;
      if (node) {
        const selection = buildSelectionHighlights(currentGraph(), node.id);
        state.highlightedNodeIds = selection.nodeIds;
        state.highlightedEdgeKeys = selection.edgeKeys;
      } else {
        state.highlightedNodeIds = [];
        state.highlightedEdgeKeys = [];
      }
      renderSelectionPanel();
      drawGraph();
    });
    canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      const delta = event.deltaY < 0 ? 1.12 : 0.88;
      state.scale = Math.max(0.18, Math.min(3.2, state.scale * delta));
      drawGraph();
    }, { passive: false });
    document.getElementById('search-button').addEventListener('click', runSearch);
    elements.searchInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') runSearch();
    });
    document.querySelectorAll('[data-zoom]').forEach((button) => {
      button.addEventListener('click', () => {
        const mode = button.getAttribute('data-zoom');
        if (mode === 'in') state.scale = Math.min(3.2, state.scale * 1.15);
        if (mode === 'out') state.scale = Math.max(0.18, state.scale * 0.87);
        if (mode === 'reset') {
          resetViewport();
        }
        drawGraph();
      });
    });

    state.activeFileName = currentAgent()?.files[0]?.name || null;
    render();
    resizeCanvas();
    resetViewport();
    drawGraph();
  </script>
</body>
</html>
"""


__all__ = ["generate_dashboard", "resolve_artifact_directory"]