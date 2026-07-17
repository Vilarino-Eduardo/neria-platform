from flask import Flask

from app.config import BOT_NAME
from app.routes import messages_bp
from app.core.database import database


app = Flask(
    __name__,
    template_folder="app/templates"
)


app.register_blueprint(messages_bp)


@app.route("/")
def home():

    return "WhatsApp Automation is running!"


def initialize_application():

    database.get_connection()

    print("Database initialized.")


if __name__ == "__main__":

    initialize_application()

    app.run(debug=True)