import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from timeit import default_timer as timer

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from app.models.data import AccountInfoSnapshot
import csv
from sqlalchemy.sql import func, text

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

# create and configure logger
filename = "../../logs/richest_accounts.log"
logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()

sql = (
    "SELECT :account_id as account_id, COUNT(*) AS in_degree,  COALESCE(SUM(value), 0.00) as weight"
    " FROM extrinsic"
    " where module_id = 'Balances' and success = 1 and to_address=:account_id and block_id <= :block_id and "
    "from_address != to_address; "
)

# Main
if __name__ == '__main__':

    try:
        start = timer()

        block_ids = [1293957, 1739297, 2168299, 2612529, 3042945, 3487164, 3932501, 4332719, 4778061, 5206293,
                     5650640, 6082432, 6527621, 6973768, 7405900, 7847525, 8279239, 8725455,
                     9171661, 9573880, 10019762, 10448617, 10883304, 11307029]
        k = 100

        for block_id in block_ids:
            # query non zero balance totals
            query = AccountInfoSnapshot.query(db_session).filter_by(block_id=block_id)
            total_accounts = query.count()
            total_active = query.filter(AccountInfoSnapshot.balance_total > 0).count()
            top_records = query.order_by(AccountInfoSnapshot.balance_total.desc()).limit(k).all()

            if len(top_records) > 0:
                with open('../../accounts/account_info_snapshot_{}_top{}.csv'.format(block_id, k), 'w',
                          newline='') as outfile:
                    outcsv = csv.writer(outfile)
                    outcsv.writerow(AccountInfoSnapshot.__table__.columns.keys())
                    [outcsv.writerow([getattr(curr, column.name) for column in AccountInfoSnapshot.__mapper__.columns])
                     for
                     curr in
                     top_records]
                    logger.info("Saved file for top {} Block#{}".format(k, block_id))

                account_ids = []
                for e in top_records:
                    account_ids.append(e.account_id)

                # cumulative in-degree
                with open('../../accounts/account_info_snapshot_{}_top{}_indegree.csv'.format(block_id, k), 'w',
                          newline='') as outfile:
                    outcsv = csv.writer(outfile)
                    outcsv.writerow(["account_id", "in_degree", "weight"])
                    for account_id in account_ids:
                        query = db_session.execute(text(sql),
                                                   {"block_id": block_id, "account_id": account_id}).fetchall()
                        outcsv.writerows(query)
                    logger.info("Saved file for indegree top {} Block#{}".format(k, block_id))

                average = db_session.query(func.avg(AccountInfoSnapshot.balance_total)).filter(
                    AccountInfoSnapshot.block_id == block_id, AccountInfoSnapshot.balance_total > 0).first()[0]
                logger.info("Block#{} --- Total Average: {}".format(block_id, average))
                logger.info("Total Active Account # {}".format(total_active))
                logger.info("Total Inactive Accounts #{}".format(total_accounts - total_active))

        logger.info("Block Processing Total Execution Time (seconds): {}".format(timer() - start))
        print("End of Execution....")

    except KeyboardInterrupt:
        print('KeyboardInterrupt')
        db_session.remove()  # close db connection
        sys.exit(0)

    except Exception as err:
        db_session.remove()  # close db connection
        logger.error(traceback.format_exc())

    finally:
        db_session.remove()
