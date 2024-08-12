"""
main.py

Querying Blocks, Events, and Transactions data from the substrate API.

<Author>: Hanaa Abbas
<Email>: hanaaloutfy94@gmail.com
<Date>: 31 May, 2023

GNU General Public License Version 3
"""


import getopt
import logging
import sys
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from timeit import default_timer as timer
import json
import copy

from scalecodec.base import ScaleBytes
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.sql import text
from substrateinterface import SubstrateInterface

from app.models.data import Block, Transaction, Account, Event, ProxyAccount

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
filename = "logs/polkadot_analysis_nov.log"
logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()

EXTERNAL_URL = "wss://rpc.polkadot.io"
INTERNAL_URL = "ws://172.22.254.48:9944"
# INTERNAL_URL = "ws://172.20.23.176:9944"
# INTERNAL_URL = "ws://localhost:9944"
# DEFAULT_URL = "ws://192.168.3.38:9999"


class BlockAlreadyAdded(Exception):
    pass


def validate_index(idx):
    try:
        idx = idx.strip()
        if not idx:
            idx = db_session.query(Block.id).order_by(Block.id.desc()).first()
            if idx == 0 or idx is None:
                return BLOCK_TRANSFER_FUNCTION
            else:
                return idx.id + 1
        elif idx.isdigit():
            return int(idx)
        else:
            return BLOCK_TRANSFER_FUNCTION
    except ValueError as ex:
        print(ex)


def validate_count(block_count):
    try:
        block_count = block_count.strip()
        if not block_count:
            return 1
        elif block_count.isdigit():
            return int(block_count)
        else:
            return 1
    except ValueError as ex:
        print(ex)

def create_account(address, block, options = {}):
    account_info = substrate.query(module='System', storage_function='Account',
                                   params=[address], block_hash=block.hash)

    identity_display = None
    identity_judgement = None

    try:
        identity = substrate.query(module='Identity', storage_function='IdentityOf',
                            params=[address], block_hash=block.hash)
        if identity.value:        
            if isinstance(identity.value, tuple):
                identity_value = identity.value[0]
            else:
                identity_value = identity.value
            
            identity_display = identity_value.get('info')['display']['Raw']
            identity_judgement = ','.join(map(str, identity_value['judgements']))
    except Exception:
        logger.error(traceback.format_exc())

    # returns list of validators at that session of the block
    session = substrate.query(module='Session', storage_function='Validators',
                              block_hash=block.hash)
    if session.value:
        is_validator = address in session.value

    token_decimals = substrate.token_decimals if block.id >= 1248328 else 12

    is_proxy = options.get('is_proxy') or False
    proxied = options.get('proxied') or False
    is_multisig = options.get('is_multisig') or False

    account = Account.query(db_session).filter_by(address=address).first()
    if not account:
        account = Account(
            address=address,
            pkey=substrate.ss58_decode(address),
            balance_free=account_info['data']['free'].value / 10 ** token_decimals,
            balance_reserved=account_info['data']['reserved'].value / 10 ** token_decimals,
            nonce=account_info['nonce'].value,
            created_at_block=block.id,
            updated_at_block=block.id,
            identity_display=identity_display,
            # identity_judgement=identity_judgement,
            is_validator=is_validator,
            is_proxy=is_proxy,
            proxied=proxied,
            is_multisig=is_multisig
        )
        account.save(db_session)

    else:
        print("Previous Records for account {} exists in DB".format(address))
        is_proxy = is_proxy or account.is_proxy
        proxied = proxied or account.proxied
        is_multisig = is_multisig or account.is_multisig

        Account.query(db_session).filter_by(
            address=address
        ).update({Account.balance_free: account_info['data']['free'].value / 10 ** token_decimals,
                  Account.balance_reserved: account_info['data']['reserved'].value / 10 ** token_decimals,
                  Account.nonce: account_info['nonce'].value,
                  Account.updated_at_block: block.id,
                #   Account.identity_judgement: identity_judgement,
                  Account.identity_display: identity_display,
                  Account.is_validator: is_validator,
                  Account.is_proxy: is_proxy,
                  Account.proxied: proxied,
                  Account.is_multisig: is_multisig},
                 synchronize_session='fetch')
        print("Updated Account {}...".format(address))

