import os
from dotenv import load_dotenv

load_dotenv()


BOT_NAME = os.getenv("BOT_NAME")
ENVIRONMENT = os.getenv("ENVIRONMENT")