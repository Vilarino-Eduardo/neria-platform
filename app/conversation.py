import json
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

FILE_PATH = DATA_DIR / "conversations.json"



def load_conversations():

    DATA_DIR.mkdir(exist_ok=True)


    if not FILE_PATH.exists():

        return []


    try:

        with open(FILE_PATH, "r", encoding="utf-8") as file:

            data = json.load(file)


            if isinstance(data, list):

                return data


            return []


    except json.JSONDecodeError:

        return []



def save_conversation(phone, user_message, bot_response):

    conversations = load_conversations()


    conversation = {

        "phone": phone,

        "timestamp": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "user": user_message,

        "bot": bot_response

    }


    conversations.append(conversation)


    with open(FILE_PATH, "w", encoding="utf-8") as file:

        json.dump(
            conversations,
            file,
            indent=4,
            ensure_ascii=False
        )