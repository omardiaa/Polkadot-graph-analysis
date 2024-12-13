import unittest
import networkx as nx
import os
from unittest.mock import MagicMock, patch
from app.scripts.graph_creator.graph_creator import create_graph, process_batches, merge_graphs, db_session, Transaction

class TestGraphCreator(unittest.TestCase):

    def setUp(self):
        # Mock database session
        self.mock_db_session = patch('app.scripts.graph_creator.graph_creator.db_session').start()
        self.mock_query = self.mock_db_session.query.return_value

        # Sample transactions for testing
        self.sample_transactions = [
            Transaction(
                from_address='A', to_address='B', value=10, fee=0.1,
                timestamp='2024-12-11', block_id=1, call_id='transfer', signed=1, success=1
            ),
            Transaction(
                from_address='B', to_address='C', value=20, fee=0.2,
                timestamp='2024-12-12', block_id=2, call_id='transfer', signed=1, success=1
            )
        ]

    def test_print_graph(self):
        graph = create_graph(self.sample_transactions)

        # Print nodes
        print("Nodes:")
        print(graph.nodes(data=True))

        # Print edges
        print("\nEdges:")
        print(graph.edges(data=True))

    def tearDown(self):
        patch.stopall()

    def test_create_graph(self):
        graph = create_graph(self.sample_transactions)
        self.assertEqual(graph.number_of_nodes(), 3)
        self.assertEqual(graph.number_of_edges(), 2)
        self.assertTrue(graph.has_edge('A', 'B'))
        self.assertTrue(graph.has_edge('B', 'C'))
    
    def test_process_batches(self):
        # Mock database query behavior for this test
        responses = [
            MagicMock(all=MagicMock(return_value=self.sample_transactions[:1])),  # First transaction
            MagicMock(all=MagicMock(return_value=self.sample_transactions[1:])),  # Second transaction
            MagicMock(all=MagicMock(return_value=[]))  # Empty list
        ]

        def filter_side_effect(*args, **kwargs):
            # Simulate sequential responses: first call returns first transaction, second call returns second, then empty
            return responses.pop(0) if responses else MagicMock(all=MagicMock(return_value=[]))

        self.mock_query.filter.side_effect = filter_side_effect

        # Expected graphs for batches
        expected_graphs = [
            nx.MultiDiGraph([('A', 'B', {'weight': 10.0, 'date': '2024-12-11', 'fee': 0.1})]),
            nx.MultiDiGraph([('B', 'C', {'weight': 20.0, 'date': '2024-12-12', 'fee': 0.2})])
        ]

        # Mock file writing
        with patch('networkx.write_gpickle') as mock_write_gpickle:
            process_batches(batch_size=1)

            # Check if graph is saved
            mock_write_gpickle.assert_called()
            self.assertEqual(mock_write_gpickle.call_count, 2)

            # Validate the content of each saved graph
            for call, expected_graph in zip(mock_write_gpickle.call_args_list, expected_graphs):
                saved_graph = call[0][0]  # Get the graph passed to write_gpickle
                self.assertTrue(nx.is_isomorphic(saved_graph, expected_graph))
                self.assertEqual(sorted(saved_graph.edges(data=True)), sorted(expected_graph.edges(data=True)))
                self.assertEqual(sorted(saved_graph.nodes(data=True)), sorted(expected_graph.nodes(data=True)))
    

    def test_merge_graphs_with_5_files(self):
        # Mock graph files
        graph_files = ['graph1.gpickle', 'graph2.gpickle', 'graph3.gpickle', 'graph4.gpickle', 'graph5.gpickle']

        # Create dummy graphs for merging
        g1 = nx.MultiDiGraph()
        g1.add_edge('A', 'B', weight=1)

        g2 = nx.MultiDiGraph()
        g2.add_edge('C', 'D', weight=2)

        g3 = nx.MultiDiGraph()
        g3.add_edge('E', 'F', weight=3)

        g4 = nx.MultiDiGraph()
        g4.add_edge('G', 'H', weight=4)

        g5 = nx.MultiDiGraph()
        g5.add_edge('I', 'J', weight=5)

        # Simulate the intermediate merged graphs
        merged_g1_g2 = nx.compose(g1, g2)
        merged_g3_g4 = nx.compose(g3, g4)
        merged_final = nx.compose(merged_g1_g2, merged_g3_g4)
        merged_final.add_edges_from(g5.edges(data=True))

        # Expected merged graph
        expected_merged_graph = nx.MultiDiGraph()
        expected_merged_graph.add_edge('A', 'B', weight=1)
        expected_merged_graph.add_edge('C', 'D', weight=2)
        expected_merged_graph.add_edge('E', 'F', weight=3)
        expected_merged_graph.add_edge('G', 'H', weight=4)
        expected_merged_graph.add_edge('I', 'J', weight=5)

        # Mock file operations
        with patch('networkx.read_gpickle', side_effect=[g1, g2, g3, g4, g5, merged_g1_g2, merged_g3_g4, merged_final]), \
             patch('networkx.write_gpickle') as mock_write_gpickle, \
             patch('os.remove') as mock_remove:

            merged_file = merge_graphs(graph_files)

            # Verify the merged graph was written correctly
            mock_write_gpickle.assert_called()

            # Get the graph passed to write_gpickle in the final call
            merged_graph = mock_write_gpickle.call_args[0][0]
            
            # Assert the merged graph is as expected
            self.assertTrue(nx.is_isomorphic(merged_graph, expected_merged_graph))
            self.assertEqual(sorted(merged_graph.edges(data=True)), sorted(expected_merged_graph.edges(data=True)))
            self.assertEqual(sorted(merged_graph.nodes(data=True)), sorted(expected_merged_graph.nodes(data=True)))

            self.assertEqual(merged_file, 'merged_0.gpickle')

    def test_empty_batches(self):
        # Mock empty query result
        self.mock_query.filter.return_value.limit.return_value.offset.return_value.all.return_value = []

        with patch('networkx.write_gpickle') as mock_write_gpickle:
            process_batches(batch_size=1)
            mock_write_gpickle.assert_not_called()

if __name__ == '__main__':
    unittest.main()
