from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.db import utcnow
from ashare_evidence.models import AccountSpace

ROOT_ACCOUNT_LOGIN = "root"
ROLE_ROOT = "root"
ROLE_MEMBER = "member"


def ensure_account_space(
    session: Session,
    *,
    account_login: str,
    role_snapshot: str,
    actor_login: str | None = None,
    created_by_root: bool = False,
    mark_seen: bool = True,
    mark_acted: bool = False,
) -> AccountSpace:
    normalized_login = str(account_login).strip()
    if not normalized_login:
        raise ValueError("account_login is required")
    record = session.get(AccountSpace, normalized_login)
    now = utcnow()
    if record is None:
        record = AccountSpace(
            account_login=normalized_login,
            role_snapshot=role_snapshot,
            first_seen_at=now,
            last_seen_at=now if mark_seen else None,
            last_acted_at=now if mark_acted else None,
            created_by_root=created_by_root,
            metadata_payload={"created_by_actor_login": actor_login} if actor_login else {},
        )
        session.add(record)
    else:
        record.role_snapshot = role_snapshot
        if mark_seen:
            record.last_seen_at = now
        if mark_acted:
            record.last_acted_at = now
        payload = dict(record.metadata_payload or {})
        if actor_login:
            payload["last_actor_login"] = actor_login
        if created_by_root:
            record.created_by_root = True
        record.metadata_payload = payload
    session.flush()
    return record


def record_account_presence(
    session: Session,
    *,
    actor_login: str,
    actor_role: str,
    target_login: str,
    mark_acted: bool = False,
) -> None:
    ensure_account_space(
        session,
        account_login=actor_login,
        role_snapshot=actor_role,
        actor_login=actor_login,
        created_by_root=False,
        mark_seen=True,
        mark_acted=mark_acted and actor_login == target_login,
    )
    if target_login != actor_login:
        ensure_account_space(
            session,
            account_login=target_login,
            role_snapshot=ROLE_MEMBER,
            actor_login=actor_login,
            created_by_root=actor_role == ROLE_ROOT,
            mark_seen=True,
            mark_acted=mark_acted,
        )


def visible_account_spaces(session: Session, *, actor_login: str, actor_role: str) -> list[dict[str, Any]]:
    if actor_role == ROLE_ROOT:
        records = session.scalars(
            select(AccountSpace).order_by(AccountSpace.account_login.asc())
        ).all()
    else:
        record = ensure_account_space(
            session,
            account_login=actor_login,
            role_snapshot=actor_role,
            actor_login=actor_login,
            created_by_root=False,
            mark_seen=True,
            mark_acted=False,
        )
        records = [record]
    return [
        {
            "account_login": record.account_login,
            "role_snapshot": record.role_snapshot,
            "first_seen_at": record.first_seen_at,
            "last_seen_at": record.last_seen_at,
            "last_acted_at": record.last_acted_at,
            "created_by_root": record.created_by_root,
        }
        for record in records
    ]
