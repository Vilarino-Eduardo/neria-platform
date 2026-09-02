import re
import unicodedata
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import KnowledgeChunk, KnowledgeSource, KnowledgeSourceStatus
from app.services.ai.contracts import RetrievedKnowledge

STOP_WORDS = {
    "a", "ao", "as", "com", "como", "da", "das", "de", "do", "dos", "e", "em",
    "consigo", "eu", "meu", "minha", "o", "os", "para", "por", "preciso", "qual",
    "quais", "quanta", "quantas", "quanto", "quantos", "que", "quero", "tenho", "um",
    "uma", "voces",
}

SYNONYM_GROUPS = {
    "agendamento": {
        "agenda", "agendamento", "agendar", "marcar", "remarcar", "reagendar",
        "reagendamento", "reserva", "reservar",
    },
    "cancelamento": {"cancelamento", "cancelar", "desmarcar"},
    "disponibilidade": {"disponibilidade", "disponivel", "estoque"},
    "endereco": {"endereco", "localizacao", "local", "onde"},
    "entrega": {"entrega", "envio", "frete", "transportadora"},
    "horario": {
        "abre", "abrem", "aberto", "fecha", "fecham", "funcionamento", "horario",
        "horas", "expediente",
    },
    "pagamento": {
        "boleto", "cartao", "pagamento", "pagar", "parcela", "parcelamento",
        "parcelar", "pix",
    },
    "prazo": {"prazo", "tempo", "periodo", "dias"},
    "preco": {"custo", "investimento", "orcamento", "orcar", "preco", "valor"},
    "promocao": {"promocao", "desconto", "oferta"},
    "troca": {"troca", "trocar", "devolucao", "devolver", "substituicao"},
}
SYNONYM_INDEX = {
    synonym: canonical
    for canonical, synonyms in SYNONYM_GROUPS.items()
    for synonym in synonyms
}


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def terms(value: str) -> list[str]:
    return [
        SYNONYM_INDEX.get(term, term)
        for term in re.findall(r"[a-z0-9]+", normalize_text(value))
        if len(term) > 2 and term not in STOP_WORDS
    ]


def relevance_score(query: str, content: str) -> float:
    query_terms = Counter(terms(query))
    if not query_terms:
        return 0
    content_terms = Counter(terms(content))
    matches = {
        term: content_terms[term]
        or max(
            (
                count
                for candidate, count in content_terms.items()
                if min(len(term), len(candidate)) >= 5
                and term[:5] == candidate[:5]
            ),
            default=0,
        )
        for term in query_terms
    }
    matched = sum(
        min(weight, matches[term]) for term, weight in query_terms.items()
    )
    coverage = sum(1 for term in query_terms if matches[term]) / len(query_terms)
    return matched + coverage


class LexicalKnowledgeRetriever:
    """MVP retriever that can later be replaced by vector or hybrid search."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def search(
        self, organization_id: str, query: str, limit: int = 5
    ) -> list[RetrievedKnowledge]:
        rows = self.session.execute(
            select(KnowledgeChunk, KnowledgeSource.title)
            .join(KnowledgeSource, KnowledgeSource.id == KnowledgeChunk.source_id)
            .where(
                KnowledgeChunk.organization_id == uuid.UUID(organization_id),
                KnowledgeSource.status == KnowledgeSourceStatus.READY,
            )
            .limit(5000)
        )
        ranked = [
            RetrievedKnowledge(
                chunk_id=str(chunk.id),
                source_title=title,
                content=chunk.content,
                score=relevance_score(query, chunk.content),
            )
            for chunk, title in rows
        ]
        return sorted(
            (item for item in ranked if item.score > 0),
            key=lambda item: item.score,
            reverse=True,
        )[:limit]
