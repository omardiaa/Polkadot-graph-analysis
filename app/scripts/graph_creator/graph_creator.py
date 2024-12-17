import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

import networkx as nx
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, scoped_session

from ..models.data import Transaction, ProxyAccount, MultisigMemberAccount, ProxyExtrinsicRealAddress
from timeit import default_timer as timer
import pytz
from datetime import datetime
import os

# Configure logger
filename = "graph.log"
graph_folder = "exported_graph"
multisig_accounts = {}
proxy_accounts = {}

logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()

DB_CONNECTION = "mysql+mysqlconnector://crilab_db_admin:CRI%40admin24%21@10.70.43.249:3306/polkadot_analysis"

engine = create_engine(DB_CONNECTION, echo=False, isolation_level="READ_UNCOMMITTED", pool_pre_ping=True)
session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
db_session = scoped_session(session_factory)

def print_graph_statistics(graph, description):
    """
    Print basic statistics for the given graph.
    """
    logger.info(f"Statistics for {description}:")
    logger.info(f"  Number of nodes: {graph.number_of_nodes()}")
    logger.info(f"  Number of edges: {graph.number_of_edges()}")
    logger.info("")

def process_multisig_accounts():
     # Query to group by multisig_account_address and concatenate addresses
    results = (
        db_session.query(
            MultisigMemberAccount.multisig_account_address,
            func.group_concat(MultisigMemberAccount.address.op('ORDER BY')(MultisigMemberAccount.address), ',').label('concatenated_addresses')
        )
        .group_by(MultisigMemberAccount.multisig_account_address)
        .all()
    )

    # Create a dictionary with multisig_account_address as the key and concatenated addresses as the value
    multisig_dict = {
        result.multisig_account_address: result.concatenated_addresses for result in results
    }
    return multisig_dict

def process_proxy_accounts():
    results = (
        db_session.query(ProxyAccount).all()
    )

    proxy_dict = {}
    for result in results:
        if result.proxied_account_address not in proxy_dict:
            proxy_dict[result.proxied_account_address] = []
        # This is proxy account address not proxied account address. This is wrong. The value is reversed in the original code.
        # TODO: Update value to be proxy_dict[result.address] instead after fixing the original code
        proxy_dict[result.proxied_account_address].append(result.address)

    return proxy_dict

def create_graph(transactions):
    di_graph = nx.MultiDiGraph()
    for transaction, real_address in transactions:
        try:
            date = transaction.timestamp
            from_address = transaction.from_address
            if real_address:
                from_address = real_address

            di_graph.add_edge(
                from_address,
                transaction.to_address,
                weight=float(transaction.value),
                date=date,
                fee=float(transaction.fee)
            )
            
            # We are not concerned with row.from_address because it could be a proxy account. 
            # We are only concerned with the actual account that is being proxied. If it is a multisig account, we will get the multisig member accounts.
            
            multisig_member_accounts = []
            if multisig_accounts.get(from_address):
                multisig_member_accounts = multisig_accounts[from_address].split(',')

            di_graph.nodes[from_address]["multisig_member_accounts"] = multisig_member_accounts
            
        except Exception:
            logger.error("Error at transaction id {}-{}".format(transaction.block_id, transaction.extrinsic_idx))
    return di_graph

def process_batches(batch_size):
    start_block = 2_000_000
    end_block = start_block + batch_size

    while True:
        if end_block > 5_000_000:
            break

        transactions = db_session.query(Transaction, ProxyExtrinsicRealAddress.real_address).outerjoin(
            ProxyExtrinsicRealAddress,
            (Transaction.block_id == ProxyExtrinsicRealAddress.block_id) &
            (Transaction.extrinsic_idx == ProxyExtrinsicRealAddress.extrinsic_idx) &
            (Transaction.nesting_idx == ProxyExtrinsicRealAddress.nesting_idx) &
            (Transaction.batch_idx == ProxyExtrinsicRealAddress.batch_idx) &
            (Transaction.unique_sequence == ProxyExtrinsicRealAddress.unique_sequence)
        ).filter(
            Transaction.signed == 1,
            Transaction.success == 1,
            Transaction.module_id == 'Balances',
            Transaction.call_id.in_([
                'transfer',
                'transfer_keep_alive',
                'transfer_all',
                'transfer_allow_death'
            ]),
            Transaction.to_address.is_not(None),
            Transaction.from_address.is_not(None),
            Transaction.from_address != Transaction.to_address,
            Transaction.value > 0,
            Transaction.block_id >= start_block,
            Transaction.block_id < end_block
        ).all()

        logger.info(f"Transactions count: {len(transactions)} between blocks {start_block} and {end_block}")

        created_graph = create_graph(transactions)
        logger.info(f"Graph created with {created_graph.number_of_nodes()} nodes and {created_graph.number_of_edges()} edges")
        file_name = f"{graph_folder}/{start_block}_{end_block - 1}.gpickle"
        nx.write_gpickle(created_graph, file_name)

        logger.info(f"Batch {start_block}-{end_block - 1} saved: {file_name}")

        start_block = end_block
        end_block += batch_size

def merge_graphs(graph_files):
    logger.info("Merging graphs...")
    while len(graph_files) > 1:
        merged_files = []

        for i in range(0, len(graph_files), 2):
            if i + 1 < len(graph_files):
                graph1 = nx.read_gpickle(f"{graph_folder}/{graph_files[i]}")
                graph2 = nx.read_gpickle(f"{graph_folder}/{graph_files[i + 1]}")

                print_graph_statistics(graph1, graph_files[i])
                print_graph_statistics(graph2, graph_files[i + 1])

                merged_graph = nx.MultiDiGraph()
                merged_graph.update(graph1)
                merged_graph.update(graph2)

                # Deduplicate edges
                for u, v, key, data in graph2.edges(data=True, keys=True):
                    if not merged_graph.has_edge(u, v, key):
                        merged_graph.add_edge(u, v, key=key, **data)

                print_graph_statistics(merged_graph, f"Merged Graph {graph_files[i]} + {graph_files[i+1]}")

                merged_file = f"merged_{i//2}.gpickle"
                nx.write_gpickle(merged_graph, f"{graph_folder}/{merged_file}")
                merged_files.append(merged_file)

                logger.info(f"Merged {graph_files[i]} and {graph_files[i + 1]} into {merged_file}")
            else:
                merged_files.append(graph_files[i])

        graph_files = merged_files

    return graph_files[0] if graph_files else None

if __name__ == '__main__':
    try:
        start = timer()

        batch_size = 1_000_000

        logger.info(f"Processing transactions in batches of {batch_size}...")
        multisig_accounts = process_multisig_accounts()
        proxy_accounts = process_proxy_accounts()
        process_batches(batch_size)

        graph_files = [f for f in os.listdir(graph_folder) if f.endswith('.gpickle')]

        logger.info("Graph Files: ", graph_files)
        final_graph_file = merge_graphs(graph_files)

        logger.info(f"Final merged graph saved as {final_graph_file}")
        logger.info(f"Total Execution Time (seconds): {timer() - start}")

    except Exception:
        db_session.remove()
        logger.error(traceback.format_exc())
