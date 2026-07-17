from app.whatsapp import send_message
from app.conversation import save_conversation
from app.bot import generate_response
from app.client_manager import get_client_id



def process_message(phone, message):

    client_id = get_client_id(phone)


    response = generate_response(
        message,
        client_id,
        phone
    )


    save_conversation(
        phone,
        message,
        response
    )


    send_message(
        phone,
        response
    )


    return response