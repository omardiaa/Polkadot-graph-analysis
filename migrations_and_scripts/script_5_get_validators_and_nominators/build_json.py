import yaml
import json
import pymysql
import logging
import os
from datetime import datetime
from scalecodec.utils.ss58 import ss58_encode, is_valid_ss58_address
from substrateinterface import SubstrateInterface

# Load database configuration
with open("../../config.yaml", "r") as file:
    config = yaml.safe_load(file)

DB_HOST = config["database"]["host"]
DB_PORT = config["database"]["port"]
DB_USER = config["database"]["user"]
DB_PASSWORD = config["database"]["password"]
DB_NAME = config["database"]["name"]

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Connect to the database
connection = pymysql.connect(
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    port=DB_PORT,
    charset='utf8mb4'
)

def set_group_concat_max_len():
    """
    Set SESSION group_concat_max_len to handle large concatenations.
    """
    with connection.cursor() as cursor:
        cursor.execute("SET SESSION group_concat_max_len = 1000000;")
        connection.commit()

def fetch_payout_stakers():
    """
    Load all staking.payout_stakers extrinsics that have multiple call_args.
    """
    set_group_concat_max_len()
    query = """
        SELECT block_id, extrinsic_idx, COUNT(*) as counts, 
               GROUP_CONCAT(call_args SEPARATOR '-separator-') as concat_call_args
        FROM polkadot_analysis.extrinsic
        WHERE module_id = 'staking' AND call_id = 'payout_stakers' AND success = 1
        GROUP BY block_id, extrinsic_idx
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()

def parse_json_separated(json_string, separator="-separator-"):
    """
    Splits and parses JSON objects separated by a specific separator.
    """
    try:
        return [json.loads(obj) for obj in json_string.split(separator)]
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON: {e} | JSON: {json_string}")
        return []

def normalize_event(data):
    """
    Extracts address and amount from staking event attributes.
    """
    result = {"address": None, "amount": None}
    try:
        if isinstance(data, list) and isinstance(data[0], dict):
            for item in data:
                if item.get("type") == "AccountId":
                    result["address"] = item.get("value")
                elif item.get("type") == "Balance" or item.get("type_name") == "BalanceOf":
                    result["amount"] = int(item.get("value"))
                elif item.get("type_name") == "AccountId":
                    result["address"] = ss58_encode(item.get("value").replace('0x', ''), 0)
        elif isinstance(data, dict):
            if isinstance(data.get("dest"), dict) and "Account" in data["dest"]:
                result["address"] = data["dest"]["Account"]
            elif "stash" in data:
                result["address"] = data["stash"]
            elif "who" in data:
                result["address"] = data["who"]
            if "amount" in data:
                result["amount"] = data["amount"]
        elif isinstance(data, list) and len(data) in [2, 3]:
            result["address"] = data[0]
            result["amount"] = data[2] if len(data) == 3 else data[1]
        if not result["address"]:
            raise ValueError("Address is missing or invalid in the input data.")
        return result
    except Exception as e:
        logging.error(f"Error processing event: {e}")
        return result

def correct_balance(era, balance):
    if not isinstance(balance, int):
        raise ValueError(f"Balance is not an integer for era {era}")
    if era >= 80: #80: 1_247_607, should be 1_248_328 (small inaccuracy)
        token_decimals = 10
    else:
        token_decimals = 12
    return balance / 10 ** token_decimals

def load_eras():
    with open("../script_4_get_eras_blocks/era_blocks.json", "r") as file:
        return json.load(file)

def process_payout_stakers():
    """
    Process the payout stakers extrinsics and extract staking rewards.
    """
    eras_staking_info = {}
    rows = fetch_payout_stakers()
    era_blocks = load_eras()
    print("Loaded payout_stakers")
    counter = 0
    wrong_count = 0
    total = len(rows)
    for row in rows:
        counter = counter + 1
        if counter % 1000 == 0:
            print("Processed {} out of {} with percentage: {}%".format(counter, total, counter/total*100))
        block_id, extrinsic_idx, _, concat_call_args = row
        parsed_data = parse_json_separated(concat_call_args)
        validator_era_pairs = []
        
        for obj in parsed_data:
            validator_stash = obj[0]['value']
            era = int(obj[1]['value'])
            if not is_valid_ss58_address(validator_stash):
                validator_stash = ss58_encode(validator_stash.replace('0x', ''), 0)
            validator_era_pairs.append((validator_stash, era))
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT attributes FROM polkadot_analysis.event
                WHERE block_id = %s AND extrinsic_idx = %s 
                  AND module_id = 'staking' AND (event_id = 'rewarded' OR event_id = 'reward')
            """, (block_id, extrinsic_idx))
            rewards = [normalize_event(json.loads(row[0])) for row in cursor.fetchall()]

        validator_idx = 0
        current_validator, current_era = None, None
        next_validator, next_era = validator_era_pairs[validator_idx]

        for reward in rewards:
            if reward["address"] == next_validator:
                blocks_produced = []

                # In case of Utility.batch(payout_stakers with same stash (e.g. 2 times), and one fails because validator didn't validate in that era)

                while len(blocks_produced) == 0:
                    current_validator, current_era = next_validator, next_era
                    
                    validator_idx += 1
                    if validator_idx < len(validator_era_pairs):
                        next_validator, next_era = validator_era_pairs[validator_idx]

                    if validator_idx > len(validator_era_pairs):
                        break
                    if current_era == 0:
                        start_block = 0
                    else:
                        try:
                            start_block = era_blocks[str(current_era-1)]
                        except Exception as e:
                            import pdb; pdb.set_trace()
                    end_block = era_blocks.get(str(current_era), start_block * 2) # In last iteration, end_block is set to 2 * start_block
                    
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT id FROM polkadot_analysis.block 
                            WHERE author = %s AND id >= %s AND id < %s
                        """, (current_validator, start_block, end_block))
                        blocks_produced = [row[0] for row in cursor.fetchall()]


                    if len(blocks_produced) == 0:
                        print("Skipping validator rewards at era {}".format(current_era))

                if len(blocks_produced) == 0:
                    print("Should not reach here")
                    break

                if str(current_era) not in eras_staking_info:
                    eras_staking_info[str(current_era)] = {}
                
                if  correct_balance(block_id, reward["amount"]) > 0 and len(blocks_produced) == 0:
                    wrong_count = wrong_count + 1
                    print("Wrong count [should not reach here]: ", wrong_count)

                eras_staking_info[str(current_era)][current_validator] = {
                    "reward": correct_balance(block_id, reward["amount"]),
                    "blocks_produced": blocks_produced,
                    "nominators": []
                }
            elif current_validator:
                eras_staking_info[str(current_era)][current_validator]["nominators"].append({
                    "address": reward["address"],
                    "reward": correct_balance(block_id, reward["amount"])
                })

        if validator_idx != len(validator_era_pairs) and len(rewards) != 0:
            print("Missing validator in payout_staker events at block {}".format(block_id))
    
    with open("eras_staking_info.json", "w") as file:
        json.dump(eras_staking_info, file, indent=4)
    
    logging.info("Saved staking rewards data to eras_staking_info.json")

if __name__ == "__main__":
    process_payout_stakers()
