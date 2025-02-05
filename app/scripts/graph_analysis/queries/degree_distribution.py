import json
from collections import Counter
import os
import networkx as nx
import pdb
from collections import defaultdict
from datetime import datetime, timedelta
import calendar

# Get the directory of the current script
script_dir = os.path.dirname(__file__)
# Construct the relative path to the graph file
graph_file_path = os.path.join(script_dir, '../../../../exported_graph/updated_graph_26.gpickle')
# Read the graph from the file

try:
    graph = nx.read_gpickle(graph_file_path)
except FileNotFoundError:
    print(f"Error: The file {graph_file_path} was not found.")
    exit(1)
except nx.NetworkXError as e:
    print(f"Error reading the graph: {e}")
    exit(1)
# Compute in-degree distribution
in_degree_counts = Counter(dict(graph.in_degree()).values())

# Compute out-degree distribution
out_degree_counts = Counter(dict(graph.out_degree()).values())

# Sort dictionaries by degree (keys)
sorted_in_degree_counts = dict(sorted(in_degree_counts.items()))
sorted_out_degree_counts = dict(sorted(out_degree_counts.items()))
import pdb; pdb.set_trace();
# Combine results
degree_distribution = {
    "in_degree_counts": sorted_in_degree_counts,
    "out_degree_counts": sorted_out_degree_counts
}

# Write to file
with open("degree_distribution.json", "w") as f:
    json.dump(degree_distribution, f, indent=4)

print("Degree distribution saved successfully!")