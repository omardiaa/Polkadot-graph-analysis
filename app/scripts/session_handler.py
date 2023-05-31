"""
session_handler.py

Fetching Validator and Nominator Session data from the substrate API.

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

# from models.data import Event
from app.models.session import Session, SessionValidator, SessionNominator

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
filename = "../../logs2/session_handler_aug2022.log"
logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()

EXTERNAL_URL = "wss://rpc.polkadot.io"
INTERNAL_URL = "ws://172.20.23.176:9944"
# INTERNAL_URL = "ws://localhost:9944"
DEFAULT_URL = "ws://192.168.3.38:9999"

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

            try:
                # first_session_block = 2392
                first_session_block = 9966143
                # last_session_block = 9726401
                last_session_block = substrate.get_block_number(substrate.get_chain_head())

                # new_session_list = Event.query(db_session).filter_by(module_id="Session", event_id="NewSession").all()
                # for rank_event, session_event in enumerate(new_session_list):
                for block_id in range(first_session_block, last_session_block):
                    # block_id = session_event.block_id
                    # block_hash = substrate.get_block_hash(session_event.block_id)
                    # attributes = session_id
                    session_id = None
                    block = substrate.get_block(block_number=block_id)
                    block_hash = block['header']['hash']
                    block_events = substrate.get_events(block_hash=block_hash)

                    for event in block_events:
                        if event.value['module_id'] == 'Session' and event.value['event_id'] == 'NewSession':
                            attributes = event.value['attributes']
                            if type(attributes) is list:
                                session_id = attributes[0]['value']
                            else:
                                session_id = attributes
                        else:
                            continue

                    if session_id and Session.query(db_session).filter_by(id=session_id).count() > 0:
                        logger.info("Session {} already added".format(session_id))
                        continue

                    if not session_id:
                        continue

                    token_decimals = substrate.token_decimals if block_id >= 1248328 else 12
                    nominators = []
                    logger.info("Processing Session Id {}, Block Id {}".format(session_id, block_id))

                    try:
                        current_era = substrate.query(
                            module="Staking",
                            storage_function="CurrentEra",
                            block_hash=block_hash
                        )
                        current_era = current_era.value
                    except StorageFunctionNotFound:
                        current_era = None

                    # Retrieve validators for new session from storage
                    try:
                        validators = substrate.query(
                            module="Session",
                            storage_function="Validators",
                            params=[],
                            block_hash=block_hash
                        )
                    except StorageFunctionNotFound:
                        validators = []

                    for rank_nr, validator_account in enumerate(validators):
                        validator_ledger = {}
                        validator_session = None
                        validator_stash = validator_account.value.replace('0x', '')

                        # Retrieve controller account
                        try:
                            validator_controller = substrate.query(
                                module="Staking",
                                storage_function="Bonded",
                                params=[validator_account.value],
                                block_hash=block_hash
                            )
                            validator_controller = validator_controller.value

                            if validator_controller:
                                validator_controller = validator_controller.replace('0x', '')

                        except StorageFunctionNotFound:
                            validator_controller = None
                            logger.error("Session id {} has no validator controller for stash {} "
                                         .format(session_id, validator_account.value))

                        # Retrieve validator preferences for stash account
                        try:
                            validator_prefs = substrate.query(
                                module="Staking",
                                storage_function="ErasValidatorPrefs",
                                params=[current_era, validator_account.value],
                                block_hash=block_hash
                            )
                            validator_prefs = validator_prefs.value
                        except StorageFunctionNotFound:
                            validator_prefs = None

                        if not validator_prefs:
                            validator_prefs = {'commission': None}

                        # Retrieve bonded
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

                        if exposure['total']:
                            bonded_nominators = (exposure['total'] - exposure['own']) / 10 ** token_decimals
                        else:
                            bonded_nominators = None

                        if validator_controller:
                            validator_ledger = substrate.query(
                                module="Staking",
                                storage_function="Ledger",
                                params=[validator_controller],
                                block_hash=block_hash
                            )
                            validator_ledger = validator_ledger.value

                            if not validator_ledger:
                                validator_ledger = {'active': 0}

                        session_validator = SessionValidator(
                            session_id=session_id,
                            controller_key=validator_controller,
                            stash_key=validator_stash,
                            bonded_total=exposure.get('total') / 10 ** token_decimals,
                            bonded_active=validator_ledger[
                                              'active'] / 10 ** token_decimals if validator_ledger else None,
                            bonded_own=exposure['own'] / 10 ** token_decimals,
                            bonded_nominators=bonded_nominators,  # value bonded by nominators
                            # validator_session=validator_session, # session key
                            rank=rank_nr,
                            # unlocking=validator_ledger.get('unlocking'), # unlocking amount
                            count_nominators=len(exposure['others']),
                            # unstake_threshold=None,
                            commission=validator_prefs.get('commission') * 1e-7  # parts per billion to percent
                        )
                        session_validator.save(db_session)

                        # Store nominators
                        for rank_nominator, nominator_info in enumerate(exposure.get('others', [])):
                            nominator_stash = nominator_info.get('who').replace('0x', '')
                            nominators.append(nominator_stash)

                            session_nominator = SessionNominator(
                                session_id=session_id,
                                rank_validator=rank_nr,
                                rank_nominator=rank_nominator,
                                stash_key=nominator_stash,
                                bonded=nominator_info.get('value') / 10 ** token_decimals,
                            )
                            session_nominator.save(db_session)

                    # Store session
                    session = Session(
                        id=session_id,
                        start_at_block=block_id + 1,
                        created_at_block=block_id,
                        end_at_block=block_id + 2400,
                        created_at_event=1,
                        count_validators=len(validators),
                        count_nominators=len(set(nominators)),  # set of unique nominators
                        era=current_era
                    )
                    session.count_blocks = session.end_at_block - session.start_at_block + 1
                    session.save(db_session)

                    logger.info("Era {} Session {}; Validator# {}; Nominators# {}; start {}-end {} "
                                .format(current_era, session_id, session.count_validators, session.count_nominators,
                                        session.created_at_block, session.end_at_block))

                    db_session.commit()
                    # session_id += 1

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
