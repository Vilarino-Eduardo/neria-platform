import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

CATALOG_DIR = BASE_DIR / "data" / "catalogs"



def load_catalog(category):

    file_path = CATALOG_DIR / f"{category}.json"


    if not file_path.exists():

        return []


    with open(file_path, "r", encoding="utf-8") as file:

        return json.load(file)



def format_catalog(products):

    if not products:

        return "Nenhum produto encontrado."


    response = "Produtos disponíveis:\n\n"


    for product in products:

        response += (
            f'{product["name"]}\n'
            f'Preço: {product["price"]}\n'
            f'Status: {product["availability"]}\n\n'
        )


    return response