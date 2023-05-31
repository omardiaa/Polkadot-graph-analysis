"""
identity_handler.py

Fetching Account Identity for known user accounts from substrate API.

<Author>: Hanaa Abbas
<Email>: hanaaloutfy94@gmail.com
<Date>: 31 May, 2023

GNU General Public License Version 3
"""

import getopt
import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from timeit import default_timer as timer

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.sql import text

from substrateinterface import SubstrateInterface

from data import AccountInfoSnapshot

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
filename = "../../logs/identity_handler.log"
logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()

EXTERNAL_URL = "wss://rpc.polkadot.io"
INTERNAL_URL = "ws://172.20.135.65:9944"

# Main
if __name__ == '__main__':

    try:
        argv = sys.argv[1:]
        url = None

        try:
            opts, args = getopt.getopt(argv, "h:u", ["url="])
        except getopt.GetoptError:
            print('main.py -u <url>')
            sys.exit(2)

        for opt, arg in opts:
            if opt == '-h':
                print('main.py -u <url>')
                sys.exit()
            elif opt in ("-u", "--url"):
                url = arg

        if not url:
            url = INTERNAL_URL

        logger.info("Substrate URL: {}".format(url))
        with SubstrateInterface(url=url, ss58_format=0, type_registry_preset='polkadot',
                                use_remote_preset=True) as substrate:
            logger.info(
                "Connected to chain {} using {} v {}".format(substrate.chain, substrate.name, substrate.version))
            start = timer()

            # last block used for analysis
            block_id = 11320000
            block_hash = substrate.get_block_hash(block_id)

            with engine.connect().execution_options(autocommit=True) as conn:
                sql = '''SELECT * FROM account_info_snapshot where is_nominator = 1 or is_validator = 1 or is_council 
                = 1; '''
                result = conn.execute(text(sql)).fetchall()

                for row in result:
                    account_id = row['account_id']
                    identity = substrate.query(module='Identity', storage_function='IdentityOf',
                                               params=[account_id], block_hash=block_hash)

                    if identity.value:
                        identity_display = identity.value.get('info')

                        try:
                            AccountInfoSnapshot.query(db_session).filter_by(block_id=block_id, account_id=account_id) \
                                .update({AccountInfoSnapshot.identity_display: identity_display, },
                                        synchronize_session='fetch')
                            logger.info("Saving identity for {}, block#{}".format(account_id, block_id))
                            db_session.commit()
                        except Exception as err:
                            # clear the db session
                            db_session.rollback()
                            logger.error(traceback.format_exc())

        logger.info("Block Processing Total Execution Time (seconds): {}".format(timer() - start))
        print("End of Execution....")

    except KeyboardInterrupt:
        print('KeyboardInterrupt')
        substrate.close()  # close substrate connection
        db_session.remove()  # close db connection
        sys.exit(0)

    except Exception as err:
        substrate.close()  # close substrate connection
        db_session.remove()  # close db connection
        logger.error(traceback.format_exc())

    finally:
        substrate.close()
        db_session.remove()
