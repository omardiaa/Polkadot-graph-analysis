import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.sql import text

from data import Transaction

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
filename = "../../logs/fixes.log"
logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()

#  and e.block_id > 9080936
transfer_all_sql = ("select e.block_id as block_id, e.extrinsic_idx as extrinsic_idx, e.attributes as attributes "
                    "from extrinsic ex "
                    "join event e "
                    "where ex.call_id = '{0}' and ex.extrinsic_idx = e.extrinsic_idx and e.block_id = ex.block_id "
                    "and e.event_id = '{1}';") \
    .format('transfer_all', 'Transfer')

# and block_id > 7228648
batch_sql = (
    "select ex.block_id as block_id, ex.extrinsic_idx as extrinsic_idx, ex.batch_idx as batch_idx, "
    "e.attributes as attributes from extrinsic ex "
    "join event e on e.block_id = ex.block_id and e.extrinsic_idx = ex.extrinsic_idx "
    "where e.module_id = '{0}' and e.event_id = '{1}' and ex.module_id = '{2}' and ex.block_id > 7228648;") \
    .format('Utility', 'BatchInterrupted', 'Utility')


query_proper_txns = (
    "select b.id, b.datetime, sum(e.value) as total_value, count(e.block_id) as volume from block b "
    "JOIN extrinsic e on e.block_id = b.id"
    "where e.module_id = 'Balances' and e.success = 1 and e.value > 0 and e.from_address != e.to_address"
    "GROUP BY date(b.datetime) "
    "order by id desc;"
    )

query_pseudospam_txns = (
    "select b.id, b.datetime, sum(e.value) as total_value, count(e.block_id) as volume from block b "
    "JOIN extrinsic e on e.block_id = b.id"
    "where (e.value = 0 OR e.from_address = e.to_address)"
    "and e.module_id = 'Balances' and e.success = 1 "
    "GROUP BY date(b.datetime) "
    "order by id desc;"
)

# Main
if __name__ == '__main__':
    try:

        ################## Fixing transfer_all value #############################
        # rows = db_session.execute(text(transfer_all_sql))
        # print("Total Count: {}".format(rows.rowcount))
        # for row in rows:
        #     attributes = json.loads(row['attributes'])
        #     for attr in attributes:
        #         if type(attr) is not dict:
        #             value = attributes[2] / 10 ** 10
        #             break
        #         elif attr['type'] == 'Balance':
        #             value = attr['value'] / 10 ** 10
        #
        #     Transaction.query(db_session).filter_by(block_id=row['block_id'], extrinsic_idx=row['extrinsic_idx'])\
        #         .update({Transaction.value: value}, synchronize_session='fetch')
        #     db_session.commit()

        ################## Fixing success value for batch interrupted #############################
        rows = db_session.execute(text(batch_sql))
        print("Total Count: {}".format(rows.rowcount))  # 1478984
        # failed at block 7228648
        for row in rows:
            attributes = json.loads(row['attributes'])
            for attr in attributes:
                if type(attr) is dict:
                    if attr['type'] == 'u32':
                        error_index = attr['value']
                else:
                    error_index = attr
                    break

            print(
                "Block {} extrinsic_idx {} error_index {} ".format(row['block_id'], row['extrinsic_idx'], error_index))
            results = Transaction.query(db_session).filter(Transaction.block_id == row['block_id'],
                                                           Transaction.extrinsic_idx == row['extrinsic_idx'],
                                                           Transaction.batch_idx >= error_index + 1)
            print("Updating {} records ".format(results.count()))
            results.update({Transaction.success: False}, synchronize_session='fetch')
            db_session.commit()

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
