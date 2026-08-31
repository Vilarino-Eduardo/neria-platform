import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.api.dashboard import get_dashboard
from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import Contact, Conversation, User, UserRole
from app.services.audit import record_audit

router = APIRouter(prefix="/exports", tags=["exports"])

VALUE_LABELS = {
    "open": "Aberta",
    "closed": "Encerrada",
    "bot": "Bot",
    "human": "Humano",
    "low": "Baixa",
    "normal": "Normal",
    "high": "Alta",
    "urgent": "Urgente",
}


def require_admin(current_user: CurrentUser) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem exportar dados.")


def safe_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def csv_response(filename: str, headers: list[str], rows: list[list[object]]) -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows([[safe_cell(value) for value in row] for row in rows])
    content = "\ufeff" + output.getvalue()
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def record_export(
    session: DatabaseSession, current_user: CurrentUser, export_type: str
) -> None:
    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="data.exported",
        target_type="export",
        metadata={"type": export_type},
    )
    session.commit()


@router.get("/contacts.csv")
def export_contacts(session: DatabaseSession, current_user: CurrentUser) -> Response:
    require_admin(current_user)
    contacts = session.scalars(
        select(Contact)
        .where(Contact.organization_id == current_user.organization_id)
        .order_by(Contact.created_at.desc())
        .limit(50000)
    )
    rows = [
        [
            contact.name or contact.profile_name,
            contact.phone_number,
            "Sim" if contact.is_blocked else "Não",
            contact.created_at.isoformat(),
        ]
        for contact in contacts
    ]
    record_export(session, current_user, "contacts")
    return csv_response(
        "neria-contatos.csv",
        ["Nome", "Telefone", "Bloqueado", "Cadastrado em"],
        rows,
    )


@router.get("/conversations.csv")
def export_conversations(session: DatabaseSession, current_user: CurrentUser) -> Response:
    require_admin(current_user)
    assignee = aliased(User)
    rows_query = session.execute(
        select(Conversation, Contact, assignee.name.label("assignee_name"))
        .join(Contact, Contact.id == Conversation.contact_id)
        .outerjoin(assignee, assignee.id == Conversation.assigned_user_id)
        .where(Conversation.organization_id == current_user.organization_id)
        .order_by(Conversation.created_at.desc())
        .limit(50000)
    )
    rows = [
        [
            row.Contact.name or row.Contact.profile_name,
            row.Contact.phone_number,
            VALUE_LABELS[row.Conversation.status.value],
            VALUE_LABELS[row.Conversation.mode.value],
            VALUE_LABELS[row.Conversation.priority.value],
            row.assignee_name,
            row.Conversation.last_message_at.isoformat()
            if row.Conversation.last_message_at
            else None,
            row.Conversation.closed_at.isoformat() if row.Conversation.closed_at else None,
            row.Conversation.created_at.isoformat(),
        ]
        for row in rows_query
    ]
    record_export(session, current_user, "conversations")
    return csv_response(
        "neria-conversas.csv",
        [
            "Contato",
            "Telefone",
            "Situação",
            "Modo",
            "Prioridade",
            "Responsável",
            "Última mensagem",
            "Encerrada em",
            "Criada em",
        ],
        rows,
    )


@router.get("/team-performance.csv")
def export_team_performance(
    session: DatabaseSession, current_user: CurrentUser
) -> Response:
    require_admin(current_user)
    dashboard = get_dashboard(session, current_user)
    rows = [
        [
            item.name,
            "Administrador" if item.role == UserRole.ADMIN else "Atendente",
            "Ativo" if item.is_active else "Inativo",
            item.open_assigned,
            item.closed_30d,
            item.messages_sent_30d,
            item.average_response_minutes,
        ]
        for item in dashboard.team_performance
    ]
    record_export(session, current_user, "team_performance")
    return csv_response(
        f"neria-equipe-{datetime.now(UTC).date().isoformat()}.csv",
        [
            "Usuário",
            "Perfil",
            "Situação",
            "Conversas abertas",
            "Encerradas em 30 dias",
            "Mensagens em 30 dias",
            "Resposta média (minutos)",
        ],
        rows,
    )
