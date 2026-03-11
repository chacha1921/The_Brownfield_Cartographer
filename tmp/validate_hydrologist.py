from agents.hydrologist import HydrologistAgent

agent = HydrologistAgent('tmp/hydrologist_repo')
graph = agent.build_lineage_graph()

print('nodes', sorted(graph.graph.nodes()))
print('edges', sorted(graph.graph.edges(data=True)))
print('blast_radius_raw_orders', agent.blast_radius('raw.orders'))
print('source_nodes', sorted(agent.find_source_nodes()))
print('sink_nodes', sorted(agent.find_sink_nodes()))
