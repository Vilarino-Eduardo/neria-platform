from app.config_loader import load_bot_config
from app.catalog import load_catalog, format_catalog
from app.session import set_state, get_state, clear_state
import random



def get_main_menu(config):

    return (
        f'{config["welcome"]}\n\n'
        "1 - Consultar produtos\n"
        "2 - Nossas lojas\n"
        "3 - Falar com atendente"
    )



def get_product_menu():

    return (
        "Escolha uma categoria:\n\n"
        "1 - Eletrônicos\n"
        "2 - Informática\n"
        "3 - Acessórios"
    )



def generate_protocol():

    return random.randint(10000, 99999)



def generate_response(message, client_id="demo", phone="demo-user"):

    config = load_bot_config(client_id)

    message = message.lower().strip()


    state = get_state(phone)



    # MENU INICIAL

    if message in ["oi", "olá", "ola", "menu", "inicio"]:

        clear_state(phone)

        return get_main_menu(config)



    # ESCOLHA DE PRODUTOS

    if message == "1" and state is None:

        set_state(phone, "categories")

        return get_product_menu()



    # CATEGORIAS

    if state == "categories":


        if message == "1":

            clear_state(phone)

            return format_catalog(
                load_catalog("eletronicos")
            )


        elif message == "2":

            clear_state(phone)

            return format_catalog(
                load_catalog("informatica")
            )


        elif message == "3":

            clear_state(phone)

            return format_catalog(
                load_catalog("acessorios")
            )


        else:

            return "Escolha uma categoria válida."



    # LOJAS

    if message == "2" and state is None:

        return (
            "Nossas lojas:\n\n"
            "Loja Centro\n"
            "📍 Rua Principal, 123\n"
            "📞 (54) 99999-1111\n"
            "⏰ Segunda a sábado: 09h às 18h\n\n"
            "Loja Shopping\n"
            "📍 Avenida Central, 500\n"
            "📞 (54) 98888-2222\n"
            "⏰ Segunda a domingo: 10h às 22h"
        )



    # ATENDENTE

    if message == "3" and state is None:

        protocol = generate_protocol()

        return (
            "Atendimento aberto!\n\n"
            f"Seu protocolo é #{protocol}.\n\n"
            "Um de nossos atendentes entrará em contato em breve."
        )



    return (
        "Não entendi sua mensagem.\n\n"
        "Digite MENU para iniciar."
    )