import networkx as nx
graph = nx.read_gpickle("./validators_and_nominators_graph.gpickle")
import pdb; pdb.set_trace()
num_nominators = sum(1 for node, data in graph.nodes(data=True) if data.get("role") == "nominator")
num_validators = sum(1 for node, data in graph.nodes(data=True) if data.get("role") == "validator")
