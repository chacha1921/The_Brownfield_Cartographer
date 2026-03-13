from analyzers.tree_sitter_analyzer import analyze_module
from agents.surveyor import SurveyorAgent

module = analyze_module('src/agents/surveyor.py')
print('module_imports', module.imports[:3])
print('module_functions', module.public_functions[:5])
print('module_classes', [item.model_dump() for item in module.class_definitions])

agent = SurveyorAgent('.')
velocity = agent.extract_git_velocity('.', days=30)
print('velocity_entries', len(velocity))
print('velocity_sample', list(sorted(velocity.items()))[:5])

graph = agent.build_import_graph()
pagerank = agent.calculate_pagerank()
sccs = agent.identify_strongly_connected_components()
print('graph_nodes', graph.graph.number_of_nodes())
print('graph_edges', graph.graph.number_of_edges())
print('graph_metadata_keys', sorted(graph.graph.graph.keys()))
print('hub_sample', graph.graph.graph['architectural_hubs'][:5])
print('sccs', sccs)
print('high_velocity_core', graph.graph.graph['high_velocity_core'])
print('pagerank_sample', list(sorted(pagerank.items(), key=lambda item: item[1], reverse=True))[:5])
