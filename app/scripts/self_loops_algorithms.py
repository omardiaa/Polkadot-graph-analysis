"""
self_loops_algorithms.py

Self-Loops and Zero DOT transaction Algorithms

<Author>: Hanaa Abbas
<Email>: hanaaloutfy94@gmail.com
<Date>: 31 May, 2023

GNU General Public License Version 3
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.sql import text

import traceback
import logging
import sys
from logging.handlers import RotatingFileHandler

import csv
from data import Block
import datetime

from pandas import *

# create and configure logger
filename = "../../logs/utils.log"
logging.basicConfig(level=logging.INFO,
                    handlers=[RotatingFileHandler(filename, maxBytes=1000000, backupCount=100, mode='a'),
                              logging.StreamHandler(sys.stdout)],
                    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
                    datefmt='%Y-%m-%dT%H:%M:%S', )
logger = logging.getLogger()

# Algorithm 1:
# Input:    start (date): if 0 genesis,
#           end (date): if 0 last parsed block
# Output: TX_Volume (int) number of TXs,
#                 TX_Value (int) total amount of DOTs spent,
#                 Max_Value (int) max TX value
totals_SQL = (
    "select count(e.block_id) as volume, sum(e.value) as value, max(e.value) as max from block b "
    "join extrinsic e on e.block_id = b.id "
    "where e.module_id = '{0}' and e.success = 1 and b.timestamp between {1} and {2};"
)


def totals(start_date, end_date):
    if start_date == 0:
        first_block = db_session.query(Block).filter_by(id=1205128).first()
        if first_block:
            start_date = first_block.timestamp

    if end_date == 0:
        last_block = db_session.query(Block).order_by(Block.id.desc()).first()
        end_date = last_block.timestamp

    if type(start_date) == str:
        try:
            start_datetime = datetime.datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S')
            start_date = datetime.datetime.timestamp(start_datetime)
        except Exception:
            logger.error(traceback.format_exc())
    elif isinstance(start_date, datetime.date):
        start_date = datetime.datetime.timestamp(start_date)

    if type(end_date) == str:
        try:
            end_datetime = datetime.datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S')
            end_date = datetime.datetime.timestamp(end_datetime)
        except Exception:
            logger.error(traceback.format_exc())
    elif isinstance(end_date, datetime.date):
        end_date = datetime.datetime.timestamp(end_date)

    return db_session.execute(text(totals_SQL.format('Balances', start_date, end_date)))


# Algorithm 2:
# Input:    start (date): if 0 genesis,
#           end (date): if 0 last parsed block,
#           account
# Output: self_loops (array): timestamp, value
#         zero_dots (array): receiver account, fee
#         incoming_tx (array): sender account, value, timestamp
#         outgoing_tx (array): destination account, value, timestamp

self_loops_sql = (
    "select b.id as block_number, e.extrinsic_idx as idx, b.datetime as datetime, e.value as value, e.fee as fee from "
    "block b "
    "join extrinsic e on e.block_id = b.id "
    "where e.module_id = '{0}' and e.success = 1 and b.timestamp between {1} and {2} "
    "and e.from_address = '{3}' and e.to_address = e.from_address;"
)

zero_dots_sql = (
    "select b.id as block_number, e.extrinsic_idx as idx, b.datetime as datetime, e.to_address as receiver, "
    "e.fee as fee from block b "
    "join extrinsic e on e.block_id = b.id "
    "where e.module_id = '{0}' and e.success = 1 and b.timestamp between {1} and {2} "
    "and e.from_address = '{3}' and e.value = 0;"
)

incoming_txns_sql = (
    "select b.id as block_number, e.extrinsic_idx as idx, b.datetime as datetime, e.from_address as sender, "
    "e.value as value, e.fee as fee from block b "
    "join extrinsic e on e.block_id = b.id "
    "where e.module_id = '{0}' and e.success = 1 and b.timestamp between {1} and {2} "
    "and e.to_address = '{3}';"
)

outgoing_txns_sql = (
    "select b.id as block_number, e.extrinsic_idx as idx, b.datetime as datetime, e.to_address as receiver, "
    "e.value as value, e.fee as fee from block b "
    "join extrinsic e on e.block_id = b.id "
    "where e.module_id = '{0}' and e.success = 1 and b.timestamp between {1} and {2} "
    "and e.from_address = '{3}';"
)

sql2 = (
    "SELECT :address as address, SUM(IF(to_address = :address, 1, 0)) AS incoming_count, "
    "SUM(IF(to_address = :address, value, 0)) AS incoming_sum, "
    "SUM(IF(from_address = :address, 1, 0)) AS outgoing_count, "
    "SUM(IF(from_address = :address, value, 0)) AS outgoing_sum"
    " FROM extrinsic"
    " where module_id = 'Balances' and success = 1;"
)


def account_totals(start_date, end_date, address):
    if start_date == 0:
        first_block = db_session.query(Block).filter_by(id=1205128).first()
        if first_block:
            start_date = first_block.timestamp

    if end_date == 0:
        last_block = db_session.query(Block).order_by(Block.id.desc()).first()
        end_date = last_block.timestamp

    if type(start_date) == str:
        try:
            start_datetime = datetime.datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S')
            start_date = datetime.datetime.timestamp(start_datetime)
        except Exception:
            logger.error(traceback.format_exc())
    elif isinstance(start_date, datetime.date):
        start_date = datetime.datetime.timestamp(start_date)

    if type(end_date) == str:
        try:
            end_datetime = datetime.datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S')
            end_date = datetime.datetime.timestamp(end_datetime)
        except Exception:
            logger.error(traceback.format_exc())
    elif isinstance(end_date, datetime.date):
        end_date = datetime.datetime.timestamp(end_date)

    self_loops = db_session.execute(text(self_loops_sql.format('Balances', start_date, end_date, address)))
    with open('utils/self_loops_{}_{}_{}.csv'.format(address, start_date, end_date), 'w', newline='') as outfile:
        outcsv = csv.writer(outfile)
        outcsv.writerow(self_loops.keys())
        outcsv.writerows(self_loops.fetchall())

    zero_dots = db_session.execute(text(zero_dots_sql.format('Balances', start_date, end_date, address)))
    with open('utils/zero_dots{}_{}_{}.csv'.format(address, start_date, end_date), 'w', newline='') as outfile:
        outcsv = csv.writer(outfile)
        outcsv.writerow(zero_dots.keys())
        outcsv.writerows(zero_dots.fetchall())

    incoming_txns = db_session.execute(text(incoming_txns_sql.format('Balances', start_date, end_date, address)))
    with open('utils/incoming_txns_{}_{}_{}.csv'.format(address, start_date, end_date), 'w', newline='') as outfile:
        outcsv = csv.writer(outfile)
        outcsv.writerow(incoming_txns.keys())
        outcsv.writerows(incoming_txns.fetchall())

    outgoing_txns = db_session.execute(text(outgoing_txns_sql.format('Balances', start_date, end_date, address)))
    with open('utils/outgoing_txns_{}_{}_{}.csv'.format(address, start_date, end_date), 'w', newline='') as outfile:
        outcsv = csv.writer(outfile)
        outcsv.writerow(outgoing_txns.keys())
        outcsv.writerows(outgoing_txns.fetchall())


def db_connect(username="root", password="root", host="localhost", port=3306, name="polkadot_analysis"):
    DB_CONNECTION = "mysql+mysqlconnector://{}:{}@{}:{}/{}".format(username, password, host, port, name)
    engine = create_engine(DB_CONNECTION, echo=False, isolation_level="READ_UNCOMMITTED", pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return scoped_session(session_factory)


# Main
if __name__ == '__main__':
    try:
        start_date = 0
        end_date = 0

        db_session = db_connect("root", "root", "localhost", 3306, "polkadot_analysis")
        rows = totals(start_date, end_date)
        logger.info("Results: Volume, Total Value, Max Value")
        logger.info(rows.fetchall()[0])

        data = read_csv("../../distinct_self_loops_perpetuators.csv")
        address_list = data['SENDER'].tolist()

        with open('distinct_self_loops_account_totals.csv', 'a', newline='') as outfile:
            outcsv = csv.writer(outfile)
            for address in address_list:
                result = db_session.execute(text(sql2), {"address": address}).fetchall()
                logger.info("Printing Line: {}".format(result))
                # outcsv.writerow(result.keys())
                outcsv.writerows(result)

    except Exception as err:
        db_session.remove()  # close db connection
        logger.error(traceback.format_exc())
