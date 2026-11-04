"""Platform-owned account profile retirement; caller owns scopes and transactions.

These trusted server helpers do not authorize HTTP callers, change tenant GUCs,
commit, or delete billing/payment records. Discovery must enumerate inactive
as well as active tenant scopes and the platform (None) scope.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

from controlplane_db.models import (
    ChatHistoryAI,
    ChatSessionAI,
    IdentityRetirement,
    User,
    UserGroupMembership,
    UserMagicLink,
    UserPasskey,
    UserPasskeyChallenge,
    UserPasswordReset,
    UserPreference,
    UserWalletBinding,
)
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from controlplane_tenancy.tenant_membership import lock_identity

ACCOUNT_PROFILE_RETENTION = timedelta(days=89)


def _test_plane_wipes_freely() -> bool:
    """True only for the exact test-plane setting ``ACCOUNT_CLOSURE_RETENTION=none``.

    This setting changes the personal-profile waiting period only. Financial
    retention, preservation holds and outstanding obligations retain their rules.
    """
    return os.environ.get("ACCOUNT_CLOSURE_RETENTION", "").strip().lower() == "none"


def _closure_retention() -> timedelta:
    if _test_plane_wipes_freely():
        return timedelta(0)
    return ACCOUNT_PROFILE_RETENTION


def _preservation_hold_blocks(hold: bool) -> bool:
    return bool(hold)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Aware account lifecycle timestamp required")
    return value.astimezone(UTC)


def _erased_email(subject: str, identifier: uuid.UUID) -> str:
    digest = hashlib.sha256(
        f"account-profile-retirement-v1\n{subject}\n{identifier}".encode()
    ).digest()
    # A case-insensitive, 59-character local part fits the existing email
    # uniqueness index without retaining the contact address or raw subject.
    encoded = base64.b32encode(digest).rstrip(b"=").decode("ascii").lower()
    return f"closed+{encoded}@account.invalid"


async def _require_scope(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    actual = await session.scalar(
        text("SELECT current_setting('app.current_tenant_id', true)")
    )
    if actual != (str(tenant_id) if tenant_id else ""):
        raise ValueError("Explicit matching profile database scope required")


async def disable_subject_memberships(
    session: AsyncSession, tenant_id: uuid.UUID | None, subject: str
) -> tuple[uuid.UUID, ...]:
    await _require_scope(session, tenant_id)
    await lock_identity(session, subject)
    if await session.get(IdentityRetirement, subject, populate_existing=True) is None:
        raise ValueError("Identity retirement must be recorded first")
    rows = (
        (
            await session.execute(
                select(User)
                .where(User.tenant_id == tenant_id, User.keycloak_sub == subject)
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.is_active = False
    await session.flush()
    return tuple(row.id for row in rows)


async def _purge_legacy_chats(
    session: AsyncSession, tenant_id, identifiers
) -> dict[str, int]:
    sessions = list(
        (
            await session.execute(
                select(ChatSessionAI)
                .where(
                    ChatSessionAI.tenant_id == tenant_id,
                    ChatSessionAI.user_id.in_(identifiers),
                )
                .order_by(ChatSessionAI.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )
    counts = {"chat_sessions_ai": 0, "chat_histories_ai": 0, "shared_chat_histories": 0}
    if not sessions:
        return counts
    # A tenant-filtered reference count cannot prove that deleting a history
    # won't cascade into hidden references. Require actual owner/global read
    # authority instead of silently treating RLS-hidden children as absent.
    global_read = await session.scalar(
        text("""SELECT
        bool_and((NOT c.relrowsecurity OR r.rolsuper OR r.rolbypassrls OR
          (pg_has_role(current_user,c.relowner,'USAGE') AND NOT c.relforcerowsecurity))
          AND has_table_privilege(current_user,c.oid,'SELECT')
          AND has_table_privilege(current_user,c.oid,'DELETE'))
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles r ON r.rolname=current_user
        WHERE c.oid IN ('public.chat_sessions_ai'::regclass,
                        'public.chat_histories_ai'::regclass)""")
    )
    if global_read is not True:
        raise ValueError("Legacy history owner authority required")
    history_ids = sorted({row.history_id for row in sessions})
    histories = list(
        (
            await session.execute(
                select(ChatHistoryAI)
                .where(
                    ChatHistoryAI.id.in_(history_ids),
                )
                .order_by(ChatHistoryAI.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )
    # Parent locks and global authority cover every referenced history, including
    # a history owned by another scope. Its last account reference must not be
    # removed without cleaning the newly orphaned history in this transaction.
    # Histories still referenced by any other account remain untouched.
    result = await session.execute(
        delete(ChatSessionAI).where(
            ChatSessionAI.tenant_id == tenant_id,
            ChatSessionAI.user_id.in_(identifiers),
            ChatSessionAI.id.in_([row.id for row in sessions]),
        )
    )
    counts["chat_sessions_ai"] = result.rowcount
    for history in histories:
        remaining = await session.scalar(
            select(func.count())
            .select_from(ChatSessionAI)
            .where(ChatSessionAI.history_id == history.id)
        )
        if remaining:
            counts["shared_chat_histories"] += 1
        else:
            await session.delete(history)
            counts["chat_histories_ai"] += 1
    return counts


async def purge_retired_profile(
    session: AsyncSession,
    tenant_id: uuid.UUID | None,
    subject: str,
    user_ids: tuple[uuid.UUID, ...],
    *,
    verified_closed_at: datetime,
    now: datetime,
) -> dict[str, int]:
    closed, current = _aware(verified_closed_at), _aware(now)
    if current < closed + _closure_retention():
        raise ValueError("Account profile retention window has not elapsed")
    await _require_scope(session, tenant_id)
    await lock_identity(session, subject)
    marker = await session.get(IdentityRetirement, subject, populate_existing=True)
    if marker is None or marker.retired_at > closed:
        raise ValueError("Verified identity retirement required")
    rows = (
        (
            await session.execute(
                select(User)
                .where(User.tenant_id == tenant_id, User.id.in_(user_ids))
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) != len(set(user_ids)):
        raise ValueError("Complete matching profile inventory required")
    for row in rows:
        placeholder = _erased_email(subject, row.id)
        if row.keycloak_sub != subject and not (
            row.keycloak_sub is None
            and row.deleted_at is not None
            and not row.is_active
            and row.email == placeholder
        ):
            raise ValueError("Profile inventory does not belong to retired subject")
    emails = [row.email.strip().lower() for row in rows if row.keycloak_sub == subject]
    ambiguous = await session.scalar(
        select(User.id)
        .where(
            User.tenant_id == tenant_id,
            User.id.not_in([row.id for row in rows]),
            func.lower(func.btrim(User.email)).in_(emails),
        )
        .limit(1)
    )
    if ambiguous is not None:
        raise ValueError(
            "Ambiguous email-owned authentication data requires owner proof"
        )
    counts = await _purge_legacy_chats(session, tenant_id, [row.id for row in rows])
    for model in (
        UserPreference,
        UserPasswordReset,
        UserMagicLink,
        UserGroupMembership,
    ):
        result = await session.execute(
            delete(model).where(
                model.tenant_id == tenant_id,
                model.user_id.in_([row.id for row in rows]),
            )
        )
        counts[model.__tablename__] = result.rowcount
    for model, field in (
        (UserPasskey, UserPasskey.user_email),
        (UserPasskeyChallenge, UserPasskeyChallenge.email),
    ):
        result = await session.execute(
            delete(model).where(
                model.tenant_id == tenant_id, func.lower(func.btrim(field)).in_(emails)
            )
        )
        counts[model.__tablename__] = result.rowcount
    if tenant_id is None:
        result = await session.execute(
            delete(UserWalletBinding).where(UserWalletBinding.keycloak_sub == subject)
        )
        counts["user_wallet_bindings"] = result.rowcount
    counts["profiles"] = sum(row.keycloak_sub == subject for row in rows)
    for row in rows:
        row.email = _erased_email(subject, row.id)
        row.first_name = row.last_name = ""
        row.gender = "unspecified"
        row.image_url = row.password = row.sso_provider_id = None
        row.sociacl_attributes = None
        row.keycloak_sub = row.role_id = row.activated_at = None
        row.is_active = False
        row.deleted_at = row.deleted_at or current
    await session.flush()
    return counts
