# %%
import networkx as nx

# %%
import matplotlib.pyplot as plt

# %%
digraph = nx.read_gpickle('../../../exported_graph/updated_graph_26.gpickle')
print("Graph Reading COMPLETED...")

# %%
# print("Number of self-loops: {}".format(nx.number_of_selfloops(digraph)))
# print("Number of Nodes: {}".format(nx.number_of_nodes(digraph)))
print('Number of edges: {}'.format(nx.number_of_edges(digraph)))

# %% [markdown]
# Connectivity: connectivity is one of the basic concepts of graph theory: it asks for the minimum number of elements (nodes or edges) that need to be removed to separate the remaining nodes into two or more isolated subgraphs

# %%
print("Is Strongly Connected? {}".format(nx.is_strongly_connected(digraph)))

# %%
# print("Is Weakly Connected? {}".format(nx.is_weakly_connected(digraph)))

# %%
print('\tAssortativity: {}'.format(nx.degree_assortativity_coefficient(digraph)))
print('\tPearson: {}'.format(nx.degree_pearson_correlation_coefficient(digraph)))
print('\t#SCC: {}'.format(nx.number_strongly_connected_components(digraph)))
# print('\t#WCC: {}'.format(nx.number_weakly_connected_components(digraph)))

# %%
print("Average Degree Connectivity: {}".format(nx.average_degree_connectivity(digraph)))

# %%
# print("Graph Clique Number: {}".format(nx.graph_clique_number(digraph.to_undirected())))

# %%
number_of_nodes = [len(n) for n in sorted(nx.strongly_connected_components(digraph))]
print("Number of SCC: {}".format(len(number_of_nodes)))
