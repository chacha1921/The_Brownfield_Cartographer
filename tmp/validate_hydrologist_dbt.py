from agents.hydrologist import HydrologistAgent

agent = HydrologistAgent('tmp/hydrologist_dbt_repo')
graph = agent.build_lineage_graph()

print('nodes', sorted(graph.graph.nodes()))
print('edges', sorted(graph.graph.edges(data=True)))
print('blast_radius', agent.blast_radius('raw.orders'))
print('find_sources', sorted(agent.find_sources()))
print('find_sinks', sorted(agent.find_sinks()))
