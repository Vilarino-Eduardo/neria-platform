from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@contextmanager
def integrity_conflict(session: Session, detail: str) -> Iterator[None]:
    try:
        yield
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail=detail) from None
