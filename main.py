from app.config import BOT_NAME
from flask import Flask
from app.routes import messages_bp


app = Flask(__name__, template_folder="app/templates")

app.register_blueprint(messages_bp)


@app.route("/")
def home():
    return "WhatsApp Automation is running!"


if __name__ == "__main__":
    app.run(debug=True)