def create_proxy_account(address, proxied_account_address, proxy_type):
    account = ProxyAccount.query(db_session).filter_by(
        address=address, proxied_account_address=proxied_account_address
    ).first()
    if not account:
        account = ProxyAccount(
            address=address,
            proxied_account_address=proxied_account_address,
            proxy_type=proxy_type
        )
        account.save(db_session)

    else:
        print("Previous Records for account {} exists in DB".format(address))
        ProxyAccount.query(db_session).filter_by(
            address=address, proxied_account_address=proxied_account_address
        ).update({ProxyAccount.proxy_type: proxy_type})
        print("Updated Account {}, {}...".format(address, proxied_account_address))

def process_single_txn(extrinsic_success, extrinsic_idx, extrinsic, block, batch=False, nesting_idx=0, batch_idx=0):
    transaction = Transaction(
        block_id=block.id,
        extrinsic_idx=extrinsic_idx,
        nesting_idx=nesting_idx,
        batch_idx=batch_idx,
        extrinsic_length=extrinsic.value['extrinsic_length'],
        extrinsic_hash=extrinsic.value['extrinsic_hash'],
        signed=extrinsic.signed,
        module_id=extrinsic.value['call']['call_module'],
        call_id=extrinsic.value["call"]["call_function"],
        success=int(extrinsic_success),
        spec_version_id=extrinsic.runtime_config.active_spec_version_id,
        # debug_info=calls,
        datetime=block.datetime,
        timestamp=block.timestamp
    )

    call_args = extrinsic.value['call']['call_args']

    addresses = []
    token_decimals = substrate.token_decimals if block.id >= 1248328 else 12
    old_fees = False

    # signed extrinsic
    if extrinsic.signed:
        # get transaction fee
        event = Event.query(db_session).filter_by(block_id=block.id, extrinsic_idx=extrinsic_idx,
                                                  module_id='Balances', event_id='Withdraw').first()
        #TODO: remove this query, additional database access that can be optimized

        if event:
            if type(event.attributes) is dict:
                transaction.fee = event.attributes['amount'] / 10 ** token_decimals
            else:
                transaction.fee = event.attributes[1] / 10 ** token_decimals
        else:
            old_fees = True
            transaction.fee = 0
            event_list = Event.query(db_session).filter_by(block_id=block.id, extrinsic_idx=extrinsic_idx,
                                                           module_id='Balances', event_id='Deposit').all()
            if event_list and len(event_list) > 0:
                for e in event_list:
                    for attr in e.attributes:
                        # handle post-7229130 changes to event attributes
                        if type(attr) is not dict:
                            transaction.fee += (e.attributes[1] / 10 ** token_decimals)
                            break
                        elif attr['type'] == 'Balance':
                            transaction.fee += (attr['value'] / 10 ** token_decimals)

            event_list = Event.query(db_session).filter_by(block_id=block.id, extrinsic_idx=extrinsic_idx,
                                                           module_id='Treasury', event_id='Deposit').all()
            if event_list and len(event_list) > 0:
                for e in event_list:
                    # handle post-7229130 changes to event attributes
                    if type(e.attributes) is list:
                        for attr in e.attributes:
                            if attr['type'] == 'Balance':
                                transaction.fee += (attr['value'] / 10 ** token_decimals)
                    else:
                        transaction.fee += (e.attributes / 10 ** token_decimals)

        for param in call_args:
            if 'Balance' in param['type'] and isinstance(param['value'], int):
                # handle redomination
                try:
                    transaction.value = param['value'] / 10 ** token_decimals
                except TypeError:
                    logger.error(traceback.format_exc())  # do nothing
                except Exception:
                    logger.error(traceback.format_exc())
            elif param['type'] == 'LookupSource':
                # Handle Substrate MultiAddress Format: Id, Index, Address32, Address20 (20 bytes representation)
                # https://docs.substrate.io/rustdocs/latest/sp_runtime/enum.MultiAddress.html
                # starting from block #4001911
                try:
                    if type(param['value']) is dict:
                        if 'Id' in param['value']:
                            transaction.to_address = param['value']['Id']
                        elif 'Address20' in param['value']:
                            transaction.to_address = 'Address20:' + param['value']['Address20']
                        elif 'Address32' in param['value']:
                            transaction.to_address = substrate.ss58_encode(param['value']['Address32'])
                        elif 'Raw' in param['value']:
                            transaction.to_address = substrate.ss58_encode(param['value']['Raw'])
                    else:
                        transaction.to_address = param['value'].replace('0x', '')

                    if substrate.is_valid_ss58_address(transaction.to_address):
                        addresses.append(transaction.to_address)
                except Exception: # to catch exceptions such as substrate errors (Invalid length for address)
                    logger.error(traceback.format_exc())
            elif param['type'] == 'AccountIdLookupOf':
                transaction.to_address = param['value']
                if substrate.is_valid_ss58_address(transaction.to_address):
                    addresses.append(transaction.to_address)

        if 'address' in extrinsic:
            transaction.from_address = extrinsic.value['address'].replace('0x', '')
            transaction.signature = list(extrinsic.value['signature'].values())[0]
            transaction.tip = extrinsic.value['tip'] / 10 ** token_decimals
            transaction.nonce = extrinsic.value['nonce']
            addresses.append(transaction.from_address)

            # subtract tips (if withdraw event is not there):
            if old_fees:  # check if also applicable to new fees if withdraw includes the fees as well
                transaction.fee = transaction.fee - transaction.tip

        # TODO handle Balances-transfer_all separately
        # NOTE:::: the value of the transaction is part of its corresponding Balances-Transfer event
        # some of these transfer_all do not have an event available, this is because the transaction had either failed
        # or the sender is including his own address as the destination !!!

        if transaction.value is not None and \
                transaction.value > 0 and transaction.to_address is not None:
            logger.info(">>{} {} from {} -> {}: Value {}".format(
                transaction.module_id, transaction.call_id,
                transaction.from_address, transaction.to_address,
                '{} {}'.format(transaction.value, substrate.token_symbol)
            ))

    # unsigned
    else:
        for param in extrinsic.value["call"]['call_args']:
            if param['name'] == 'now':
                block.timestamp = param['value']
                block.datetime = datetime.fromtimestamp(block.timestamp / 1e3)
                logger.info(">> Datetime: " + block.datetime.strftime("%d/%m/%Y, %H:%M:%S"))

    transaction.save(db_session)
    return addresses

