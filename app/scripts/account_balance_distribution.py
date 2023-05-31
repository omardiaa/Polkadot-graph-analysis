"""
account_balance_distribution.py

Generating a distribution PDF plot of the account balances.

<Author>: Hanaa Abbas
<Email>: hanaaloutfy94@gmail.com
<Date>: 31 May, 2023

GNU General Public License Version 3
""" 
import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from timeit import default_timer as timer

from sqlalchemy import create_engine
from sqlalchemy.sql import text

import pandas as pd
import matplotlib.pyplot as plt

DB_NAME = "polkadot_analysis"
DB_HOST = "localhost"
DB_PORT = 3306
DB_USERNAME = "root"
DB_PASSWORD = "root"
DEBUG = False

DB_CONNECTION = "mysql+mysqlconnector://{}:{}@{}:{}/{}".format(
    DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME)

engine = create_engine(DB_CONNECTION, echo=DEBUG, isolation_level="READ_UNCOMMITTED", pool_pre_ping=True)

# create and configure logger
filename = "../../logs/account_balance.log"
logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()

# Main
if __name__ == '__main__':

    try:
        start = timer()

        with engine.connect().execution_options(autocommit=True) as conn:

            # sql = ''' select e.block_id, CONVERT_TZ(e.datetime, '+03:00', '+00:00') as date_time,
            #       count(e.block_id) as txns_volume, sum(e.value) as txns_total_value,
            #       min(e.value) as minimum_value, max(e.value) as maximum_value
            #       from extrinsic e
            #       where e.module_id = 'Balances' and e.success = 1
            #       group by e.block_id
            #       order by e.block_id asc; '''

            sql = ''' SELECT balance_total FROM account_info_snapshot; '''
            query = conn.execute(text(sql))
            df = pd.DataFrame(query.fetchall())

            # df.to_csv(r'success_txn_per_block.csv', index=False)  # place 'r' before the path name

            plt.figure(figsize=(12, 8))
            df.balance_total.hist()
            plt.gca().set_yscale("log")
            plt.xlabel('Total Balance (DOT)')
            plt.title('Distribution of Account Balances')
            plt.ylabel('Number of accounts')
            plt.show()

            logger.info("Block Processing Total Execution Time (seconds): {}".format(timer() - start))
            print("End of Execution....")

    except Exception as err:
        logger.error(traceback.format_exc())
