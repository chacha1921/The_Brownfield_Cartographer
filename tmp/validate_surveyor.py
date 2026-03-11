from agents.surveyor import SurveyorAgent

agent = SurveyorAgent('.')
velocity = agent.extract_git_velocity()
graph = agent.build_import_graph()
pagerank = agent.calculate_pagerank()

print('velocity_count', len(velocity))
print('velocity_sample', sorted(list(velocity.items()))[:5])
print('graph_nodes', graph.graph.number_of_nodes())
print('graph_edges', graph.graph.number_of_edges())
print('pagerank_top', sorted(pagerank.items(), key=lambda item: item[1], reverse=True)[:5])