def construct_extrinsic_value(extrinsic, call):
    new_extrinsic = copy.deepcopy(extrinsic)
    new_extrinsic.value["extrinsic_length"] = 0 # Total length is in the original extrinsic
    new_extrinsic.value["call"] = call
    return new_extrinsic


def create_transaction(extrinsic, block, extrinsic_success, extrinsic_idx, nesting_idx, batch, batch_idx, batch_interrupted_index, multisig_status, proxy_status):
    if extrinsic.signed:
        block.count_extrinsics_signed += 1
    else:
        block.count_extrinsics_unsigned += 1

    call_args = extrinsic.value["call"]['call_args']    
    
    addresses = process_single_txn(extrinsic_success, extrinsic_idx, extrinsic, block, batch, nesting_idx, batch_idx)
    #TODO: Update addresses, not the complete list

    call_module = extrinsic.value['call']['call_module']

    if call_module == 'Utility':
        logger.info("Utility Extrinsic {}...".format(extrinsic.value["call"]["call_function"]))
        # handling batch transactions
        for call in call_args:
            if 'Vec<Call>' in call['type'] or call['name'] == 'calls':
                batch_calls = call['value']
                batch_idx = 1
                for batch_call in batch_calls:
                    if batch_idx == batch_interrupted_index:
                        extrinsic_success = False #For all next extrinsics in the batch as well
                    new_extrinsic = construct_extrinsic_value(extrinsic, batch_call)
                    #extrinsic.value["call"]['call_args']
                    _, new_addresses = create_transaction(new_extrinsic, block, extrinsic_success, extrinsic_idx, nesting_idx + 1, True, batch_idx, batch_interrupted_index, multisig_status, proxy_status)
                    addresses.extend(new_addresses)
                    batch_idx += 1
            elif call['name'] == 'call': # Utility.as_declarative: Dispatch a call from a derivative signed origin
                batch_idx = 1
                new_extrinsic = construct_extrinsic_value(extrinsic, call['value'])
                _, new_addresses = create_transaction(new_extrinsic, block, extrinsic_success, extrinsic_idx, nesting_idx + 1, True, batch_idx, batch_interrupted_index, multisig_status, proxy_status)
                addresses.extend(new_addresses)

    if (call_module == 'Multisig' and multisig_status) or (call_module == 'Proxy' and proxy_status):
        #TODO: Handle if proxy failed, proxy_status
        logger.info("{} Extrinsic {}...".format(call_module, extrinsic.value["call"]["call_function"]))

        for call in call_args:
            if call['name'] == 'call':
                internal_call_args = call['value']
                if type(internal_call_args) is dict:
                    new_extrinsic = construct_extrinsic_value(extrinsic, internal_call_args)
                    _, new_addresses = create_transaction(new_extrinsic, block, extrinsic_success, extrinsic_idx, nesting_idx + 1, False, batch_idx, batch_interrupted_index, multisig_status, proxy_status)
                    addresses.extend(new_addresses)
                else:
                    logger.warning("Nested Extrinsic {} in block {} skipped because of encoded calls".format(call_module, block.id))

    return block, addresses

