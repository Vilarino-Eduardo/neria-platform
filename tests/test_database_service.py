from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.services.database import integrity_conflict


def test_integrity_conflict_rolls_back_and_returns_409() -> None:
    session = Mock()

    with (
        pytest.raises(HTTPException) as error,
        integrity_conflict(session, "Registro já cadastrado."),
    ):
        raise IntegrityError("INSERT", {}, Exception("unique violation"))

    assert error.value.status_code == 409
    assert error.value.detail == "Registro já cadastrado."
    session.rollback.assert_called_once_with()
