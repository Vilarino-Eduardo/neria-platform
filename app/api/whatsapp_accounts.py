import uuid

import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.core.crypto import decrypt_secret, encrypt_secret
from app.integrations.whatsapp.client import MetaWhatsAppClient
from app.models.core import (
    UserRole,
    WhatsAppAccount,
    WhatsAppAccountStatus,
    WhatsAppTemplate,
    WhatsAppTemplateStatus,
)
from app.schemas.whatsapp import (
    WhatsAppAccountCreate,
    WhatsAppAccountResponse,
    WhatsAppTemplateResponse,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/whatsapp-accounts", tags=["whatsapp"])


@router.get("", response_model=list[WhatsAppAccountResponse])
def list_whatsapp_accounts(
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[WhatsAppAccount]:
    return list(
        session.scalars(
            select(WhatsAppAccount).where(
                WhatsAppAccount.organization_id == current_user.organization_id
            )
        )
    )


@router.post("", response_model=WhatsAppAccountResponse, status_code=status.HTTP_201_CREATED)
def create_whatsapp_account(
    payload: WhatsAppAccountCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> WhatsAppAccount:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem conectar o WhatsApp.")

    existing = session.scalar(
        select(WhatsAppAccount.id).where(
            WhatsAppAccount.organization_id == current_user.organization_id
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="O plano atual permite um número de WhatsApp.")

    account = WhatsAppAccount(
        organization_id=current_user.organization_id,
        display_name=payload.display_name,
        phone_number=payload.phone_number,
        meta_phone_number_id=payload.meta_phone_number_id,
        meta_business_account_id=payload.meta_business_account_id,
        access_token_encrypted=encrypt_secret(payload.access_token),
        status=WhatsAppAccountStatus.PENDING,
        is_primary=True,
    )
    session.add(account)
    session.flush()
    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="whatsapp.account_created",
        target_type="whatsapp_account",
        target_id=str(account.id),
        metadata={"phone_number": account.phone_number},
    )
    session.commit()
    session.refresh(account)
    return account


@router.post("/{account_id}/verify", response_model=WhatsAppAccountResponse)
def verify_whatsapp_account(
    account_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> WhatsAppAccount:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem validar o WhatsApp.")

    account = session.scalar(
        select(WhatsAppAccount).where(
            WhatsAppAccount.id == account_id,
            WhatsAppAccount.organization_id == current_user.organization_id,
        )
    )
    if account is None or not account.access_token_encrypted or not account.meta_phone_number_id:
        raise HTTPException(status_code=404, detail="Conta do WhatsApp não encontrada.")

    client = MetaWhatsAppClient(
        access_token=decrypt_secret(account.access_token_encrypted),
        phone_number_id=account.meta_phone_number_id,
    )
    try:
        client.verify_phone_number()
    except httpx.HTTPError:
        raise HTTPException(status_code=422, detail="A Meta recusou as credenciais informadas.") from None

    account.status = WhatsAppAccountStatus.ACTIVE
    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="whatsapp.account_verified",
        target_type="whatsapp_account",
        target_id=str(account.id),
    )
    session.commit()
    session.refresh(account)
    return account


@router.get("/{account_id}/templates", response_model=list[WhatsAppTemplateResponse])
def list_whatsapp_templates(
    account_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[WhatsAppTemplate]:
    return list(
        session.scalars(
            select(WhatsAppTemplate).where(
                WhatsAppTemplate.whatsapp_account_id == account_id,
                WhatsAppTemplate.organization_id == current_user.organization_id,
            )
        )
    )


@router.post("/{account_id}/templates/sync", response_model=list[WhatsAppTemplateResponse])
def sync_whatsapp_templates(
    account_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[WhatsAppTemplate]:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem sincronizar templates.")

    account = session.scalar(
        select(WhatsAppAccount).where(
            WhatsAppAccount.id == account_id,
            WhatsAppAccount.organization_id == current_user.organization_id,
        )
    )
    if (
        account is None
        or not account.access_token_encrypted
        or not account.meta_phone_number_id
        or not account.meta_business_account_id
    ):
        raise HTTPException(status_code=404, detail="Conta do WhatsApp não encontrada.")

    client = MetaWhatsAppClient(
        access_token=decrypt_secret(account.access_token_encrypted),
        phone_number_id=account.meta_phone_number_id,
    )
    try:
        remote_templates = client.list_templates(
            business_account_id=account.meta_business_account_id
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Não foi possível consultar os templates.") from None

    for remote in remote_templates:
        template = session.scalar(
            select(WhatsAppTemplate).where(
                WhatsAppTemplate.whatsapp_account_id == account.id,
                WhatsAppTemplate.name == remote["name"],
                WhatsAppTemplate.language == remote["language"],
            )
        )
        remote_status = remote.get("status", "PENDING").lower()
        try:
            template_status = WhatsAppTemplateStatus(remote_status)
        except ValueError:
            template_status = WhatsAppTemplateStatus.PENDING

        if template is None:
            template = WhatsAppTemplate(
                organization_id=current_user.organization_id,
                whatsapp_account_id=account.id,
                name=remote["name"],
                language=remote["language"],
                category=remote.get("category"),
                status=template_status,
            )
            session.add(template)
        else:
            template.category = remote.get("category")
            template.status = template_status

    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="whatsapp.templates_synced",
        target_type="whatsapp_account",
        target_id=str(account.id),
        metadata={"remote_count": len(remote_templates)},
    )
    session.commit()
    return list(
        session.scalars(
            select(WhatsAppTemplate).where(
                WhatsAppTemplate.whatsapp_account_id == account.id
            )
        )
    )
