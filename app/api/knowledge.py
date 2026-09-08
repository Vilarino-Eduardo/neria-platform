import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.settings import get_settings
from app.models.core import (
    KnowledgeChunk,
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
    UserRole,
)
from app.schemas.knowledge import (
    KnowledgeChunkResponse,
    KnowledgeSourceResponse,
    ManualKnowledgeCreate,
)
from app.services.knowledge_service import (
    build_storage_key,
    create_processed_source,
)
from app.services.object_storage import get_object_storage
from app.tasks.knowledge import enqueue_knowledge_source_processing

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)


def require_admin(current_user: CurrentUser) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem alterar a base.")


def get_source(
    session: DatabaseSession, organization_id: uuid.UUID, source_id: uuid.UUID
) -> KnowledgeSource:
    source = session.scalar(
        select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.organization_id == organization_id,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Fonte não encontrada.")
    return source


@router.get("/sources", response_model=list[KnowledgeSourceResponse])
def list_sources(
    session: DatabaseSession, current_user: CurrentUser
) -> list[KnowledgeSource]:
    return list(
        session.scalars(
            select(KnowledgeSource)
            .where(KnowledgeSource.organization_id == current_user.organization_id)
            .order_by(KnowledgeSource.updated_at.desc())
        )
    )


@router.post(
    "/sources/manual",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_source(
    payload: ManualKnowledgeCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> KnowledgeSource:
    require_admin(current_user)
    source = create_processed_source(
        session,
        organization_id=current_user.organization_id,
        title=payload.title,
        source_type=KnowledgeSourceType.MANUAL,
        text=payload.content,
    )
    session.commit()
    session.refresh(source)
    return source


@router.post(
    "/sources/upload",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_source(
    session: DatabaseSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=200)] = None,
) -> KnowledgeSource:
    require_admin(current_user)
    settings = get_settings()
    content = await file.read(settings.knowledge_max_file_bytes + 1)
    if len(content) > settings.knowledge_max_file_bytes:
        raise HTTPException(status_code=413, detail="O arquivo excede o limite de 10 MB.")
    try:
        storage_key = build_storage_key(current_user.organization_id, file.filename or "")
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    storage = get_object_storage()
    try:
        storage.put(storage_key, content, file.content_type)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Falha ao armazenar o arquivo.") from exc
    try:
        source = KnowledgeSource(
            organization_id=current_user.organization_id,
            title=(title or Path(file.filename or "Documento").stem).strip(),
            source_type=KnowledgeSourceType.FILE,
            status=KnowledgeSourceStatus.PROCESSING,
            filename=Path(file.filename or "documento").name,
            mime_type=file.content_type,
            storage_key=storage_key,
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        enqueue_knowledge_source_processing(str(source.id))
        return source
    except Exception as exc:
        session.rollback()
        try:
            storage.delete(storage_key)
        except Exception:
            logger.exception("knowledge_upload_compensation_failed")
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=str(exc)) from None
        raise


@router.get("/sources/{source_id}/chunks", response_model=list[KnowledgeChunkResponse])
def list_source_chunks(
    source_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[KnowledgeChunk]:
    get_source(session, current_user.organization_id, source_id)
    return list(
        session.scalars(
            select(KnowledgeChunk)
            .where(
                KnowledgeChunk.source_id == source_id,
                KnowledgeChunk.organization_id == current_user.organization_id,
            )
            .order_by(KnowledgeChunk.position)
        )
    )


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    require_admin(current_user)
    source = get_source(session, current_user.organization_id, source_id)
    storage_key = source.storage_key
    if storage_key:
        try:
            get_object_storage().delete(storage_key)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Não foi possível remover o arquivo armazenado.",
            ) from exc
    session.delete(source)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
