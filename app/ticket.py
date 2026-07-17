import json
import random
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

TICKETS_FILE = BASE_DIR / "data" / "tickets.json"



def load_tickets():

    if not TICKETS_FILE.exists():

        return []


    try:

        with open(
            TICKETS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)


    except json.JSONDecodeError:

        return []



def save_tickets(tickets):

    with open(
        TICKETS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            tickets,
            file,
            indent=4,
            ensure_ascii=False
        )



def create_ticket(phone):

    tickets = load_tickets()


    protocol = str(
        random.randint(10000, 99999)
    )


    ticket = {

        "protocol": protocol,

        "phone": phone,

        "status": "open",

        "created_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    }


    tickets.append(ticket)


    save_tickets(tickets)


    return protocol