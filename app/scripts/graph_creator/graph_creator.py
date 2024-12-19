import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

import networkx as nx
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, scoped_session

from ..models.data import Transaction, Event, ProxyAccount, MultisigMemberAccount, ProxyExtrinsicRealAddress
from timeit import default_timer as timer
import pytz
from datetime import datetime
import os
from scalecodec.utils.ss58 import ss58_encode

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
                fee=float(transaction.fee) if transaction.nesting_idx == 0 else 0.0
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
    start_block = 0
    end_block = start_block + batch_size
    last_block = 23_098_211
    last_iteration = False

    while not last_iteration:
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
        if end_block == last_block:
            last_iteration = True
        elif end_block + batch_size > last_block:
            end_block = last_block
        else:
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

def correct_balance(block_id, balance):
    if not isinstance(balance, int):
        raise ValueError(f"Balance is not an integer for block_id {block_id}")
    if block_id >= 1_248_328:
        token_decimals = 10
    else:
        token_decimals = 12
    return balance / 10 ** token_decimals

def parse_staking_rewards(graph, batch_size):
    start_block = 0
    end_block = start_block + batch_size
    last_block = 23_098_211
    last_iteration = False

    while not last_iteration:
        logger.info("Processing next batch...")
        events = (
            db_session.query(Event)
            .filter(
                Event.module_id == "Staking",
                Event.event_id.in_(["Rewarded", "Reward"]),
                Event.block_id >= start_block,
                Event.block_id < end_block
            )
            .all()
        )

        logger.info(f"Events count: {len(events)} between blocks {start_block} and {end_block}")

        for event in events:
            normalized_event = normalize_event(event.attributes)
            normalized_event['amount'] = correct_balance(event.block_id, normalized_event['amount'])

            graph.add_edge(
                "StakingRewardSystem",
                normalized_event['address'],
                weight=normalized_event['amount'],
                date=event.block_id
            )

        logger.info(f"Graph updated with events from blocks {start_block} to {end_block - 1}")

        start_block = end_block
        if end_block == last_block:
            last_iteration = True
        elif end_block + batch_size > last_block:
            end_block = last_block
        else:
            end_block += batch_size

        save_updated_graph(graph)
    
    return graph

def normalize_event(data):
    """
    Normalize different reward event formats into {"address": ..., "amount": ...}
    Handles various input structures and prioritizes the 'Account' field over 'stash' if both exist.
    """
    result = {"address": None, "amount": None}

    try:
        # Case 1: List format [{"type": "AccountId", ...}, {"type": "Balance", ...}]
        if isinstance(data, list) and isinstance(data[0], dict):
            for item in data:
                if item.get("type") == "AccountId":
                    result["address"] = item.get("value")
                elif item.get("type") == "Balance" or item.get("type_name") == "BalanceOf":
                    result["amount"] = int(item.get("value"))
                elif item.get("type_name") == "AccountId":
                    result["address"] = ss58_encode(item.get("value").replace('0x', ''), 0)
                    

        # Case 2: Dictionary format with 'stash' and 'amount'
        elif isinstance(data, dict):
            # Handle 'dest' with 'Account' prioritization
            if isinstance(data.get("dest"), dict) and "Account" in data["dest"]:
                result["address"] = data["dest"]["Account"]
            # Fallback to 'stash' if no 'Account'
            elif "stash" in data:
                result["address"] = data["stash"]
            elif "who" in data:
                result["address"] = data["who"]

            # Extract amount if it exists
            if "amount" in data:
                result["amount"] = data["amount"]

        # Case 3: Tuple-like list format ["address", amount]
        elif isinstance(data, list) and len(data) == 2:
            result["address"] = data[0]
            result["amount"] = data[1]

        elif isinstance(data, list) and len(data) == 3:
            result["address"] = data[0]
            result["amount"] = data[2]
        # Handle invalid address formats
        if not result["address"]:
            raise ValueError("Address is missing or invalid in the input data.")

        return result

    except Exception as e:
        print(f"Error processing event: {e}")
        return result

def parse_claim_attests(graph, batch_size):
    start_block = 0
    end_block = start_block + batch_size
    last_block = 23_098_211
    last_iteration = False

    while not last_iteration:
        logger.info("Processing next batch for claim attests...")
        events = (
            db_session.query(Event)
            .filter(
                Event.module_id == "Claims",
                Event.event_id == "Claimed",
                Event.block_id >= start_block,
                Event.block_id < end_block
            )
            .all()
        )

        logger.info(f"Events count: {len(events)} between blocks {start_block} and {end_block}")

        for event in events:
            normalized_event = normalize_event(event.attributes)
            graph.add_edge(
                "ClaimAttestsSystem",
                normalized_event['address'],
                weight=correct_balance(event.block_id, normalized_event['amount']),
                date=event.block_id
            )

        logger.info(f"Graph updated with claim attests from blocks {start_block} to {end_block - 1}")

        start_block = end_block
        if end_block == last_block:
            last_iteration = True
        elif end_block + batch_size > last_block:
            end_block = last_block
        else:
            end_block += batch_size

        save_updated_graph(graph)

def parse_system_to_user_transactions(graph, batch_size):
    updated_graph = parse_staking_rewards(graph, batch_size)
    # graph_file_name = get_max_version_file_name()
    # updated_graph = nx.read_gpickle(graph_file_name)
    parse_claim_attests(updated_graph, batch_size)
    
def get_max_version_file_name(plus_one=False):
    max_version = max([int(f.split('_')[-1].split('.')[0]) for f in os.listdir(graph_folder) if f.startswith('updated_graph_') and f.endswith('.gpickle')], default=0)
    if plus_one:
        max_version += 1
    file_name = f"{graph_folder}/updated_graph_{max_version}.gpickle"
    return file_name

def save_updated_graph(graph):
    file_name = get_max_version_file_name(plus_one=True)
    nx.write_gpickle(graph, file_name)
    logger.info(f"New graph saved: {file_name}")

if __name__ == '__main__':
    try:
        start = timer()

        batch_size = 1_000_000
        final_graph_file = '../../../exported_graph/merged_0.gpickle'

        # Phase 1: Process graph without staking rewards
        logger.info(f"Processing transactions in batches of {batch_size}...")
        multisig_accounts = process_multisig_accounts()
        proxy_accounts = process_proxy_accounts()
        process_batches(batch_size)

        graph_files = [f for f in os.listdir(graph_folder) if f.endswith('.gpickle')]

        logger.info("Graph Files: ", graph_files)
        final_graph_file = merge_graphs(graph_files)

        logger.info(f"Final merged graph saved as {final_graph_file}")
        logger.info(f"Total Execution Time (seconds): {timer() - start}")

        # Phase 2: Parse staking rewards and Claims.attest
        script_dir = os.path.dirname(__file__)
        graph_file_path = os.path.join(script_dir, final_graph_file)
        graph = nx.read_gpickle(graph_file_path)
        
        parse_system_to_user_transactions(graph, batch_size)
        
    except Exception:
        db_session.remove()
        logger.error(traceback.format_exc())
