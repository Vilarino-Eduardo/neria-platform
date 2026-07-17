import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

CLIENTS_DIR = BASE_DIR / "data" / "clients"



def load_bot_config(client_id="demo"):

    config_file = CLIENTS_DIR / f"{client_id}.json"


    with open(config_file, "r", encoding="utf-8") as file:

        return json.load(file)