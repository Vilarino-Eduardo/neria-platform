import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SESSIONS_FILE = BASE_DIR / "data" / "sessions.json"



def load_sessions():

    if not SESSIONS_FILE.exists():

        return {}


    try:

        with open(
            SESSIONS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)


    except json.JSONDecodeError:

        return {}



def save_sessions(sessions):

    with open(
        SESSIONS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            sessions,
            file,
            indent=4,
            ensure_ascii=False
        )



def set_state(phone, state):

    sessions = load_sessions()


    sessions[phone] = {
        "state": state
    }


    save_sessions(sessions)



def get_state(phone):

    sessions = load_sessions()


    if phone in sessions:

        return sessions[phone].get("state")


    return None



def clear_state(phone):

    sessions = load_sessions()


    if phone in sessions:

        del sessions[phone]


        save_sessions(sessions)