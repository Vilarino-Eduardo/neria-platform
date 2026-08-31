import re
import uuid
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.core import (
    KnowledgeChunk,
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)

ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}
MAX_EXTRACTED_CHARACTERS = 2_000_000


def normalize_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def extract_text(content: bytes, extension: str) -> str:
    if extension == ".txt":
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1")
    if extension == ".pdf":
        reader = PdfReader(BytesIO(content))
        if len(reader.pages) > 300:
            raise ValueError("O PDF excede o limite de 300 páginas.")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if extension == ".docx":
        document = Document(BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    raise ValueError("Formato não suportado.")


def split_into_chunks(text: str, target_size: int = 1200, overlap: int = 150) -> list[str]:
    paragraphs = [value.strip() for value in text.split("\n") if value.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        parts = [paragraph[index : index + target_size] for index in range(0, len(paragraph), target_size)]
        for part in parts:
            candidate = f"{current}\n{part}".strip()
            if current and len(candidate) > target_size:
                chunks.append(current)
                current = f"{current[-overlap:]} {part}".strip()
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def create_processed_source(
    session: Session,
    *,
    organization_id: uuid.UUID,
    title: str,
    source_type: KnowledgeSourceType,
    text: str,
    filename: str | None = None,
    mime_type: str | None = None,
    storage_key: str | None = None,
) -> KnowledgeSource:
    normalized = normalize_text(text)
    if len(normalized) < 20:
        raise ValueError("Não foi possível extrair conteúdo suficiente.")
    if len(normalized) > MAX_EXTRACTED_CHARACTERS:
        raise ValueError("O conteúdo extraído excede o limite permitido.")
    source = KnowledgeSource(
        organization_id=organization_id,
        title=title,
        source_type=source_type,
        status=KnowledgeSourceStatus.READY,
        filename=filename,
        mime_type=mime_type,
        storage_key=storage_key,
        character_count=len(normalized),
    )
    session.add(source)
    session.flush()
    session.add_all(
        KnowledgeChunk(
            organization_id=organization_id,
            source_id=source.id,
            position=position,
            content=chunk,
            chunk_metadata={"characters": len(chunk)},
        )
        for position, chunk in enumerate(split_into_chunks(normalized))
    )
    return source


def build_storage_key(organization_id: uuid.UUID, filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Envie um arquivo TXT, PDF ou DOCX.")
    return f"{organization_id}/{uuid.uuid4()}{extension}"
