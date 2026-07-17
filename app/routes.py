from flask import Blueprint, request, jsonify, render_template
from app.services import process_message


messages_bp = Blueprint("messages", __name__)


@messages_bp.route("/message", methods=["POST"])
def receive_message():
    data = request.json

    incoming_message = data.get("message")
    phone = data.get("phone")

    response = process_message(phone, incoming_message)

    return jsonify({
        "response": response
    })


@messages_bp.route("/chat")
def chat():
    return render_template("chat.html")