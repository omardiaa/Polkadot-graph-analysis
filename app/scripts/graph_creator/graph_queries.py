import networkx as nx
import pdb
import os

# Get the directory of the current script
script_dir = os.path.dirname(__file__)
# Construct the relative path to the graph file
# graph_file_path = os.path.join(script_dir, '../../../exported_graph/merged_0.gpickle')
# graph_file_path = os.path.join(script_dir, '../../../exported_graph/20000000_21999999.gpickle')

exported_graph_dir = os.path.join(script_dir, '../../../exported_graph/')
graph_files = [f for f in os.listdir(exported_graph_dir) if f.startswith('updated_graph_') and f.endswith('.gpickle')]
if graph_files:
    max_version = max([int(f.split('_')[-1].split('.')[0]) for f in graph_files])
else:
    max_version = 0
graph_file_path = os.path.join(exported_graph_dir, f"updated_graph_{max_version}.gpickle")

print("Reading graph from file:", graph_file_path)
# Read the graph from the file
try:
    graph = nx.read_gpickle(graph_file_path)
except FileNotFoundError:
    print(f"Error: The file {graph_file_path} was not found.")
    exit(1)
except nx.NetworkXError as e:
    print(f"Error reading the graph: {e}")
    exit(1)

# Process the graph (you can add your processing code here)
# For now, we will just print the number of nodes and edges
num_nodes = graph.number_of_nodes()
num_edges = graph.number_of_edges()

print(f"Number of nodes: {num_nodes}")
print(f"Number of edges: {num_edges}")

# Add a pdb breakpoint
pdb.set_trace()