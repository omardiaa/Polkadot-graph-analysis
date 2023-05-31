import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

import networkx as nx

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from models.data import Transaction
from timeit import default_timer as timer
import pytz

from datetime import datetime
from dateutil.rrule import rrule, MONTHLY

# create and configure logger
filename = "graph.log"
logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()

DB_NAME = "polkadot_analysis"
DB_HOST = "localhost"
DB_PORT = 3306
DB_USERNAME = "root"
DB_PASSWORD = "root"
DEBUG = False

DB_CONNECTION = "mysql+mysqlconnector://{}:{}@{}:{}/{}".format(
    DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME)

engine = create_engine(DB_CONNECTION, echo=DEBUG, isolation_level="READ_UNCOMMITTED", pool_pre_ping=True)
session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
db_session = scoped_session(session_factory)


def create_graph(transactions):
    # Directed graphs with self loops and parallel edges
    # weighted edges
    di_graph = nx.MultiDiGraph()
    for row in transactions:
        try:
            # date = datetime.fromtimestamp(row.timestamp / 1e3)
            # date = date.strftime("%Y-%m-%d-%H:%M:%S")
            date = row.timestamp
            di_graph.add_edge(row.from_address, row.to_address, weight=float(row.value), date=date, fee=float(row.fee))
        except Exception as err:
            datetime = row.datetime
            dt_utc = datetime.astimezone(pytz.UTC).strftime("%Y-%m-%d-%H:%M:%S")
            di_graph.add_edge(row.from_address, row.to_address, weight=float(row.value), date=dt_utc, fee=float(row.fee))
            logger.error("Error at transaction id {}-{}".format(row.block_id, row.extrinsic_idx))
    return di_graph


def loop_months(graph):
    try:
        # EDIT the end date as needed
        start = datetime(2020, 8, 1)
        end = datetime(2022, 7, 26)
        months_list = [str(d.year) + "-" + str(d.month) for d in rrule(MONTHLY, dtstart=start, until=end)]

        for month in months_list:
            subgraph = nx.MultiDiGraph(((source, target, attr) for source, target, attr in graph.edges(data=True) if
                                        datetime.strptime(attr['date'], "%Y-%m-%d-%H").strftime("%Y-%#m").startswith(
                                            month)))
            logger.info(month)
            nx.write_gpickle(subgraph, 'multidigraph_{}.gpickle'.format(month))

            # Perform any computations required on the monthly subgraph

            logger.info("=======================================END======================================")

    except Exception as error:
        logger.error(error)


# Main
if __name__ == '__main__':
    try:
        # Graph Analysis
        start = timer()
        # Conditions for a proper balance transfer

        # excluding self-loop and zero transfer -- comment out filter condition as required
        signed_transactions = db_session.query(Transaction).filter(Transaction.signed == 1, Transaction.success == 1,
                                                                   Transaction.module_id == 'Balances',
                                                                   Transaction.call_id.in_(
                                                                       ['transfer', 'transfer_keep_alive',
                                                                        'transfer_all']),
                                                                   Transaction.to_address.is_not(None),
                                                                   Transaction.from_address.is_not(None),
                                                                   Transaction.from_address != Transaction.to_address,
                                                                   Transaction.block_id <= 12532600,
                                                                   Transaction.value > 0)

        count = signed_transactions.count()
        logger.info("SUCCESSFUL Balances Transfer (only) Count={}".format(count))

        digraph = create_graph(signed_transactions)
        logger.info("GRAPH CREATED!")
        nx.write_gpickle(digraph, 'multidigraph_12532600_without_zero.gpickle')

        #digraph = nx.read_gpickle('multidigraph_proper_txns.gpickle')
        #logger.info("Graph Reading COMPLETED...")

        # loop_months(digraph)

        #degree_centrality = nx.degree_centrality(digraph)
        #max_centrality = sorted(degree_centrality, key=degree_centrality.get, reverse=True)
        # Top 10 max degree centrality
        # max_centrality = sorted(degree_centrality, key=degree_centrality.get, reverse=True)[:10]
        # for a in max_centrality:
        #     print(a, "----->", degree_centrality[a])

        # logger.info(max_centrality)

        #logger.info("Graph Analysis Total Execution Time (seconds): {}".format(timer() - start))

    except Exception as err:
        db_session.remove()  # close db connection
        logger.error(traceback.format_exc())