def process_block(block_number):
    if Block.query(db_session).filter_by(id=block_number).count() > 0:
        raise BlockAlreadyAdded(block_number)  # skip if block already exists

    block = substrate.get_block(block_number=block_number, include_author=True)
    block_hash = block['header']['hash']
    logger.info(">>> Processing block {} hash '{}' author: {}".format(block_number, block_hash, block['author']))

    block_id = block['header']['number']
    digest_logs = block['header'].get('digest', {}).pop('logs', None)
    extrinsics_data = block.pop('extrinsics')
    block_events = substrate.get_events(block_hash=block_hash)

    if Block.query(db_session).filter_by(hash=block_hash).count() > 0:
        raise BlockAlreadyAdded(block_hash)  # skip if block already exists

    # new block to be added
    block = Block(
        id=block_id,
        parent_id=block_id - 1,
        hash=block_hash,
        parent_hash=block['header']['parentHash'],
        state_root=block['header']['stateRoot'],
        extrinsics_root=block['header']['extrinsicsRoot'],
        author=block['author'],
        count_extrinsics=len(extrinsics_data),
        count_extrinsics_signed=0,
        count_extrinsics_unsigned=0,
        count_extrinsics_error=0,
        count_extrinsics_success=0,
        count_events=len(block_events),
        count_accounts_new=0,
        count_accounts_reaped=0,
        count_sessions_new=0,
        count_log=len(digest_logs),
        spec_version_id=substrate.runtime_version
    )

    # handling block digest/logs
    logs = []
    try:
        for log_data in digest_logs:
            if substrate.implements_scaleinfo():
                if 'PreRuntime' in log_data and log_data.value['PreRuntime'][0] == f"0x{b'BABE'.hex()}":
                    babe_predigest = substrate.runtime_config.create_scale_object(
                        type_string='RawBabePreDigest',
                        data=ScaleBytes(log_data.value['PreRuntime'][1])
                    )
                    babe_predigest.decode()
                    block.authority_index = babe_predigest[1].value['authority_index']
                    block.slot_number = babe_predigest[1].value['slot_number']
                    log_data.value['PreRuntime'] = ('BABE', babe_predigest.value)

                elif 'Seal' in log_data and log_data.value['Seal'][0] == f"0x{b'BABE'.hex()}":
                    # do nothing
                    # print("TODO: decode Seal")
                    log_data.value['Seal'] = ('BABE', log_data.value['Seal'][1])
            else:
                if 'PreRuntime' in log_data:
                    # Determine block producer
                    block.authority_index = int(log_data.value['PreRuntime']['data']['authority_index'])
                    block.slot_number = log_data.value['PreRuntime']['data']['slot_number']

            logs.append(log_data.value)

    except Exception as e:
        # errors due to new way of handling logs as scale_info, new runtime types
        print(e)  # do nothing

    block.logs = logs

    # ==== Get block events from Substrate ==================
    extrinsic_success_idx = {}
    extrinsic_batch_success_idx = {} #For Utility.Batch extrinsics
    multisig_status_idx = {} #For Multisig extrinsics
    proxy_status_idx = {} #For Proxy extrinsics

    # Events ###
    event_idx = 0
    parent_spec_version = substrate.get_block_runtime_version(block.parent_hash).get('specVersion', 0)
    for event in block_events:
        if Event.query(db_session).filter_by(block_id=block_id, extrinsic_idx=event.value['extrinsic_idx'],
                                             event_idx=event_idx).count() > 0:
            print("Event {} for block {}-extrinsic {} already exists".format(event_idx, block_id,
                                                                             event.value['extrinsic_idx']))
        else:
            model = Event(
                block_id=block_id,
                event_idx=event_idx,
                phase=event.value['phase'],
                extrinsic_idx=event.value['extrinsic_idx'],
                type=event.value['event_index'],
                spec_version_id=parent_spec_version,
                module_id=event.value['module_id'],
                event_id=event.value['event_id'],
                system=int(event.value['module_id'] == 'System'),
                attributes=event.value['attributes']
            )

            # Process event
            if event.value['module_id'] == 'System':
                # Store result of extrinsic
                if event.value['event_id'] == 'ExtrinsicSuccess':
                    extrinsic_success_idx[event.value['extrinsic_idx']] = True
                    block.count_extrinsics_success += 1

                if event.value['event_id'] == 'ExtrinsicFailed':
                    extrinsic_success_idx[event.value['extrinsic_idx']] = False
                    block.count_extrinsics_error += 1

                if event.value['event_id'] == 'NewAccount':
                    block.count_accounts_new += 1

                if event.value['event_id'] == 'KilledAccount':

                    # handle post-block 7229130 errors TypeError: string indices must be integers TODO find better
                    #  way to get a decoded version of events and extrinsics based on the runtime version
                    if type(event.value['attributes']) is str:
                        addr = event.value['attributes']
                    elif type(event.value['attributes']) is dict and 'account' in event.value['attributes']:
                        addr = event.value['attributes']['account']
                    else:
                        addr = event.value['attributes'][0]['value']

                    Account.query(db_session).filter_by(
                        address=addr
                    ).update({Account.is_reaped: True}, synchronize_session='fetch')
                    block.count_accounts_reaped += 1
                    logger.info("Updated Killed Account {}...".format(addr))

            if event.value['module_id'] == 'Utility':
                if event.value['event_id'] ==  'BatchInterrupted':
                    block_extrinsic_idx = event.value['extrinsic_idx']
                    batch_extrinsic_idx = 0
                    if isinstance(event.value['attributes'], list):
                        batch_extrinsic_idx = event.value['attributes'][0]['value']
                    elif 'index' in event.value['attributes']:
                        batch_extrinsic_idx = event.value['attributes']['index']
                        
                    extrinsic_batch_success_idx[block_extrinsic_idx] = batch_extrinsic_idx + 1
            # TODO handle other events to figure out information about governance,
            #  staking and sessions (incl. validators and nominators)
            if event.value['module_id'] == 'Session' and event.value['event_id'] == 'NewSession':
                block.count_sessions_new += 1

            if event.value['module_id'] == 'Proxy':
                if event.value['event_id'] ==  'ProxyAdded':
                    delegator = event.value['attributes']['delegator']
                    delegatee = event.value['attributes']['delegatee']
                    proxy_type = event.value['attributes']['proxy_type']

                    create_account(delegator, block, {'proxied': True})
                    create_account(delegatee, block, {'is_proxy': True})
                    create_proxy_account(delegator, delegatee, proxy_type)
                elif event.value['event_id'] ==  'ProxyRemoved':
                    logger.info("Proxy removed")
                    #TODO: remove proxy account, remove account record
                elif event.value['event_id'] == 'ProxyExecuted':
                    extrinsic_idx = event.value['extrinsic_idx']
                    proxy_status_idx[extrinsic_idx] = True

            if event.value['module_id'] == 'Multisig':
                if event.value['event_id'] == 'MultisigExecuted':
                    create_multisig_account = False
                    if isinstance(event.value['attributes'], list):
                        # [0] is sender address, [2] is multisig address
                        multisig = event.value['attributes'][2]['value']
                        create_multisig_account = True
                    elif type(event.value['attributes']) is dict and 'multisig' in event.value['attributes']:
                        multisig = event.value['attributes']['multisig']
                        create_multisig_account = True

                    if create_multisig_account:
                        create_account(multisig, block, {'is_multisig': True})

                    extrinsic_idx = event.value['extrinsic_idx']
                    multisig_status_idx[extrinsic_idx] = True

            model.save(db_session)
        event_idx += 1

    extrinsic_idx = 0
    nesting_idx = 0
    batch_idx = 0
    batch = False

    address_list = set()
    for extrinsic in extrinsics_data:
        if Transaction.query(db_session).filter_by(block_id=block_id, extrinsic_idx=extrinsic_idx).count() > 0:
            print("Transaction {} for block {} already exists".format(extrinsic_idx, block_id))
        else:
            extrinsic_success = extrinsic_success_idx.get(extrinsic_idx, False)
            batch_interrupted_index = extrinsic_batch_success_idx.get(extrinsic_idx, -1)
            multisig_status = multisig_status_idx.get(extrinsic_idx) or False
            proxy_status = proxy_status_idx.get(extrinsic_idx) or False

            (block, addresses) = create_transaction(extrinsic, block, extrinsic_success, extrinsic_idx, nesting_idx, batch,  batch_idx, batch_interrupted_index, multisig_status, proxy_status)

            address_list.update(addresses)
        extrinsic_idx += 1

    # handle accounts creation/update
    for address in address_list:
        create_account(address, block)
    create_account(block.author, block)  # create account for validator/block author

    block.save(db_session)
    # commit the db session
    db_session.commit()


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

        clear = input("Clear DB?")

        if clear.lower() == 'y':
            engine.execute(text('''TRUNCATE TABLE event''').execution_options(autocommit=True))
            engine.execute(text('''TRUNCATE TABLE extrinsic''').execution_options(autocommit=True))
            engine.execute(text('''TRUNCATE TABLE account_history''').execution_options(autocommit=True))
            engine.execute(text('''TRUNCATE TABLE account''').execution_options(autocommit=True))
            engine.execute(text('''TRUNCATE TABLE block''').execution_options(autocommit=True))

        clear = input("Clear Logs?")
        if clear.lower() == 'y':
            open('polkadot_analysis.log', 'w').close()

        first_index = validate_index(input('Enter first block index [default=highest block]: '))
        count = validate_count(input('Enter block count [default=1]: '))

        if not url:
            url = INTERNAL_URL

        logger.info("Substrate URL: {}".format(url))
        with SubstrateInterface(url=url, ss58_format=0, type_registry_preset='polkadot') as substrate:

            logger.info(
                "Connected to chain {} using {} v {}".format(substrate.chain, substrate.name, substrate.version))

            # check the finalized chain head
            # last_index = substrate.get_block_number(substrate.get_chain_head())

            start = timer()
            # adding missing blocks (if any)
            # missing_blocks = Block.get_missing_block_ids(db_session).all()
            # for missing_block in missing_blocks:
            #     try:
            #         for i in range(int(missing_block[0]), missing_block[1]+1):
            #             process_block(i)
            #     except BlockAlreadyAdded:
            #         print("Block Already Added, Skipping Block...")
            #     except Exception as err:
            #         # clear the db session
            #         db_session.rollback()
            #         logger.error(traceback.format_exc())

            for i in range(first_index, first_index + count):
                try:
                    process_block(i)
                except BlockAlreadyAdded:
                    print("Block Already Added, Skipping Block...")
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
