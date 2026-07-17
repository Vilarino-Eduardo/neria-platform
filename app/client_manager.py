import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

MAPPING_FILE = BASE_DIR / "data" / "client_mapping.json"



def get_client_id(phone):

    if not MAPPING_FILE.exists():

        return "demo"


    with open(MAPPING_FILE, "r", encoding="utf-8") as file:

        clients = json.load(file)


    return clients.get(phone, "demo")