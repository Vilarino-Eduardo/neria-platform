import pytest

from scripts.verify_backup_restore import (
    require_local_database,
    validate_restore_database,
)


def test_backup_verification_accepts_only_local_database() -> None:
    local = require_local_database(
        "postgresql+psycopg://neria:neria@localhost:5432/neria"
    )
    assert local.database == "neria"
    with pytest.raises(ValueError, match="somente"):
        require_local_database(
            "postgresql+psycopg://neria:secret@database.example.com/neria"
        )


def test_restore_database_name_is_strictly_scoped() -> None:
    validate_restore_database("neria_restore_check_012345abcdef")
    for unsafe in ("neria", "postgres", "neria_restore_check_123", "other_012345abcdef"):
        with pytest.raises(ValueError, match="inseguro"):
            validate_restore_database(unsafe)
