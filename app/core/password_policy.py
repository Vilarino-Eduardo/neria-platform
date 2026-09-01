import unicodedata

COMMON_PASSWORDS = {
    "123456789012",
    "administrador",
    "administrator",
    "password1234",
    "qwertyuiop12",
    "senha1234567",
    "senhaadministrador",
}


def validate_password_strength(password: str) -> str:
    if len(password) < 12:
        raise ValueError("A senha deve ter pelo menos 12 caracteres.")
    if len(password) > 128:
        raise ValueError("A senha deve ter no máximo 128 caracteres.")

    normalized = unicodedata.normalize("NFKC", password).casefold()
    compact = "".join(character for character in normalized if character.isalnum())
    if compact in COMMON_PASSWORDS or len(set(normalized)) < 4:
        raise ValueError("Escolha uma senha menos comum e menos repetitiva.")
    return password
