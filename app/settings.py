"""
settings.py

Database and Substrate Node Config

<Author>: Hanaa Abbas
<Email>: hanaaloutfy94@gmail.com
<Date>: 31 May, 2023

GNU General Public License Version 3
"""

import os

DB_NAME = os.environ.get("DB_NAME", "polkadot_analysis")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", 3306)
DB_USERNAME = os.environ.get("DB_USERNAME", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "root")

DB_CONNECTION = os.environ.get("DB_CONNECTION", "mysql+mysqlconnector://{}:{}@{}:{}/{}?charset=utf8mb4".format(
    DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
))

SUBSTRATE_RPC_URL = os.environ.get("SUBSTRATE_RPC_URL", "http://substrate-node:9933/")
SUBSTRATE_ADDRESS_TYPE = int(os.environ.get("SUBSTRATE_ADDRESS_TYPE", 42))