"""
account_info_handler.py

Fetching Account Info for known accounts from the substrate API.

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
from substrateinterface import SubstrateInterface
from substrateinterface.exceptions import StorageFunctionNotFound

from app.models.data import AccountInfoSnapshot

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

BLOCK_TRANSFER_FUNCTION = 1205128

# create and configure logger
filename = "../../logs/account_info_snapshot2.log"
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

            # Query snapshot at block_id corresponding to 25th of each month from 25 Aug 2020 00:00:00 until July 25
            # 2022
            # select id from block where datetime= DATE_FORMAT(CONVERT_TZ(datetime, '+03:00', '+00:00'),
            # '2020-%m-25 00:00:00');
            block_ids = [1293957, 1739297, 2168299, 2612529, 3042945, 3487164, 3932501, 4332719, 4778061, 5206293, 5650640, 6082432, 6527621, 6973768, 7847525, 8279239, 8725455,
                         9171661, 9573880, 10019762, 10448617, 10883304, 11307029]
            # block_id = 11320000 (July 25)

            for block_id in block_ids:

                try:

                    block_hash = substrate.get_block_hash(block_id)
                    nominators = []
                    validators = []
                    council_members = []

                    # retrieve council members for block
                    try:
                        council = substrate.query(
                            module="Council",
                            storage_function="Members",
                            block_hash=block_hash
                        )
                        council_members = council.value
                    except StorageFunctionNotFound:
                        council_members = []

                    # retrieve session ID for block
                    try:
                        current_era = substrate.query(
                            module="Staking",
                            storage_function="CurrentEra",
                            block_hash=block_hash
                        )
                        current_era = current_era.value
                    except StorageFunctionNotFound:
                        current_era = None

                    # Retrieve validators for session from storage
                    try:
                        validators_q = substrate.query(
                            module="Session",
                            storage_function="Validators",
                            params=[],
                            block_hash=block_hash
                        )
                    except StorageFunctionNotFound:
                        validators_q = []

                    for rank_nr, validator_account in enumerate(validators_q):
                        validators.append(validator_account.value)

                        try:
                            exposure = substrate.query(
                                module="Staking",
                                storage_function="ErasStakers",
                                params=[current_era, validator_account.value],
                                block_hash=block_hash
                            )
                            exposure = exposure.value

                        except StorageFunctionNotFound:
                            exposure = None

                        if not exposure:
                            exposure = {}

                        # Store nominators
                        for rank_nominator, nominator_info in enumerate(exposure.get('others', [])):
                            nominator_stash = nominator_info.get('who').replace('0x', '')
                            nominators.append(nominator_stash)

                    for validator in validators:
                        try:
                            AccountInfoSnapshot.query(db_session).filter_by(block_id=block_id, account_id=validator) \
                                .update({AccountInfoSnapshot.is_validator: True, }, synchronize_session='fetch')
                            logger.info("Saving validator {}, block#{}".format(validator, block_id))
                            db_session.commit()
                        except Exception as err:
                            # clear the db session
                            db_session.rollback()
                            logger.error(traceback.format_exc())

                    for nominator in nominators:
                        try:
                            AccountInfoSnapshot.query(db_session).filter_by(block_id=block_id, account_id=nominator) \
                                .update({AccountInfoSnapshot.is_nominator: True, }, synchronize_session='fetch')
                            logger.info("Saving nominator {}, block#{}".format(nominator, block_id))
                            db_session.commit()
                        except Exception as err:
                            # clear the db session
                            db_session.rollback()
                            logger.error(traceback.format_exc())

                    for council in council_members:
                        try:
                            AccountInfoSnapshot.query(db_session).filter_by(block_id=block_id, account_id=council) \
                                .update({AccountInfoSnapshot.is_council: True, }, synchronize_session='fetch')
                            logger.info("Saving council {}, block#{}".format(council, block_id))
                            db_session.commit()
                        except Exception as err:
                            # clear the db session
                            db_session.rollback()
                            logger.error(traceback.format_exc())

                except Exception as err:
                    # clear the db session.py
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
